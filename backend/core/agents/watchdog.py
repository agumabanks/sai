"""
Sanaa AI Watchdog — Real-time server health monitoring with escalation.

Monitors:
  - SSH service status + fail2ban bans
  - All critical system services
  - Network connectivity (DNS, external reach)
  - Port accessibility (key service ports)
  - Resource usage with tiered escalation
  - Recent reboots (crash detection)

Patterns applied from reference repos:
  - OpenClaw: crash-resistant task loop, exponential escalation
  - Lobster: diffLast for change detection, structured events
  - ClawHub: event sourcing, audit logging
"""

import asyncio
import hashlib
import logging
import socket
import subprocess
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import functools
import traceback

import psutil

from core.config import get_settings
from core.intelligence.memory import IntelligenceMemory
from core.database import SystemKnowledge

logger = logging.getLogger(__name__)
settings = get_settings()

def watchdog_task(category: str = "generic"):
    """
    Universal watchdog wrapper for background tasks.
    Usage:
        @watchdog_task(category="email")
        async def my_task(): ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            wd = ServerWatchdog()
            memory = IntelligenceMemory()
            try:
                # Log task start
                WatchdogEvent(
                    category=category,
                    severity=SEVERITY_INFO,
                    message=f"Task {func.__name__} started",
                    metric=f"task.{func.__name__}.status",
                    value="running"
                ).to_dict() # This normally would log to a feed or DB
                
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                # Crash-resistant: log error and remediation
                error_msg = f"Task {func.__name__} crashed: {str(e)}"
                event = WatchdogEvent(
                    category=category,
                    severity=SEVERITY_CRITICAL,
                    message=error_msg,
                    metric=f"task.{func.__name__}.status",
                    value="crashed",
                    remediation=f"Check logs for {func.__name__} traceback"
                )
                logger.error(f"{error_msg}\n{traceback.format_exc()}")
                # Emit to memory for healer to pick up
                memory.add_strategic_signal({
                    "category": category,
                    "title": f"Task Failure: {func.__name__}",
                    "summary": error_msg,
                    "severity": SEVERITY_CRITICAL,
                    "score": 9
                })
                return None
        return wrapper
    return decorator

# Severity levels for escalation
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_HIGH = "high"
SEVERITY_CRITICAL = "critical"

# Services to monitor (name → expected state)
CRITICAL_SERVICES = {
    "ssh": "active",
    "nginx": "active",
    "postgresql": "active",
    "redis-server": "active",
    "fail2ban": "active",
    "sanaa-ai-web": "active",
    "sanaa-ai-worker": "active",
    "sanaa-ai-beat": "active",
}

OPTIONAL_SERVICES = {
    "php8.4-fpm": "active",
    "whatsjet-worker": "active",
    "ollama": "active",
}

# Ports to verify (port → description)
CRITICAL_PORTS = {
    22: "SSH",
    80: "HTTP",
    443: "HTTPS",
    3306: "MySQL (WhatsJet)",
    5432: "PostgreSQL",
    6379: "Redis",
    8100: "Sanaa AI",
    11434: "Ollama",
}

# External hosts to ping for connectivity check
CONNECTIVITY_TARGETS = [
    ("8.8.8.8", "Google DNS"),
    ("1.1.1.1", "Cloudflare DNS"),
]

# Admin IPs that should never be banned (loaded from recent logins)
KNOWN_ADMIN_IPS = set()


class WatchdogEvent:
    """Structured event from the watchdog."""

    def __init__(self, category: str, severity: str, message: str,
                 metric: str = "", value: str = "", remediation: str = ""):
        self.id = hashlib.md5(f"{category}:{message}".encode()).hexdigest()[:12]
        self.category = category
        self.severity = severity
        self.message = message
        self.metric = metric
        self.value = value
        self.remediation = remediation
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "metric": self.metric,
            "value": self.value,
            "remediation": self.remediation,
            "timestamp": self.timestamp.isoformat(),
        }


class ServerWatchdog:
    """
    Comprehensive server watchdog with crash-resistant monitoring.
    Each check runs independently — errors in one check don't block others.
    """

    def __init__(self):
        self.thresholds = {
            "cpu_warn": 70,
            "cpu_critical": settings.cpu_alert_threshold,
            "ram_warn": 70,
            "ram_critical": settings.ram_alert_threshold,
            "disk_warn": 75,
            "disk_critical": settings.disk_alert_threshold,
            "load_warn": 3.0,
            "load_critical": settings.load_alert_threshold,
        }
        # Track previous state for diffLast pattern (change detection)
        self._last_state: dict = {}
        self._consecutive_failures: dict[str, int] = {}

    async def run_full_check(self) -> tuple[list[WatchdogEvent], list[str]]:
        """
        Run ALL checks and return (events, checked_metrics).
        Crash-resistant: each check is wrapped in try/except.
        """
        # Refresh thresholds from DB preferences (persisted from the Admin UI)
        self.thresholds["cpu_critical"] = await SystemKnowledge.get_pref("alert.threshold.cpu", self.thresholds["cpu_critical"])
        self.thresholds["ram_critical"] = await SystemKnowledge.get_pref("alert.threshold.ram", self.thresholds["ram_critical"])
        self.thresholds["disk_critical"] = await SystemKnowledge.get_pref("alert.threshold.disk", self.thresholds["disk_critical"])

        events = []
        checked_metrics = []
        
        # Mapping of check name to anticipated metrics for resolution tracking
        METRIC_MAP = {
            "ssh": ["service.ssh", "port.22"],
            "fail2ban": ["service.fail2ban", "fail2ban.admin_banned"],
            "services": [f"service.{s}" for s in CRITICAL_SERVICES.keys()],
            "scheduler": ["scheduler.beat_alive", "scheduler.last_dispatch_age"],
            "resources": [
                "cpu.percent", "memory.percent", "disk.percent", "load.1m", "swap.percent",
                "cpu.trend", "memory.trend", "disk.trend"
            ],
            "ports": [f"port.{p}" for p in CRITICAL_PORTS.keys()],
            "connectivity": [f"connectivity.{h}" for h, _ in CONNECTIVITY_TARGETS],
            "disk_io": ["disk.inodes"],
        }

        checks = [
            ("ssh", self._check_ssh),
            ("fail2ban", self._check_fail2ban),
            ("services", self._check_services),
            ("scheduler", self._check_scheduler_health),
            ("resources", self._check_resources),
            ("connectivity", self._check_connectivity),
            ("ports", self._check_ports),
            ("reboots", self._check_recent_reboots),
            ("disk_io", self._check_disk_health),
            ("backups", self._check_database_backups),
        ]

        for name, check_fn in checks:
            try:
                check_events = await check_fn()
                events.extend(check_events)
                checked_metrics.extend(METRIC_MAP.get(name, []))
                # Reset failure counter on success
                self._consecutive_failures[name] = 0
            except Exception as e:
                # Crash-resistant: log and continue
                self._consecutive_failures[name] = self._consecutive_failures.get(name, 0) + 1
                logger.error(f"Watchdog check '{name}' failed: {e}")
                if self._consecutive_failures[name] >= 3:
                    events.append(WatchdogEvent(
                        category="watchdog",
                        severity=SEVERITY_HIGH,
                        message=f"Watchdog check '{name}' has failed {self._consecutive_failures[name]} times consecutively: {e}",
                        metric=f"check.{name}.failures",
                    ))

        return events, checked_metrics

    # ==================== SSH ====================

    async def _check_ssh(self) -> list[WatchdogEvent]:
        events = []
        sshd_status = _systemctl_status("ssh")

        if sshd_status != "active":
            events.append(WatchdogEvent(
                category="access",
                severity=SEVERITY_CRITICAL,
                message=f"SSH service is {sshd_status} — remote access is DOWN",
                metric="service.ssh",
                value=sshd_status,
                remediation="sudo systemctl start ssh",
            ))

        # Check if SSH port is actually listening
        if not _is_port_open(22):
            events.append(WatchdogEvent(
                category="access",
                severity=SEVERITY_CRITICAL,
                message="SSH port 22 is not listening — server is unreachable via SSH",
                metric="port.22",
                value="closed",
                remediation="sudo systemctl restart ssh && sudo ufw allow 22/tcp",
            ))

        return events

    # ==================== FAIL2BAN ====================

    async def _check_fail2ban(self) -> list[WatchdogEvent]:
        events = []

        f2b_status = _systemctl_status("fail2ban")
        if f2b_status != "active":
            events.append(WatchdogEvent(
                category="security",
                severity=SEVERITY_WARNING,
                message="fail2ban is not running — brute-force protection disabled",
                metric="service.fail2ban",
                value=f2b_status,
                remediation="sudo systemctl start fail2ban",
            ))
            return events

        # Check for admin IP bans
        banned_ips = _get_fail2ban_banned_ips()
        admin_ips = _get_recent_admin_ips()

        for ip in admin_ips:
            if ip in banned_ips:
                events.append(WatchdogEvent(
                    category="access",
                    severity=SEVERITY_CRITICAL,
                    message=f"Admin IP {ip} is BANNED by fail2ban — you are locked out!",
                    metric="fail2ban.admin_banned",
                    value=ip,
                    remediation=f"sudo fail2ban-client set sshd unbanip {ip}",
                ))

        # Report total bans for awareness
        if len(banned_ips) > 10:
            events.append(WatchdogEvent(
                category="security",
                severity=SEVERITY_INFO,
                message=f"fail2ban has {len(banned_ips)} IPs banned in sshd jail",
                metric="fail2ban.banned_count",
                value=str(len(banned_ips)),
            ))

        # Check if ignoreip is configured (it should include admin IPs)
        if not _fail2ban_has_ignoreip():
            events.append(WatchdogEvent(
                category="security",
                severity=SEVERITY_WARNING,
                message="fail2ban has no ignoreip configured — admin can get locked out",
                metric="fail2ban.no_ignoreip",
                remediation="Add 'ignoreip = 127.0.0.1/8 <your_IP>' to /etc/fail2ban/jail.local",
            ))

        return events

    # ==================== SERVICES ====================

    async def _check_services(self) -> list[WatchdogEvent]:
        events = []

        for svc, expected in CRITICAL_SERVICES.items():
            status = _systemctl_status(svc)
            if status != expected:
                events.append(WatchdogEvent(
                    category="service",
                    severity=SEVERITY_CRITICAL,
                    message=f"Critical service '{svc}' is {status} (expected: {expected})",
                    metric=f"service.{svc}",
                    value=status,
                    remediation=f"sudo systemctl restart {svc}",
                ))

        for svc, expected in OPTIONAL_SERVICES.items():
            status = _systemctl_status(svc)
            if status != expected:
                events.append(WatchdogEvent(
                    category="service",
                    severity=SEVERITY_WARNING,
                    message=f"Service '{svc}' is {status}",
                    metric=f"service.{svc}",
                    value=status,
                ))

        return events

    # ==================== SCHEDULER HEALTH ====================

    async def _check_scheduler_health(self) -> list[WatchdogEvent]:
        """Dedicated check for the Celery beat scheduler — the heartbeat of all automation.

        The _check_services check already flags beat as a CRITICAL_SERVICE, but that only
        tells us it's down. This check goes deeper:
          1. Confirms beat process is alive
          2. Inspects the celerybeat-schedule DB to see how long ago beat last dispatched
          3. Checks if beat was shed by the healer (so the event message is informative)

        A scheduler that is silently dead is the most dangerous failure mode — all tasks
        (newsletters, watchdog reports, health checks) stop with no visible error.
        """
        import os, json
        events = []

        beat_status = _systemctl_status("sanaa-ai-beat")

        if beat_status != "active":
            # Check if beat was intentionally shed by the healer
            shed_context = ""
            try:
                shed_json = await SystemKnowledge.get_pref("healer.shed_services", default=None)
                if shed_json:
                    shed = json.loads(shed_json)
                    if "sanaa-ai-beat" in shed:
                        shed_context = " (NOTE: beat was load-shed by healer — this should not happen)"
            except Exception:
                pass

            events.append(WatchdogEvent(
                category="service",
                severity=SEVERITY_CRITICAL,
                message=(
                    f"Celery beat scheduler is {beat_status} — ALL scheduled tasks are silently stopped."
                    f" No newsletters, no monitoring, no watchdog reports will fire.{shed_context}"
                ),
                metric="scheduler.beat_alive",
                value=beat_status,
                remediation="sudo systemctl start sanaa-ai-beat",
            ))
            return events  # No point checking dispatch age if process is dead

        # Beat is running — check if it's actually dispatching by inspecting the schedule DB
        # celerybeat-schedule is a shelve DB written by beat on each dispatch cycle
        schedule_db_paths = [
            "/var/www/ai.sanaa.co/backend/celerybeat-schedule",
            "/opt/antigravity/celerybeat-schedule",
        ]
        for db_path in schedule_db_paths:
            # shelve writes .db, .dir, or no extension depending on the backend
            for suffix in ("", ".db", ".dir"):
                candidate = db_path + suffix
                if os.path.exists(candidate):
                    try:
                        age_seconds = time.time() - os.path.getmtime(candidate)
                        age_minutes = age_seconds / 60
                        # Beat writes to the schedule DB every max_interval (default 5 min)
                        # If the file is more than 15 minutes old, beat is stalled
                        if age_minutes > 15:
                            events.append(WatchdogEvent(
                                category="service",
                                severity=SEVERITY_HIGH,
                                message=(
                                    f"Celery beat appears stalled — schedule DB last updated "
                                    f"{age_minutes:.0f} min ago (expected < 5 min). "
                                    f"Beat process may be hung."
                                ),
                                metric="scheduler.last_dispatch_age",
                                value=f"{age_minutes:.0f}m",
                                remediation="sudo systemctl restart sanaa-ai-beat",
                            ))
                    except Exception:
                        pass
                    break  # Found a file for this db_path, stop suffix search

        return events

    # ==================== RESOURCES ====================

    async def _check_resources(self) -> list[WatchdogEvent]:
        events = []

        # CPU
        cpu = psutil.cpu_percent(interval=1)
        if cpu > self.thresholds["cpu_critical"]:
            events.append(WatchdogEvent(
                category="resource", severity=SEVERITY_CRITICAL,
                message=f"CPU at {cpu}% — critical threshold exceeded",
                metric="cpu.percent", value=f"{cpu}%",
            ))
        elif cpu > self.thresholds["cpu_warn"]:
            events.append(WatchdogEvent(
                category="resource", severity=SEVERITY_WARNING,
                message=f"CPU at {cpu}% — elevated usage",
                metric="cpu.percent", value=f"{cpu}%",
            ))

        # Memory
        mem = psutil.virtual_memory()
        if mem.percent > self.thresholds["ram_critical"]:
            # Find top memory consumers for remediation hint
            top_procs = _get_top_processes("memory", 3)
            events.append(WatchdogEvent(
                category="resource", severity=SEVERITY_CRITICAL,
                message=f"Memory at {mem.percent}% — {mem.available / (1024**3):.1f}GB free. Top: {top_procs}",
                metric="memory.percent", value=f"{mem.percent}%",
            ))
        elif mem.percent > self.thresholds["ram_warn"]:
            events.append(WatchdogEvent(
                category="resource", severity=SEVERITY_WARNING,
                message=f"Memory at {mem.percent}%",
                metric="memory.percent", value=f"{mem.percent}%",
            ))

        # Disk
        disk = psutil.disk_usage("/")
        if disk.percent > self.thresholds["disk_critical"]:
            events.append(WatchdogEvent(
                category="resource", severity=SEVERITY_CRITICAL,
                message=f"Disk at {disk.percent}% — only {disk.free / (1024**3):.1f}GB free",
                metric="disk.percent", value=f"{disk.percent}%",
                remediation="Check large files: du -sh /var/log/* /tmp/* | sort -rh | head -10",
            ))
        elif disk.percent > self.thresholds["disk_warn"]:
            events.append(WatchdogEvent(
                category="resource", severity=SEVERITY_WARNING,
                message=f"Disk at {disk.percent}%",
                metric="disk.percent", value=f"{disk.percent}%",
            ))

        # --- PREDICTIVE TREND ANALYSIS (Resource Creep) ---
        trend_events = await self._track_resource_trends(cpu, mem.percent, disk.percent)
        events.extend(trend_events)

        # Load average
        load1, load5, load15 = psutil.getloadavg()
        cores = psutil.cpu_count()
        load_warn_limit = max(float(self.thresholds["load_warn"]), cores * 0.75)
        load_critical_limit = max(float(self.thresholds["load_critical"]), float(cores))
        if load1 > load_critical_limit:
            events.append(WatchdogEvent(
                category="resource", severity=SEVERITY_CRITICAL,
                message=f"Load average {load1:.1f} ({cores} cores) — critical threshold {load_critical_limit:.1f} exceeded",
                metric="load.1m", value=f"{load1:.1f}",
            ))
        elif load1 > load_warn_limit:
            events.append(WatchdogEvent(
                category="resource", severity=SEVERITY_WARNING,
                message=f"Load average {load1:.1f} ({cores} cores) — elevated but below critical threshold",
                metric="load.1m", value=f"{load1:.1f}",
            ))

        # Swap usage (OOM risk)
        swap = psutil.swap_memory()
        if swap.total > 0 and swap.percent > 80 and mem.percent > 90:
            events.append(WatchdogEvent(
                category="resource", severity=SEVERITY_HIGH,
                message=f"Swap at {swap.percent}% and RAM at {mem.percent}% — system is severely memory-starved, OOM risk",
                metric="swap.percent", value=f"{swap.percent}%",
            ))

        return events

    # ==================== TREND ANALYSIS ====================

    async def _track_resource_trends(self, cpu: float, ram: float, disk: float) -> list[WatchdogEvent]:
        """Track growth rates and issue early warnings for Resource Creep."""
        events = []
        metrics = {"cpu": cpu, "memory": ram, "disk": disk}
        
        for name, current_val in metrics.items():
            key = f"resource.last.{name}"
            prev_val = await SystemKnowledge.get_pref(key, default=None)
            
            # Store current for next run
            await SystemKnowledge.set_pref(key, str(current_val), source="watchdog_trend")
            
            if prev_val is None:
                continue
                
            prev_val = float(prev_val)
            growth = current_val - prev_val
            
            # Trend Detection Logic
            # Disk Creep: If disk grows > 1% in a single check (usually 1-5 mins)
            if name == "disk" and growth > 1.0:
                events.append(WatchdogEvent(
                    category="foresight",
                    severity=SEVERITY_WARNING,
                    message=f"PREDICTIVE: Significant Disk Creep detected (+{growth:.1f}%). Disk will be full soon if this trend continues.",
                    metric="disk.trend",
                    value=f"+{growth:.1f}%",
                    remediation="Audit /var/log and identify rapidly growing files."
                ))
            
            # Memory Creep (Slow Leak): If RAM grows > 5% without corresponding load spike
            if name == "memory" and growth > 5.0:
                events.append(WatchdogEvent(
                    category="foresight",
                    severity=SEVERITY_WARNING,
                    message=f"PREDICTIVE: Memory Leak Warning (+{growth:.1f}%). System RAM is climbing rapidly.",
                    metric="memory.trend",
                    value=f"+{growth:.1f}%",
                    remediation="Observe top processes for memory-intensive background tasks."
                ))

        return events

    # ==================== CONNECTIVITY ====================

    async def _check_connectivity(self) -> list[WatchdogEvent]:
        events = []
        reachable = 0

        for host, name in CONNECTIVITY_TARGETS:
            if _can_reach(host):
                reachable += 1
            else:
                events.append(WatchdogEvent(
                    category="network",
                    severity=SEVERITY_WARNING,
                    message=f"Cannot reach {name} ({host})",
                    metric=f"connectivity.{host}",
                    value="unreachable",
                ))

        if reachable == 0:
            events.append(WatchdogEvent(
                category="network",
                severity=SEVERITY_CRITICAL,
                message="Server has NO internet connectivity — all external targets unreachable",
                metric="connectivity.total",
                value="0",
            ))

        # DNS & SSL check for main domains
        import ssl
        domains_to_check = ["ai.sanaa.co", "soko.sanaa.ug", "fx.sanaa.co", "cards.sanaa.ug"]
        
        for domain in domains_to_check:
            try:
                # DNS
                socket.getaddrinfo(domain, 443, socket.AF_INET)
                
                # SSL Expiry
                context = ssl.create_default_context()
                with socket.create_connection((domain, 443), timeout=5) as sock:
                    with context.wrap_socket(sock, server_hostname=domain) as ssock:
                        cert = ssock.getpeercert()
                        expiry_date = datetime.strptime(cert['notAfter'], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                        days_left = (expiry_date - datetime.now(timezone.utc)).days
                        
                        if days_left < 7:
                            events.append(WatchdogEvent(
                                category="security",
                                severity=SEVERITY_CRITICAL if days_left < 2 else SEVERITY_HIGH,
                                message=f"SSL Certificate for {domain} expires in {days_left} days!",
                                metric=f"ssl.expiry.{domain}",
                                value=f"{days_left}d",
                            ))
            except socket.gaierror:
                events.append(WatchdogEvent(
                    category="network",
                    severity=SEVERITY_HIGH,
                    message=f"DNS resolution failing for {domain}",
                    metric=f"dns.resolve.{domain}",
                    value="failed",
                ))
            except Exception as e:
                pass # Ignore SSL parsing errors for non-https internal hosts if any

        return events

    # ==================== BACKUPS ====================
    async def _check_database_backups(self) -> list[WatchdogEvent]:
        """Verify that daily database backups exist, are fresh, and stay within retention."""
        events = []
        import os

        backup_targets = {
            "mysql": "/var/backups/sanaa/mysql",
            "root_daily": "/root/backups",
            "finance_app": "/var/www/finance/mbalala/storage/backups",
            "kalamba_app": "/var/www/kalamba.sanaa.co/mbalala/storage/backups",
        }
        now = datetime.now(timezone.utc)

        try:
            for name, backup_dir in backup_targets.items():
                if not os.path.exists(backup_dir):
                    events.append(WatchdogEvent(
                        category="system",
                        severity=SEVERITY_WARNING,
                        message=f"Backup directory {backup_dir} not found. Ensure backups are configured.",
                        metric=f"backup.{name}.dir_missing",
                        value="missing",
                    ))
                    continue

                entries = [
                    os.path.join(backup_dir, file)
                    for file in os.listdir(backup_dir)
                    if not file.startswith(".")
                ]
                if not entries:
                    events.append(WatchdogEvent(
                        category="system",
                        severity=SEVERITY_CRITICAL,
                        message=f"No backups found in {backup_dir}. Data is at risk.",
                        metric=f"backup.{name}.empty",
                        value="empty",
                    ))
                    continue

                newest_age_hours = min(
                    (now - datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)).total_seconds() / 3600
                    for path in entries
                )
                if newest_age_hours > 30:
                    events.append(WatchdogEvent(
                        category="system",
                        severity=SEVERITY_CRITICAL,
                        message=f"No fresh backup in {backup_dir}; newest is {newest_age_hours:.1f} hours old.",
                        metric=f"backup.{name}.freshness",
                        value=f"{newest_age_hours:.1f}h",
                    ))

                stale_entries = [
                    path for path in entries
                    if (now - datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)).days > 7
                ]
                if stale_entries:
                    events.append(WatchdogEvent(
                        category="system",
                        severity=SEVERITY_WARNING,
                        message=f"{len(stale_entries)} backup entry/entries in {backup_dir} exceed the one-week retention rule.",
                        metric=f"backup.{name}.retention",
                        value=str(len(stale_entries)),
                        remediation=f"Delete backups older than one week in {backup_dir}",
                    ))

                for backup in entries:
                    if os.path.isfile(backup) and backup.endswith((".sql", ".gz", ".dump")):
                        size_mb = os.path.getsize(backup) / (1024 * 1024)
                        # Some tenant databases are legitimately small. Alert only
                        # for files that are effectively empty/truncated.
                        if size_mb < 0.1:
                            events.append(WatchdogEvent(
                                category="system",
                                severity=SEVERITY_HIGH,
                                message=f"Backup {os.path.basename(backup)} is suspiciously small ({size_mb:.2f} MB).",
                                metric=f"backup.{name}.size",
                                value=f"{size_mb:.2f}MB",
                            ))
        except Exception as e:
            logger.error(f"Error checking backups: {e}")
            
        return events

    # ==================== PORTS ====================

    async def _check_ports(self) -> list[WatchdogEvent]:
        events = []
        for port, desc in CRITICAL_PORTS.items():
            if not _is_port_open(port):
                severity = SEVERITY_CRITICAL if port in (22, 80, 443, 5432) else SEVERITY_WARNING
                events.append(WatchdogEvent(
                    category="port",
                    severity=severity,
                    message=f"Port {port} ({desc}) is not listening",
                    metric=f"port.{port}",
                    value="closed",
                ))
        return events

    # ==================== REBOOTS ====================

    async def _check_recent_reboots(self) -> list[WatchdogEvent]:
        """Detect unexpected reboots (crash indicator)."""
        events = []
        boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
        uptime = datetime.now(timezone.utc) - boot_time

        # If uptime < 10 minutes, we just rebooted
        if uptime < timedelta(minutes=10):
            events.append(WatchdogEvent(
                category="system",
                severity=SEVERITY_HIGH,
                message=f"Server was rebooted {int(uptime.total_seconds())}s ago — check if unexpected",
                metric="uptime.seconds",
                value=str(int(uptime.total_seconds())),
            ))

        # Count reboots in last 24h (from 'last reboot')
        try:
            result = subprocess.run(
                ["last", "reboot", "--since", "yesterday"],
                shell=False, capture_output=True, text=True, timeout=5,
            )
            reboot_count = result.stdout.count("reboot")
            if reboot_count > 2:
                events.append(WatchdogEvent(
                    category="system",
                    severity=SEVERITY_CRITICAL,
                    message=f"Server rebooted {reboot_count} times in the last 24h — possible instability",
                    metric="reboots.24h",
                    value=str(reboot_count),
                ))
        except Exception:
            pass

        return events

    # ==================== DISK HEALTH ====================

    async def _check_disk_health(self) -> list[WatchdogEvent]:
        """Check for disk I/O issues and inode exhaustion."""
        events = []

        # Inode check
        try:
            result = subprocess.run(
                ["df", "-i", "/"],
                shell=False, capture_output=True, text=True, timeout=5,
            )
            inode_pct = 0
            for line in result.stdout.splitlines():
                parts = line.split()
                if parts and parts[-1] == "/":
                    inode_pct = int(parts[-2].replace("%", ""))
                    break
            if inode_pct > 90:
                events.append(WatchdogEvent(
                    category="resource",
                    severity=SEVERITY_CRITICAL,
                    message=f"Inode usage at {inode_pct}% — disk may appear full even with free space",
                    metric="disk.inodes",
                    value=f"{inode_pct}%",
                    remediation="Find empty dirs: find / -xdev -type d -empty | head -20",
                ))
        except Exception:
            pass

        return events


# ==================== HELPER FUNCTIONS ====================

def _systemctl_status(service: str) -> str:
    """Get systemd service status."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            shell=False, capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is listening."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def _can_reach(host: str, timeout: int = 3) -> bool:
    """Check if a host is reachable via TCP port 53 (DNS) or ICMP."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, 53)) == 0
    except Exception:
        return False


def _get_fail2ban_banned_ips() -> set[str]:
    """Get currently banned IPs from fail2ban sshd jail."""
    try:
        result = subprocess.run(
            ["fail2ban-client", "status", "sshd"],
            shell=False, capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.split("\n"):
            if "Banned IP list" in line:
                ips = line.split(":", 1)[1].strip()
                return set(ip.strip() for ip in ips.split() if ip.strip())
    except Exception:
        pass
    return set()


def _get_recent_admin_ips() -> set[str]:
    """Get IPs of recent successful SSH logins (likely admin)."""
    try:
        result = subprocess.run(
            ["last", "-n", "20"],
            shell=False, capture_output=True, text=True, timeout=5,
        )
        ips = set()
        for line in result.stdout.strip().split("\n"):
            if "pts/" not in line:
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            ip = parts[2].strip()
            if ip and not ip.startswith("tmux") and not ip.startswith(":"):
                ips.add(ip)
        return ips
    except Exception:
        return set()


def _fail2ban_has_ignoreip() -> bool:
    """Check if fail2ban jail.local has ignoreip configured."""
    try:
        with open("/etc/fail2ban/jail.local", "r") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "ignoreip" in stripped:
                    return True
        return False
    except Exception:
        return False


def _get_top_processes(sort_by: str = "memory", limit: int = 3) -> str:
    """Get top processes by CPU or memory."""
    procs = []
    for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    key = "memory_percent" if sort_by == "memory" else "cpu_percent"
    procs.sort(key=lambda x: x.get(key, 0) or 0, reverse=True)

    return ", ".join(
        f"{p['name']}({p.get(key, 0):.0f}%)" for p in procs[:limit]
    )
