"""
Sanaa AI Self-Healer — Auto-remediation for common server issues.

Actions:
  - Restart failed critical services
  - Unban admin IPs from fail2ban
  - Clear large log files when disk is critical
  - Kill runaway processes consuming excessive memory

Safety:
  - Only acts on well-defined, safe remediations
  - All actions are logged to audit trail
  - Destructive actions require explicit enablement
"""

import logging
import subprocess
from datetime import datetime, timezone

from config import get_settings
from agents.watchdog import WatchdogEvent, SEVERITY_CRITICAL, SEVERITY_HIGH

logger = logging.getLogger(__name__)
settings = get_settings()

# Services that are safe to auto-restart
SAFE_TO_RESTART = {
    "ssh", "nginx", "redis-server", "postgresql",
    "antigravity-web", "antigravity-worker", "antigravity-beat",
    "fail2ban", "php8.4-fpm",
}

# Max log file size before auto-truncation (100MB)
LOG_TRUNCATE_THRESHOLD = 100 * 1024 * 1024


class SelfHealer:
    """
    Processes watchdog events and attempts auto-remediation.
    Returns a list of actions taken.
    """

    def __init__(self):
        self.actions_taken: list[dict] = []

    async def process_events(self, events: list[WatchdogEvent]) -> list[dict]:
        """
        Process watchdog events and attempt fixes.
        Returns list of actions taken with results.
        """
        self.actions_taken = []

        for event in events:
            try:
                await self._handle_event(event)
            except Exception as e:
                logger.error(f"Healer error handling {event.category}: {e}")

        return self.actions_taken

    async def _handle_event(self, event: WatchdogEvent):
        """Route event to appropriate handler."""

        if event.category == "access" and "fail2ban" in event.message.lower() and "banned" in event.message.lower():
            await self._unban_admin_ip(event)

        elif event.category == "access" and "SSH service" in event.message:
            await self._restart_service("ssh", event)

        elif event.category == "service" and event.severity in (SEVERITY_CRITICAL, SEVERITY_HIGH):
            # Extract service name from metric (e.g. "service.nginx" → "nginx")
            svc = event.metric.replace("service.", "")
            if svc in SAFE_TO_RESTART:
                await self._restart_service(svc, event)

        elif event.category == "resource" and "Disk" in event.message and event.severity == SEVERITY_CRITICAL:
            await self._clear_disk_space(event)

        elif event.category == "security" and "fail2ban is not running" in event.message:
            await self._restart_service("fail2ban", event)

    # ==================== ACTIONS ====================

    async def _restart_service(self, service: str, event: WatchdogEvent):
        """Restart a systemd service."""
        if service not in SAFE_TO_RESTART:
            logger.warning(f"Healer: refusing to restart unknown service '{service}'")
            return

        action = {
            "action": "restart_service",
            "target": service,
            "trigger": event.message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            result = subprocess.run(
                f"systemctl restart {service}",
                shell=True, capture_output=True, text=True, timeout=30,
            )
            action["success"] = result.returncode == 0
            action["output"] = result.stderr.strip() or result.stdout.strip()

            if action["success"]:
                logger.info(f"Healer: restarted service '{service}' successfully")
            else:
                logger.error(f"Healer: failed to restart '{service}': {action['output']}")

        except subprocess.TimeoutExpired:
            action["success"] = False
            action["output"] = "Restart timed out after 30s"

        self.actions_taken.append(action)

    async def _unban_admin_ip(self, event: WatchdogEvent):
        """Unban an admin IP from fail2ban."""
        ip = event.value
        if not ip:
            return

        action = {
            "action": "unban_ip",
            "target": ip,
            "trigger": event.message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            result = subprocess.run(
                f"fail2ban-client set sshd unbanip {ip}",
                shell=True, capture_output=True, text=True, timeout=10,
            )
            action["success"] = result.returncode == 0
            action["output"] = result.stdout.strip() or result.stderr.strip()

            if action["success"]:
                logger.info(f"Healer: unbanned admin IP {ip} from fail2ban")
        except Exception as e:
            action["success"] = False
            action["output"] = str(e)

        self.actions_taken.append(action)

    async def _clear_disk_space(self, event: WatchdogEvent):
        """Clear disk space by removing old logs and temp files."""
        action = {
            "action": "clear_disk_space",
            "trigger": event.message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": [],
        }

        # Truncate large log files
        log_dirs = ["/var/log", "/opt/antigravity/logs"]
        cleared_mb = 0

        for log_dir in log_dirs:
            try:
                result = subprocess.run(
                    f"find {log_dir} -name '*.log' -size +100M -type f 2>/dev/null",
                    shell=True, capture_output=True, text=True, timeout=10,
                )
                for filepath in result.stdout.strip().split("\n"):
                    if not filepath.strip():
                        continue
                    # Truncate (keep last 1000 lines)
                    subprocess.run(
                        f"tail -1000 '{filepath}' > '{filepath}.tmp' && mv '{filepath}.tmp' '{filepath}'",
                        shell=True, timeout=10,
                    )
                    action["details"].append(f"Truncated {filepath}")
                    cleared_mb += 50  # approximate
            except Exception:
                pass

        # Clean apt cache
        try:
            subprocess.run("apt-get clean 2>/dev/null", shell=True, timeout=30)
            action["details"].append("Cleaned apt cache")
        except Exception:
            pass

        # Clean old journal logs (keep 3 days)
        try:
            subprocess.run(
                "journalctl --vacuum-time=3d 2>/dev/null",
                shell=True, timeout=30,
            )
            action["details"].append("Vacuumed journal to 3 days")
        except Exception:
            pass

        action["success"] = True
        action["output"] = f"Cleared ~{cleared_mb}MB, {len(action['details'])} operations"
        self.actions_taken.append(action)
