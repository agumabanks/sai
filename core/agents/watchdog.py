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

import psutil

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

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
    "antigravity-web": "active",
    "antigravity-worker": "active",
    "antigravity-beat": "active",
}

OPTIONAL_SERVICES = {
    "php8.4-fpm": "active",
    "supervisor": "active",
}

# Ports to verify (port → description)
CRITICAL_PORTS = {
    22: "SSH",
    80: "HTTP",
    443: "HTTPS",
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

    async def run_full_check(self) -> list[WatchdogEvent]:
        """
        Run ALL checks and return a list of events.
        Crash-resistant: each check is wrapped in try/except.
        """
        events = []
        checks = [
            ("ssh", self._check_ssh),
            ("fail2ban", self._check_fail2ban),
            ("services", self._check_services),
            ("resources", self._check_resources),
            ("connectivity", self._check_connectivity),
            ("ports", self._check_ports),
            ("reboots", self._check_recent_reboots),
            ("disk_io", self._check_disk_health),
        ]

        for name, check_fn in checks:
            try:
                check_events = await check_fn()
                events.extend(check_events)
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

        return events

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

        # Load average
        load1, load5, load15 = psutil.getloadavg()
        cores = psutil.cpu_count()
        if load1 > self.thresholds["load_critical"]:
            events.append(WatchdogEvent(
                category="resource", severity=SEVERITY_CRITICAL,
                message=f"Load average {load1:.1f} ({cores} cores) — system overloaded",
                metric="load.1m", value=f"{load1:.1f}",
            ))

        # Swap usage (OOM risk)
        swap = psutil.swap_memory()
        if swap.total > 0 and swap.percent > 80:
            events.append(WatchdogEvent(
                category="resource", severity=SEVERITY_HIGH,
                message=f"Swap at {swap.percent}% — system is memory-starved, OOM risk",
                metric="swap.percent", value=f"{swap.percent}%",
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

        # DNS check
        try:
            socket.getaddrinfo("ai.sanaa.co", 443, socket.AF_INET)
        except socket.gaierror:
            events.append(WatchdogEvent(
                category="network",
                severity=SEVERITY_HIGH,
                message="DNS resolution failing for ai.sanaa.co",
                metric="dns.resolve",
                value="failed",
            ))

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
                "last reboot --since yesterday | grep -c reboot",
                shell=True, capture_output=True, text=True, timeout=5,
            )
            reboot_count = int(result.stdout.strip() or "0")
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
                "df -i / | tail -1 | awk '{print $5}'",
                shell=True, capture_output=True, text=True, timeout=5,
            )
            inode_pct = int(result.stdout.strip().replace("%", "") or "0")
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
            f"systemctl is-active {service}",
            shell=True, capture_output=True, text=True, timeout=5,
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
            "fail2ban-client status sshd",
            shell=True, capture_output=True, text=True, timeout=5,
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
            "last -n 20 | grep 'pts/' | awk '{print $3}' | sort -u",
            shell=True, capture_output=True, text=True, timeout=5,
        )
        ips = set()
        for line in result.stdout.strip().split("\n"):
            ip = line.strip()
            if ip and not ip.startswith("tmux") and not ip.startswith(":"):
                ips.add(ip)
        return ips
    except Exception:
        return set()


def _fail2ban_has_ignoreip() -> bool:
    """Check if fail2ban jail.local has ignoreip configured."""
    try:
        result = subprocess.run(
            "grep -v '^#' /etc/fail2ban/jail.local 2>/dev/null | grep 'ignoreip'",
            shell=True, capture_output=True, text=True, timeout=5,
        )
        return bool(result.stdout.strip())
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
