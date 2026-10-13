import asyncio
import logging
from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

CELERY_SERVICES = ["antigravity-worker.service", "antigravity-beat.service"]
SYSLOG_PATH = "/var/log/syslog"


async def _run(args: list[str], timeout: int = 15) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, b"", b"timeout"
    return proc.returncode or 0, stdout, stderr


class SystemServicesSkill(BaseSkill):
    name = "system_services"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")

        if action == "service_status":
            service = args.get("service_name")
            if not service:
                return SkillResult(success=False, error="service_name is required for service_status")
            return await self._get_service_status(service)

        elif action == "celery_status":
            return await self._get_celery_status()

        elif action == "recent_tasks":
            return await self._get_recent_tasks()

        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _get_service_status(self, service: str) -> SkillResult:
        try:
            rc, stdout, stderr = await _run(["systemctl", "status", service], timeout=15)
            output = (stdout + stderr).decode(errors="replace")[:4000]
            return SkillResult(success=rc == 0, output=output)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _get_celery_status(self) -> SkillResult:
        try:
            # Check processes using an argument list and filter in Python.
            rc, stdout, _ = await _run(["ps", "aux"], timeout=10)
            processes = [
                line
                for line in stdout.decode(errors="replace").splitlines()
                if "celery" in line.lower() and "grep" not in line.lower()
            ]
            output = "Celery Processes:\n" + "\n".join(processes)

            # Check services
            for svc in CELERY_SERVICES:
                rc, s_stdout, _ = await _run(["systemctl", "is-active", svc], timeout=10)
                output += f"\n{svc}: {s_stdout.decode().strip()}"

            return SkillResult(success=True, output=output)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def _get_recent_tasks(self) -> SkillResult:
        try:
            # Read syslog directly and filter for Celery task markers.
            try:
                with open(SYSLOG_PATH, "r", errors="replace") as fh:
                    lines = fh.readlines()
            except FileNotFoundError:
                return SkillResult(success=True, output="No syslog found.")
            except OSError as e:
                return SkillResult(success=False, error=f"Could not read syslog: {e}")

            matching = [line.rstrip() for line in lines if "Task core.tasks" in line]
            output = "\n".join(matching[-20:]) if matching else "No recent tasks found in syslog."
            return SkillResult(success=True, output=output)
        except Exception as e:
            return SkillResult(success=False, error=str(e))
