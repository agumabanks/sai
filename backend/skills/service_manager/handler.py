"""
Service Manager Skill — start/stop/restart services across all process managers.

Handles systemd units, PM2 apps, supervisor workers, Docker containers,
Laravel artisan commands, SSL certificate renewal, and nginx operations.
"""

import asyncio
import logging
import os
import re
import shlex

from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

NGINX_AVAILABLE = "/etc/nginx/sites-available"
NGINX_ENABLED = "/etc/nginx/sites-enabled"


async def _run(args: list[str], timeout: int = 30, cwd: str | None = None) -> tuple[int, str]:
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
    err = stderr.decode().strip()
    return proc.returncode or 0, out if out else err


def _validate_target(target: str, manager: str) -> str | None:
    """Return an error message if the target is unsafe, otherwise None."""
    if not target or not isinstance(target, str):
        return "target must be a non-empty string"
    if manager == "laravel":
        if not re.match(r"^[a-z0-9][a-z0-9\-]*\.[a-z0-9\-.]+$", target):
            return f"invalid domain target: {target}"
        return None
    if not re.match(r"^[A-Za-z0-9_\-:.]+$", target):
        return f"invalid target identifier: {target}"
    return None


def _find_app_root(domain: str) -> str | None:
    """Find the application root directory for a domain via nginx config."""
    conf = f"{NGINX_AVAILABLE}/{domain}.conf"
    if not os.path.isfile(conf):
        return None
    try:
        with open(conf) as f:
            content = f.read()
        match = re.search(r'root\s+([^;]+);', content)
        if match:
            root = match.group(1).strip()
            # Go up from /public to app root
            if root.endswith("/public"):
                return root[:-7]
            return root
    except Exception:
        pass
    return None


def _detect_manager(target: str) -> str:
    """Auto-detect which process manager handles this target."""
    # Known systemd services
    systemd_services = {
        "nginx", "mysql", "mysqld", "postgresql", "postgres",
        "redis", "redis-server", "docker", "supervisor", "supervisord",
        "scylla-server", "php8.4-fpm", "php8.3-fpm", "php8.2-fpm",
        "antigravity-web", "cron", "ssh", "fail2ban", "ufw",
    }

    if target in systemd_services or target.startswith("php"):
        return "systemd"

    # Supervisor pattern: *-worker
    if "worker" in target.lower():
        return "supervisor"

    # Docker pattern: mailcow*, container names
    if "mailcow" in target.lower() or "container" in target.lower():
        return "docker"

    # Domain patterns suggest Laravel
    if ".sanaa." in target or ".co" in target or ".ug" in target:
        return "laravel"

    return "systemd"  # default


class ServiceManagerSkill(BaseSkill):
    name = "service_manager"
    description = (
        "Manage server services — start/stop/restart systemd units, PM2 apps, "
        "supervisor workers, Docker containers, SSL renewal, and nginx."
    )
    version = "1.0.0"
    permissions = ["shell"]
    requires_approval = False  # Dashboard IS the approval; manifest has true for LLM
    timeout = 120
    tags = ["management", "infrastructure", "services", "operations"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action", "status")
        target = args.get("target", "")
        manager = args.get("manager") or _detect_manager(target)

        if not target:
            return SkillResult(success=False, error="Target service/app is required")

        if manager not in {"systemd", "supervisor", "pm2", "docker", "laravel"}:
            return SkillResult(success=False, error=f"Unknown manager: {manager}")

        err = _validate_target(target, manager)
        if err:
            return SkillResult(success=False, error=err)

        dispatch = {
            "restart": self._restart,
            "stop": self._stop,
            "start": self._start,
            "status": self._status,
            "renew_ssl": self._renew_ssl,
            "reload_nginx": self._reload_nginx,
            "deploy_app": self._deploy_app,
            "clear_cache": self._clear_cache,
        }

        handler = dispatch.get(action)
        if not handler:
            return SkillResult(success=False, error=f"Unknown action: {action}")

        return await handler(target, manager)

    # ------------------------------------------------------------------
    # Service lifecycle: start, stop, restart
    # ------------------------------------------------------------------
    async def _restart(self, target: str, manager: str) -> SkillResult:
        args, cwd, desc = self._build_cmd("restart", target, manager)
        rc, out = await _run(args, cwd=cwd, timeout=30)

        # Laravel restart also clears the cache.
        if manager == "laravel" and cwd:
            rc2, out2 = await _run(["php", f"{cwd}/artisan", "cache:clear"], cwd=cwd, timeout=30)
            if rc == 0:
                rc = rc2
            out += "\n" + out2

        # Verify
        status_args, _, _ = self._build_cmd("status", target, manager)
        _, status_out = await _run(status_args, cwd=cwd, timeout=10)

        output = f"RESTART: {desc}\n{'=' * 40}\n\nCommand: {shlex.join(args)}\nResult: {'OK' if rc == 0 else 'FAILED'}\n{out}\n\nCurrent status:\n{status_out}"
        return SkillResult(success=rc == 0, output=output, data={"action": "restart", "target": target})

    async def _stop(self, target: str, manager: str) -> SkillResult:
        args, cwd, desc = self._build_cmd("stop", target, manager)
        rc, out = await _run(args, cwd=cwd, timeout=30)
        output = f"STOP: {desc}\n{'=' * 40}\n\nResult: {'OK' if rc == 0 else 'FAILED'}\n{out}"
        return SkillResult(success=rc == 0, output=output, data={"action": "stop", "target": target})

    async def _start(self, target: str, manager: str) -> SkillResult:
        args, cwd, desc = self._build_cmd("start", target, manager)
        rc, out = await _run(args, cwd=cwd, timeout=30)
        output = f"START: {desc}\n{'=' * 40}\n\nResult: {'OK' if rc == 0 else 'FAILED'}\n{out}"
        return SkillResult(success=rc == 0, output=output, data={"action": "start", "target": target})

    async def _status(self, target: str, manager: str) -> SkillResult:
        args, cwd, desc = self._build_cmd("status", target, manager)
        rc, out = await _run(args, cwd=cwd, timeout=10)
        output = f"STATUS: {desc}\n{'=' * 40}\n\n{out}"
        return SkillResult(success=True, output=output, data={"action": "status", "target": target})

    def _build_cmd(self, action: str, target: str, manager: str) -> tuple[list[str], str | None, str]:
        """Build the appropriate argument list for the process manager.

        Returns (args, cwd, description).  cwd may be None when the command
        does not need to run inside an application directory.
        """
        if manager == "systemd":
            return ["systemctl", action, target], None, f"{target} via systemd"
        elif manager == "supervisor":
            sup_action = action if action != "status" else "status"
            return ["supervisorctl", sup_action, target], None, f"{target} via supervisor"
        elif manager == "pm2":
            return ["pm2", action, target], None, f"{target} via PM2"
        elif manager == "docker":
            return ["docker", action, target], None, f"{target} via Docker"
        elif manager == "laravel":
            app_root = _find_app_root(target)
            if app_root and action == "restart":
                return ["php", f"{app_root}/artisan", "queue:restart"], app_root, f"{target} Laravel restart"
            elif app_root and action == "status":
                return [
                    "curl", "-sL", "-o", "/dev/null", "-w", "%{http_code}",
                    f"https://{target}/",
                ], None, f"{target} HTTP check"
            return ["echo", f"No app root found for {target}"], None, target
        return ["echo", f"Unknown manager: {manager}"], None, manager

    # ------------------------------------------------------------------
    # SSL certificate renewal
    # ------------------------------------------------------------------
    async def _renew_ssl(self, target: str, manager: str) -> SkillResult:
        lines = [f"SSL RENEWAL: {target}", "=" * 40, ""]

        if target == "all":
            rc, out = await _run(["certbot", "renew", "--non-interactive"], timeout=120)
            lines.append(out if rc == 0 else f"Failed: {out}")
        else:
            # Check current cert
            cert = f"/etc/letsencrypt/live/{target}/cert.pem"
            if os.path.exists(cert):
                rc, expiry = await _run(
                    ["openssl", "x509", "-in", cert, "-noout", "-enddate"]
                )
                if rc == 0 and expiry.startswith("notAfter="):
                    lines.append(f"Current expiry: {expiry.split('=', 1)[1]}")

            # Renew specific cert
            rc, out = await _run(
                ["certbot", "certonly", "--nginx", "-d", target, "--non-interactive"],
                timeout=60,
            )
            lines.append(f"\nRenewal: {'OK' if rc == 0 else 'FAILED'}")
            lines.append(out)

            # Reload nginx to pick up new cert
            if rc == 0:
                await _run(["systemctl", "reload", "nginx"])
                lines.append("\nnginx reloaded.")

        return SkillResult(success=True, output="\n".join(lines), data={"target": target})

    # ------------------------------------------------------------------
    # Nginx reload
    # ------------------------------------------------------------------
    async def _reload_nginx(self, target: str, manager: str) -> SkillResult:
        lines = ["NGINX RELOAD", "=" * 40, ""]

        # Test config first
        rc, test = await _run(["nginx", "-t"])
        lines.append(f"Config test: {'PASSED' if rc == 0 else 'FAILED'}")
        lines.append(test)

        if rc != 0:
            return SkillResult(success=False, output="\n".join(lines), data={})

        rc2, out = await _run(["systemctl", "reload", "nginx"])
        lines.append(f"\nReload: {'OK' if rc2 == 0 else 'FAILED'}")

        return SkillResult(success=rc2 == 0, output="\n".join(lines), data={})

    # ------------------------------------------------------------------
    # Deploy / update an app
    # ------------------------------------------------------------------
    async def _deploy_app(self, target: str, manager: str) -> SkillResult:
        app_root = _find_app_root(target)
        if not app_root:
            return SkillResult(success=False, error=f"Cannot find app root for {target}")

        lines = [f"DEPLOY: {target}", "=" * 40, ""]

        # Detect app type
        is_laravel = os.path.isfile(f"{app_root}/artisan")
        is_node = os.path.isfile(f"{app_root}/package.json")

        if is_laravel:
            cmds = [
                ("Pulling latest code", ["git", "pull"]),
                ("Composer install", ["composer", "install", "--no-dev", "--optimize-autoloader"]),
                ("Running migrations", ["php", "artisan", "migrate", "--force"]),
                ("Clearing caches", ["php", "artisan", "optimize:clear"]),
                ("Building caches", ["php", "artisan", "optimize"]),
                ("Restarting queue", ["php", "artisan", "queue:restart"]),
            ]
        elif is_node:
            cmds = [
                ("Pulling latest code", ["git", "pull"]),
                ("Installing dependencies", ["npm", "install", "--production"]),
                ("Building", ["npm", "run", "build"]),
            ]
        else:
            return SkillResult(success=False, error=f"Unknown app type at {app_root}")

        success = True
        for desc, args in cmds:
            lines.append(f"\n> {desc}...")
            rc, out = await _run(args, cwd=app_root, timeout=120)
            if rc != 0:
                lines.append(f"  FAILED: {out[:200]}")
                success = False
                break
            else:
                lines.append("  OK")

        return SkillResult(success=success, output="\n".join(lines), data={"target": target})

    # ------------------------------------------------------------------
    # Clear cache for a Laravel app
    # ------------------------------------------------------------------
    async def _clear_cache(self, target: str, manager: str) -> SkillResult:
        app_root = _find_app_root(target)
        if not app_root:
            return SkillResult(success=False, error=f"Cannot find app root for {target}")

        lines = [f"CLEAR CACHE: {target}", "=" * 40, ""]

        cmds = [
            ["php", "artisan", "cache:clear"],
            ["php", "artisan", "config:clear"],
            ["php", "artisan", "route:clear"],
            ["php", "artisan", "view:clear"],
            ["php", "artisan", "optimize"],
        ]

        for args in cmds:
            rc, out = await _run(args, cwd=app_root, timeout=15)
            lines.append(f"  {shlex.join(args)}: {'OK' if rc == 0 else out[:80]}")

        return SkillResult(success=True, output="\n".join(lines), data={"target": target})
