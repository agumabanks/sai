"""Tmux Runner — spawn, monitor, rename, wait on, and kill long-running background tasks."""
import subprocess
import asyncio
import logging
from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)


class TmuxRunnerSkill(BaseSkill):
    name = "tmux_runner"

    def _run(self, cmd: list[str], timeout: int = 10) -> tuple[str, int]:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.returncode

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")

        if action == "start":
            return self._start(args)
        elif action == "check":
            return self._check(args)
        elif action == "list":
            return self._list()
        elif action == "kill":
            return self._kill(args)
        elif action == "rename":
            return self._rename(args)
        elif action == "wait":
            return await self._wait(args)

        return SkillResult(success=False, error=f"Unknown action: {action}")

    # ── start ──────────────────────────────────────────────────────────────
    def _start(self, args: dict) -> SkillResult:
        session_name = args.get("session_name", "sanaa-bg")
        command = args.get("command")
        if not command:
            return SkillResult(success=False, error="'command' is required.")
        try:
            # Kill existing session with the same name silently (idempotent)
            subprocess.run(["tmux", "kill-session", "-t", session_name],
                           capture_output=True)
            out, rc = self._run(["tmux", "new-session", "-d", "-s", session_name])
            if rc != 0:
                return SkillResult(success=False, error=f"Failed to create tmux session: {out}")
            self._run(["tmux", "send-keys", "-t", session_name, command, "Enter"])
            return SkillResult(
                success=True,
                output=(
                    f"Background task started in tmux session '{session_name}'.\n"
                    f"Command: {command}\n"
                    f"Check status: use action='check' session_name='{session_name}'\n"
                    f"Attach locally: tmux attach -t {session_name}"
                ),
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── check ──────────────────────────────────────────────────────────────
    def _check(self, args: dict) -> SkillResult:
        session_name = args.get("session_name", "sanaa-bg")
        lines = int(args.get("lines", 50))
        try:
            out, rc = self._run([
                "tmux", "capture-pane", "-p", "-J", "-t", session_name, "-S", f"-{lines}"
            ])
            if rc != 0:
                return SkillResult(success=False,
                                   error=f"Session '{session_name}' not found or tmux not running.")
            return SkillResult(success=True,
                               output=f"Last {lines} lines from '{session_name}':\n{out}")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── list ───────────────────────────────────────────────────────────────
    def _list(self) -> SkillResult:
        try:
            out, _ = self._run(["tmux", "list-sessions"])
            if not out:
                return SkillResult(success=True, output="No active tmux sessions.")
            return SkillResult(success=True, output=out)
        except Exception:
            return SkillResult(success=True, output="No active tmux sessions (tmux server not running).")

    # ── kill ───────────────────────────────────────────────────────────────
    def _kill(self, args: dict) -> SkillResult:
        session_name = args.get("session_name")
        if not session_name:
            return SkillResult(success=False, error="'session_name' is required.")
        try:
            out, rc = self._run(["tmux", "kill-session", "-t", session_name])
            if rc != 0:
                return SkillResult(success=False, error=f"Session '{session_name}' not found.")
            return SkillResult(success=True, output=f"Killed tmux session '{session_name}'.")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── rename ─────────────────────────────────────────────────────────────
    def _rename(self, args: dict) -> SkillResult:
        session_name = args.get("session_name")
        new_name = args.get("new_name")
        if not session_name or not new_name:
            return SkillResult(success=False, error="'session_name' and 'new_name' are required.")
        try:
            out, rc = self._run(["tmux", "rename-session", "-t", session_name, new_name])
            if rc != 0:
                return SkillResult(success=False, error=f"Rename failed: {out}")
            return SkillResult(success=True,
                               output=f"Renamed tmux session '{session_name}' → '{new_name}'.")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── wait (async poll until command exits) ──────────────────────────────
    async def _wait(self, args: dict) -> SkillResult:
        """Poll a tmux session until it no longer exists (process finished) or timeout."""
        session_name = args.get("session_name")
        timeout_s = int(args.get("timeout", 300))
        poll_interval = int(args.get("poll_interval", 5))
        if not session_name:
            return SkillResult(success=False, error="'session_name' is required.")

        elapsed = 0
        while elapsed < timeout_s:
            _, rc = self._run(["tmux", "has-session", "-t", session_name])
            if rc != 0:
                return SkillResult(
                    success=True,
                    output=f"Session '{session_name}' finished after ~{elapsed}s.",
                    data={"elapsed_s": elapsed},
                )
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        # Return last output even if still running
        last_out, _ = self._run([
            "tmux", "capture-pane", "-p", "-J", "-t", session_name, "-S", "-20"
        ])
        return SkillResult(
            success=False,
            output=f"Session '{session_name}' still running after {timeout_s}s.\nLast output:\n{last_out}",
            error=f"Timed out waiting for session '{session_name}'.",
        )
