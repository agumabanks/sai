import asyncio
import re
from typing import Dict, Any
from core.skills.base import BaseSkill, SkillContext, SkillResult

class MailcowAgent(BaseSkill):
    name = "mailcow_agent"

    async def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        action = params.get("action", "container_health")

        if action == "queue_depth":
            return await self._queue_depth()
        elif action == "container_health":
            return await self._container_health()
        elif action == "check_storage":
            return await self._check_storage()

        return SkillResult(success=False, error=f"Unknown action: {action}")

    async def _run(self, args: list[str], timeout: int = 20) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return -1, "timeout"
        return proc.returncode or 0, stdout.decode().strip() or stderr.decode().strip()

    async def _find_container(self, name_fragment: str) -> str | None:
        """Return the container ID/name for the most recently created container matching name_fragment."""
        rc, out = await self._run(
            ["docker", "ps", "-qf", f"name={name_fragment}", "-l"],
            timeout=10,
        )
        if rc != 0 or not out:
            return None
        container_id = out.splitlines()[0].strip()
        # Basic container ID/name validation: allow alphanumerics, underscores, hyphens.
        if not re.match(r"^[A-Za-z0-9_\-]+$", container_id):
            return None
        return container_id

    async def _queue_depth(self) -> SkillResult:
        container = await self._find_container("postfix-mailcow")
        if not container:
            return SkillResult(success=False, error="Could not find or query postfix container.")

        rc, out = await self._run(["docker", "exec", container, "mailq"], timeout=15)
        if rc != 0 and "No such container" in out:
            return SkillResult(success=False, error="Could not find or query postfix container.")

        if "Mail queue is empty" in out:
            return SkillResult(success=True, output="✅ Mail queue is empty.")

        return SkillResult(success=True, output=f"✉️ Active Mail Queue:\n\n{out}")

    async def _container_health(self) -> SkillResult:
        rc, out = await self._run(
            ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"],
            timeout=15,
        )
        if rc != 0:
            return SkillResult(success=False, error="Docker not available or not running.")

        lines = [line for line in out.splitlines() if "mailcow" in line.lower()]
        if not lines:
            return SkillResult(success=False, error="Mailcow stack may not be running.")

        down = [line for line in lines if "Exited" in line or "Restarting" in line]
        if down:
            return SkillResult(
                success=False,
                output="🚨 Mailcow Stack Issues Detected:\n\n" + "\n".join(down),
            )

        return SkillResult(
            success=True,
            output="✅ All Mailcow components are running healthily.\n\n" + "\n".join(lines),
        )

    async def _check_storage(self) -> SkillResult:
        container = await self._find_container("dovecot-mailcow")
        if not container:
            return SkillResult(success=False, error="Could not find dovecot container.")

        rc, out = await self._run(
            ["docker", "exec", container, "df", "-h", "/var/vmail"],
            timeout=15,
        )
        return SkillResult(success=rc == 0, output=f"💾 Storage Status (vmail):\n\n{out}")

# Register the entry point
handler = MailcowAgent
