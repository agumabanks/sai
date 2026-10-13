"""
Server Monitor Skill — full-stack infrastructure monitoring for the entire Sanaa platform.

Monitors all web applications, databases (MySQL, PostgreSQL, ScyllaDB, Redis),
Docker containers (Mailcow), process managers (systemd, PM2, supervisor),
SSL certificates, disk/memory/CPU, and nginx status.
"""

import asyncio
import json
import logging
import os
import re
import shlex
from datetime import datetime, timezone

from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

NGINX_AVAILABLE = "/etc/nginx/sites-available"
NGINX_ENABLED = "/etc/nginx/sites-enabled"

# Database credentials must be provided via environment variables; no fallbacks.
MYSQL_HOST = os.getenv("SERVER_MONITOR_MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = os.getenv("SERVER_MONITOR_MYSQL_PORT", "3306")
MYSQL_USER = os.getenv("SERVER_MONITOR_MYSQL_USER")
MYSQL_PASS = os.getenv("SERVER_MONITOR_MYSQL_PASS")
PG_USER = os.getenv("SERVER_MONITOR_PG_USER", "postgres")


def _db_credentials_ok() -> bool:
    return bool(MYSQL_USER and MYSQL_PASS)


async def _run(args: list[str], timeout: int = 15, cwd: str | None = None) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "timeout"
    out = stdout.decode().strip()
    if not out and stderr:
        out = stderr.decode().strip()
    return proc.returncode or 0, out


async def _run_shell(cmd: str, timeout: int = 15, cwd: str | None = None) -> tuple[int, str]:
    """Execute a hardcoded shell pipeline via ["bash", "-c", cmd]."""
    proc = await asyncio.create_subprocess_exec(
        "bash",
        "-c",
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "timeout"
    out = stdout.decode().strip()
    if not out and stderr:
        out = stderr.decode().strip()
    return proc.returncode or 0, out


def _discover_all_sites() -> list[dict]:
    """Parse all nginx site configs to discover web applications."""
    sites = []
    if not os.path.isdir(NGINX_AVAILABLE):
        return sites

    for f in sorted(os.listdir(NGINX_AVAILABLE)):
        if not f.endswith(".conf"):
            continue
        if f == "default" or f.startswith("."):
            continue

        domain = f.replace(".conf", "")
        enabled = os.path.islink(f"{NGINX_ENABLED}/{f}")

        conf_path = f"{NGINX_AVAILABLE}/{f}"
        root_path = None
        proxy_pass = None
        app_type = "static"

        try:
            with open(conf_path) as fh:
                content = fh.read()
                # Find root directive
                root_match = re.search(r'root\s+([^;]+);', content)
                if root_match:
                    root_path = root_match.group(1).strip()

                # Find proxy_pass (Node.js/Python apps)
                proxy_match = re.search(r'proxy_pass\s+([^;]+);', content)
                if proxy_match:
                    proxy_pass = proxy_match.group(1).strip()
                    app_type = "proxy"

                # Detect app framework
                if root_path:
                    if "mbalala/public" in root_path:
                        app_type = "laravel-finance"
                    elif "/public" in root_path:
                        app_type = "laravel"
                    elif "dist" in root_path or "build" in root_path or ".next" in root_path:
                        app_type = "frontend"
        except Exception:
            continue

        sites.append({
            "domain": domain,
            "enabled": enabled,
            "root": root_path,
            "proxy_pass": proxy_pass,
            "app_type": app_type,
            "conf": conf_path,
        })

    return sites


class ServerMonitorSkill(BaseSkill):
    name = "server_monitor"
    description = (
        "Full-stack server monitoring — all web apps, databases, Docker, "
        "services, SSL certificates, resources, and nginx status."
    )
    version = "1.0.0"
    permissions = ["shell", "network"]
    requires_approval = False
    timeout = 90
    tags = ["monitoring", "infrastructure", "server", "operations"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action", "overview")
        app_filter = args.get("app")
        lines_count = args.get("lines", 50)

        dispatch = {
            "overview": self._overview,
            "apps": self._apps,
            "databases": self._databases,
            "docker": self._docker,
            "services": self._services,
            "ssl": self._ssl,
            "resources": self._resources,
            "nginx": self._nginx,
            "logs": self._logs,
        }

        handler = dispatch.get(action)
        if not handler:
            return SkillResult(success=False, error=f"Unknown action: {action}")

        return await handler(app_filter, lines_count)

    # ------------------------------------------------------------------
    # overview — full server health at a glance
    # ------------------------------------------------------------------
    async def _overview(self, app_filter, lines_count) -> SkillResult:
        lines = ["SANAA PLATFORM — SERVER OVERVIEW", "=" * 55, ""]
        alerts = []
        data = {}

        # System resources
        rc, uptime = await _run(["uptime", "-p"])
        rc2, load = await _run(["cat", "/proc/loadavg"])
        rc3, mem = await _run_shell("free -h | grep Mem | awk '{print $3\"/\"$2\" (\"int($3/$2*100)\"%)\"}' | head -1")
        rc4, disk = await _run_shell("df -h / | tail -1 | awk '{print $3\"/\"$2\" (\"$5\")\"}'")
        rc5, disk_pct = await _run_shell("df / | tail -1 | awk '{print $5}' | tr -d '%'")

        lines.append("SYSTEM RESOURCES")
        lines.append(f"  Uptime:    {uptime if rc == 0 else 'unknown'}")
        lines.append(f"  Load:      {load.split()[0] if rc2 == 0 else 'unknown'} (1m avg)")
        lines.append(f"  Memory:    {mem if rc3 == 0 else 'unknown'}")
        lines.append(f"  Disk (/):  {disk if rc4 == 0 else 'unknown'}")
        lines.append("")

        if rc5 == 0 and disk_pct.isdigit() and int(disk_pct) > 85:
            alerts.append(f"Disk usage at {disk_pct}% — clean up needed")

        # Nginx sites
        sites = _discover_all_sites()
        enabled = [s for s in sites if s["enabled"]]
        data["total_sites"] = len(sites)
        data["enabled_sites"] = len(enabled)

        # Group by type
        type_counts = {}
        for s in enabled:
            t = s["app_type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        lines.append(f"WEB APPLICATIONS ({len(enabled)} active / {len(sites)} configured)")
        for t, c in sorted(type_counts.items()):
            lines.append(f"  {t}: {c}")
        lines.append("")

        # Databases
        db_status = {}
        for db_name, check_args in [
            ("MySQL", ["mysqladmin", "ping", f"-u{MYSQL_USER}", f"-p{MYSQL_PASS}"] if _db_credentials_ok() else None),
            ("PostgreSQL", ["pg_isready"]),
            ("Redis", ["redis-cli", "ping"]),
            ("ScyllaDB", ["bash", "-c", "nodetool status 2>/dev/null | head -5"]),
        ]:
            if db_name == "MySQL" and check_args is None:
                db_status[db_name] = "DOWN (credentials not configured)"
                alerts.append("MySQL monitoring credentials not configured (SERVER_MONITOR_MYSQL_USER / SERVER_MONITOR_MYSQL_PASS)")
                continue

            if len(check_args) >= 3 and check_args[0] == "bash" and check_args[1] == "-c":
                rc, out = await _run_shell(check_args[2], timeout=5)
            else:
                rc, out = await _run(check_args, timeout=5)
            alive = False
            if db_name == "MySQL":
                alive = "alive" in out.lower() if rc == 0 else False
            elif db_name == "PostgreSQL":
                alive = "accepting" in out.lower() if rc == 0 else False
            elif db_name == "Redis":
                alive = out == "PONG"
            elif db_name == "ScyllaDB":
                alive = rc == 0 and ("UN" in out or "DN" in out)
            db_status[db_name] = "UP" if alive else "DOWN"

        lines.append("DATABASES")
        for db, status in db_status.items():
            icon = "UP" if status == "UP" else "DOWN"
            lines.append(f"  {db:12s} {icon}")
            if status == "DOWN" and db not in ("ScyllaDB",):  # ScyllaDB may not be running
                alerts.append(f"{db} is DOWN")
        lines.append("")
        data["databases"] = db_status

        # Docker
        rc, docker_count = await _run_shell("docker ps -q 2>/dev/null | wc -l")
        rc2, docker_total = await _run_shell("docker ps -aq 2>/dev/null | wc -l")
        running = docker_count.strip() if rc == 0 else "0"
        total = docker_total.strip() if rc2 == 0 else "0"
        lines.append(f"DOCKER CONTAINERS: {running} running / {total} total")
        data["docker_running"] = int(running) if running.isdigit() else 0
        lines.append("")

        # Process managers
        rc, supervisor_out = await _run_shell("supervisorctl status 2>/dev/null | wc -l")
        rc2, pm2_out = await _run(["pm2", "jlist"])
        supervisor_count = supervisor_out.strip() if rc == 0 else "0"

        pm2_count = "0"
        if rc2 == 0 and pm2_out:
            try:
                pm2_apps = json.loads(pm2_out)
                pm2_count = str(len(pm2_apps))
            except Exception:
                pm2_count = "?"

        lines.append(f"PROCESS MANAGERS")
        lines.append(f"  Supervisor workers: {supervisor_count}")
        lines.append(f"  PM2 apps:           {pm2_count}")
        lines.append("")

        # SSL certificates expiring soon
        expiring = []
        for s in enabled[:30]:  # limit to avoid long runtime
            domain = s["domain"]
            cert = f"/etc/letsencrypt/live/{domain}/cert.pem"
            if os.path.exists(cert):
                rc, out = await _run(
                    ["openssl", "x509", "-in", cert, "-noout", "-enddate"]
                )
                if rc == 0 and out.startswith("notAfter="):
                    try:
                        expiry = datetime.strptime(
                            out.strip().split("=", 1)[1], "%b %d %H:%M:%S %Y %Z"
                        )
                        days_left = (expiry - datetime.now(timezone.utc).replace(tzinfo=None)).days
                        if days_left < 14:
                            expiring.append(f"  {domain}: expires in {days_left} days")
                            if days_left < 0:
                                alerts.append(f"SSL EXPIRED: {domain} ({abs(days_left)} days ago)")
                    except Exception:
                        pass

        if expiring:
            lines.append(f"SSL CERTIFICATES — {len(expiring)} expiring/expired:")
            lines.extend(expiring)
        else:
            lines.append("SSL CERTIFICATES: All OK")
        lines.append("")

        # Summary
        if alerts:
            lines.append("ALERTS:")
            for a in alerts:
                lines.append(f"  {a}")
        else:
            lines.append("All systems healthy.")

        data["alerts"] = alerts
        data["app_types"] = type_counts

        return SkillResult(
            success=len(alerts) == 0,
            output="\n".join(lines),
            data=data,
        )

    # ------------------------------------------------------------------
    # apps — detailed app status
    # ------------------------------------------------------------------
    async def _apps(self, app_filter, lines_count) -> SkillResult:
        sites = _discover_all_sites()
        if app_filter:
            sites = [s for s in sites if app_filter in s["domain"]]

        lines = [f"WEB APPLICATIONS ({len(sites)} sites)", "=" * 55, ""]
        app_data = {}

        for s in sites:
            domain = s["domain"]
            status = "enabled" if s["enabled"] else "disabled"

            # HTTP check
            rc, http = await _run(
                ["curl", "-sL", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "5", f"https://{domain}/"],
                timeout=8,
            )
            http_code = http.strip("'") if rc == 0 else "error"

            app_info = {
                "status": status,
                "type": s["app_type"],
                "http": http_code,
                "root": s["root"],
                "proxy": s["proxy_pass"],
            }
            app_data[domain] = app_info

            http_display = http_code
            if http_code in ("200", "301", "302"):
                http_display = f"{http_code} OK"
            elif http_code.startswith("5"):
                http_display = f"{http_code} ERROR"

            lines.append(f"  {domain}")
            lines.append(f"    Status: {status:10s}  HTTP: {http_display:10s}  Type: {s['app_type']}")
            if s["proxy_pass"]:
                lines.append(f"    Proxy: {s['proxy_pass']}")
            if s["root"]:
                lines.append(f"    Root:  {s['root']}")
            lines.append("")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            data=app_data,
        )

    # ------------------------------------------------------------------
    # databases — detailed database status
    # ------------------------------------------------------------------
    async def _databases(self, app_filter, lines_count) -> SkillResult:
        lines = ["DATABASE STATUS", "=" * 55, ""]
        data = {}

        # MySQL — fail closed if credentials are not configured.
        if _db_credentials_ok():
            mysql_args_base = [
                "mysql", "-h", MYSQL_HOST, "-P", MYSQL_PORT,
                f"-u{MYSQL_USER}", f"-p{MYSQL_PASS}", "-N",
            ]
            rc, mysql_ver = await _run([*mysql_args_base, "-e", "SELECT VERSION();"])
            rc2, mysql_dbs = await _run([
                *mysql_args_base, "-e",
                'SELECT schema_name FROM information_schema.schemata '
                'WHERE schema_name NOT IN ("information_schema","performance_schema","mysql","sys");',
            ])
            rc3, mysql_size = await _run([
                *mysql_args_base, "-e",
                "SELECT ROUND(SUM(data_length+index_length)/1024/1024,0) FROM information_schema.tables;",
            ])
        else:
            rc = rc2 = rc3 = -1
            mysql_ver = mysql_dbs = mysql_size = "credentials not configured"

        lines.append("MYSQL")
        lines.append(f"  Version:    {mysql_ver if rc == 0 else 'unreachable'}")
        db_list = mysql_dbs.splitlines() if rc2 == 0 and mysql_dbs else []
        lines.append(f"  Databases:  {len(db_list)}")
        lines.append(f"  Total size: {mysql_size} MB" if rc3 == 0 else "  Total size: unknown")
        if db_list:
            lines.append(f"  Names:      {', '.join(db_list[:20])}")
        lines.append("")
        data["mysql"] = {"version": mysql_ver if rc == 0 else None, "databases": db_list, "size_mb": mysql_size if rc3 == 0 else None}

        # PostgreSQL
        pg_args_base = ["psql", "-U", PG_USER]
        rc, pg_ver = await _run([*pg_args_base, "-t", "-c", "SELECT version();"])
        rc2, pg_dbs = await _run([
            *pg_args_base, "-t", "-c",
            "SELECT datname FROM pg_database WHERE datistemplate=false AND datname != 'postgres';",
        ])
        lines.append("POSTGRESQL")
        lines.append(f"  Version:    {pg_ver.strip()[:60] if rc == 0 else 'unreachable'}")
        pg_list = [d.strip() for d in pg_dbs.splitlines() if d.strip()] if rc2 == 0 and pg_dbs else []
        lines.append(f"  Databases:  {len(pg_list)}")
        if pg_list:
            lines.append(f"  Names:      {', '.join(pg_list[:20])}")
        lines.append("")
        data["postgresql"] = {"databases": pg_list}

        # Redis
        rc, redis_info = await _run(["redis-cli", "info", "keyspace"])
        lines.append("REDIS")
        if rc == 0 and redis_info:
            for line in redis_info.splitlines():
                if line.startswith("db"):
                    lines.append(f"  {line}")
        else:
            lines.append("  unreachable")
        lines.append("")

        # ScyllaDB
        rc, scylla = await _run(["nodetool", "status"], timeout=10)
        lines.append("SCYLLADB")
        if rc == 0 and scylla:
            for line in scylla.splitlines()[:8]:
                lines.append(f"  {line}")
        else:
            lines.append("  not running or not installed")
        lines.append("")

        return SkillResult(success=True, output="\n".join(lines), data=data)

    # ------------------------------------------------------------------
    # docker — container status
    # ------------------------------------------------------------------
    async def _docker(self, app_filter, lines_count) -> SkillResult:
        lines = ["DOCKER CONTAINERS", "=" * 55, ""]

        rc, out = await _run(
            ["docker", "ps", "-a", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
            timeout=10,
        )

        if rc != 0:
            return SkillResult(success=False, output="Docker not available or not running", data={})

        containers = []
        for line in out.splitlines():
            if app_filter and app_filter.lower() not in line.lower():
                continue
            lines.append(f"  {line}")
            containers.append(line)

        # Docker disk usage
        rc2, disk = await _run(["docker", "system", "df"], timeout=10)
        if rc2 == 0:
            lines.append("")
            lines.append("DISK USAGE:")
            for line in disk.splitlines():
                lines.append(f"  {line}")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            data={"container_count": len(containers) - 1},  # minus header
        )

    # ------------------------------------------------------------------
    # services — systemd, PM2, supervisor
    # ------------------------------------------------------------------
    async def _services(self, app_filter, lines_count) -> SkillResult:
        lines = ["SERVICE STATUS", "=" * 55, ""]
        data = {}

        # Supervisor
        rc, sup_out = await _run(["supervisorctl", "status"])
        lines.append("SUPERVISOR WORKERS:")
        if rc == 0 and sup_out:
            for line in sup_out.splitlines():
                if app_filter and app_filter.lower() not in line.lower():
                    continue
                lines.append(f"  {line}")
        else:
            lines.append("  no workers or not running")
        lines.append("")

        # PM2
        rc, pm2_out = await _run(["pm2", "jlist"])
        lines.append("PM2 APPLICATIONS:")
        pm2_apps = []
        if rc == 0 and pm2_out:
            try:
                pm2_apps = json.loads(pm2_out)
            except Exception:
                pass

        if pm2_apps:
            for app in pm2_apps:
                name = app.get("name", "?")
                status = app.get("pm2_env", {}).get("status", "?")
                memory = app.get("monit", {}).get("memory", 0)
                cpu = app.get("monit", {}).get("cpu", 0)
                mem_mb = memory / (1024 * 1024) if memory else 0

                if app_filter and app_filter.lower() not in name.lower():
                    continue

                lines.append(f"  {name:30s}  {status:10s}  CPU: {cpu}%  MEM: {mem_mb:.0f}MB")
            data["pm2"] = [{"name": a.get("name"), "status": a.get("pm2_env", {}).get("status")} for a in pm2_apps]
        else:
            lines.append("  no apps or PM2 not running")
        lines.append("")

        # Key systemd services
        lines.append("SYSTEMD SERVICES:")
        key_services = [
            "nginx", "mysql", "postgresql", "redis-server",
            "docker", "supervisor", "antigravity-web",
            "scylla-server", "php8.4-fpm", "php8.3-fpm",
        ]
        for svc in key_services:
            rc, out = await _run(["systemctl", "is-active", svc])
            status = out.strip() if rc == 0 else "inactive"
            if status == "active":
                lines.append(f"  {svc:25s}  ACTIVE")
            elif status in ("inactive", "dead"):
                pass  # skip inactive ones to reduce noise
            else:
                lines.append(f"  {svc:25s}  {status.upper()}")

        return SkillResult(success=True, output="\n".join(lines), data=data)

    # ------------------------------------------------------------------
    # ssl — certificate monitoring
    # ------------------------------------------------------------------
    async def _ssl(self, app_filter, lines_count) -> SkillResult:
        lines = ["SSL CERTIFICATE STATUS", "=" * 55, ""]
        sites = _discover_all_sites()
        if app_filter:
            sites = [s for s in sites if app_filter in s["domain"]]

        certs = []
        expired = []
        expiring_soon = []

        for s in sites:
            domain = s["domain"]
            cert = f"/etc/letsencrypt/live/{domain}/cert.pem"
            if not os.path.exists(cert):
                # Try without subdomain variations
                continue

            rc, out = await _run(
                ["openssl", "x509", "-in", cert, "-noout", "-enddate"]
            )
            if rc == 0 and out.startswith("notAfter="):
                try:
                    expiry = datetime.strptime(
                        out.strip().split("=", 1)[1], "%b %d %H:%M:%S %Y %Z"
                    )
                    days_left = (expiry - datetime.now(timezone.utc).replace(tzinfo=None)).days

                    status = "OK"
                    if days_left < 0:
                        status = f"EXPIRED ({abs(days_left)}d ago)"
                        expired.append(domain)
                    elif days_left < 7:
                        status = f"CRITICAL ({days_left}d left)"
                        expiring_soon.append(domain)
                    elif days_left < 30:
                        status = f"WARNING ({days_left}d left)"
                        expiring_soon.append(domain)

                    certs.append({"domain": domain, "expires": out.strip(), "days_left": days_left, "status": status})
                    lines.append(f"  {domain:40s}  {status}")
                except Exception:
                    lines.append(f"  {domain:40s}  PARSE ERROR")

        lines.append("")
        lines.append(f"Total certs checked: {len(certs)}")
        if expired:
            lines.append(f"EXPIRED: {', '.join(expired)}")
        if expiring_soon:
            lines.append(f"EXPIRING SOON: {', '.join(expiring_soon)}")

        if not expired and not expiring_soon:
            lines.append("All certificates valid.")

        return SkillResult(
            success=len(expired) == 0,
            output="\n".join(lines),
            data={"certs": certs, "expired": expired, "expiring_soon": expiring_soon},
        )

    # ------------------------------------------------------------------
    # resources — detailed system resources
    # ------------------------------------------------------------------
    async def _resources(self, app_filter, lines_count) -> SkillResult:
        lines = ["SYSTEM RESOURCES", "=" * 55, ""]

        results = await asyncio.gather(
            _run(["uptime"]),
            _run(["free", "-h"]),
            _run_shell("df -h | head -20"),
            _run(["nproc"]),
            _run(["cat", "/proc/loadavg"]),
            _run_shell("top -bn1 | head -5"),
        )

        labels = ["UPTIME", "MEMORY", "DISK USAGE", "CPU CORES", "LOAD AVERAGE", "TOP PROCESSES"]
        for label, (rc, out) in zip(labels, results):
            lines.append(f"{label}:")
            if rc == 0:
                for line in out.splitlines():
                    lines.append(f"  {line}")
            else:
                lines.append("  unavailable")
            lines.append("")

        # Top memory consumers
        rc, top_mem = await _run_shell("ps aux --sort=-%mem | head -11")
        if rc == 0:
            lines.append("TOP MEMORY CONSUMERS:")
            for line in top_mem.splitlines():
                lines.append(f"  {line}")

        return SkillResult(success=True, output="\n".join(lines), data={})

    # ------------------------------------------------------------------
    # nginx — nginx status and config check
    # ------------------------------------------------------------------
    async def _nginx(self, app_filter, lines_count) -> SkillResult:
        lines = ["NGINX STATUS", "=" * 55, ""]

        rc, test = await _run(["nginx", "-t"])
        lines.append(f"Config test: {'OK' if rc == 0 else 'FAILED'}")
        if rc != 0:
            lines.append(f"  {test}")
        lines.append("")

        sites = _discover_all_sites()
        enabled = [s for s in sites if s["enabled"]]
        disabled = [s for s in sites if not s["enabled"]]

        lines.append(f"ENABLED SITES ({len(enabled)}):")
        for s in enabled:
            lines.append(f"  {s['domain']:40s}  [{s['app_type']}]")

        lines.append(f"\nDISABLED SITES ({len(disabled)}):")
        for s in disabled:
            lines.append(f"  {s['domain']:40s}  [{s['app_type']}]")

        # Connection stats
        rc, conns = await _run_shell("ss -s 2>/dev/null | head -5")
        if rc == 0:
            lines.append("\nCONNECTION STATS:")
            for line in conns.splitlines():
                lines.append(f"  {line}")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            data={"enabled": len(enabled), "disabled": len(disabled)},
        )

    # ------------------------------------------------------------------
    # logs — tail logs for any app
    # ------------------------------------------------------------------
    async def _logs(self, app_filter, lines_count) -> SkillResult:
        if not app_filter:
            # Show available log sources
            lines = ["AVAILABLE LOG SOURCES", "=" * 40, ""]
            lines.append("Specify an app name to view its logs. Examples:")
            lines.append("  nginx       — /var/log/nginx/error.log")
            lines.append("  mysql       — /var/log/mysql/error.log")
            lines.append("  docker      — docker logs")
            lines.append("  pm2         — PM2 logs")
            lines.append("  supervisor  — supervisor logs")
            lines.append("  antigravity — Sanaa AI backend logs")
            lines.append("  {domain}    — Laravel/app logs")
            return SkillResult(success=True, output="\n".join(lines), data={})

        lines = [f"LOGS: {app_filter} (last {lines_count} lines)", "=" * 55, ""]

        log_sources = {
            "nginx": "/var/log/nginx/error.log",
            "mysql": "/var/log/mysql/error.log",
            "syslog": "/var/log/syslog",
            "auth": "/var/log/auth.log",
            "antigravity": "/opt/antigravity/core/logs/app.log",
        }

        if app_filter in log_sources:
            log_path = log_sources[app_filter]
            if os.path.isfile(log_path):
                rc, out = await _run(["tail", "-n", str(lines_count), log_path], timeout=10)
                lines.append(out if rc == 0 else "Failed to read log")
            else:
                lines.append(f"Log file not found: {log_path}")
        elif app_filter == "docker":
            # Fetch the first three running container IDs, then log each.
            rc, ids_out = await _run_shell("docker ps -q | head -3", timeout=10)
            docker_lines: list[str] = []
            if rc == 0 and ids_out:
                for container_id in ids_out.splitlines():
                    container_id = container_id.strip()
                    if not container_id:
                        continue
                    rc2, out2 = await _run(
                        ["docker", "logs", "--tail", str(lines_count), container_id],
                        timeout=15,
                    )
                    if rc2 == 0:
                        docker_lines.append(out2)
            lines.append("\n".join(docker_lines) if docker_lines else "No Docker logs")
        elif app_filter == "pm2":
            rc, out = await _run(["pm2", "logs", "--nostream", "--lines", str(lines_count)], timeout=10)
            lines.append(out if rc == 0 else "No PM2 logs")
        elif app_filter == "supervisor":
            rc, out = await _run(["tail", "-n", str(lines_count), "/var/log/supervisor/supervisord.log"], timeout=10)
            lines.append(out if rc == 0 else "No supervisor logs")
        else:
            # Try as a domain — find its Laravel log
            sites = _discover_all_sites()
            site = next((s for s in sites if app_filter in s["domain"]), None)
            if site and site["root"]:
                # Try Laravel storage/logs
                root = site["root"]
                if "/public" in root:
                    app_base = root.rsplit("/public", 1)[0]
                else:
                    app_base = root
                log_path = f"{app_base}/storage/logs/laravel.log"
                if os.path.isfile(log_path):
                    rc, out = await _run(["tail", "-n", str(lines_count), log_path], timeout=10)
                    lines.append(out if rc == 0 else "Failed to read log")
                else:
                    lines.append(f"No log at {log_path}")
            else:
                lines.append(f"Unknown app: {app_filter}")

        return SkillResult(success=True, output="\n".join(lines), data={})
