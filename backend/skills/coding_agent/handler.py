"""Coding Agent — read, write, patch, search, and safely run commands."""
import os
import asyncio
import logging
import shlex
from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

# Sandboxed directories the agent is allowed to touch
ALLOWED_ROOTS = [
    "/var/www/ai.sanaa.co/backend",
    "/var/www/ai.sanaa.co/frontend",
    "/tmp/sanaa_scratch",
]

# Safe read-only programs allowed in 'run' mode (first token of the command).
# The command is parsed with shlex and executed via create_subprocess_exec.
SAFE_PROGRAMS = {"ls", "cat", "head", "tail", "wc", "grep", "find", "du", "df",
                 "python3", "pip", "ruff", "git", "pwd", "whoami", "echo"}
DANGEROUS_TOKENS = ["rm ", "rmdir", "mv ", "chmod", "chown", "sudo", "su ",
                    "curl", "wget", "nc ", "bash -c", "sh -c", "exec", "eval",
                    "kill", "pkill", "systemctl", ">", ">>"]
SHELL_METACHARACTERS = {";", "|", "&", "$", "(", ")", "`", "\\n", "\\r"}


def _is_path_allowed(path: str) -> bool:
    resolved = os.path.realpath(path)
    return any(resolved.startswith(root) for root in ALLOWED_ROOTS)


def _is_command_safe(cmd: str) -> bool:
    cmd_s = cmd.strip()
    if not cmd_s:
        return False
    if any(d in cmd_s for d in DANGEROUS_TOKENS):
        return False
    if any(m in cmd_s for m in SHELL_METACHARACTERS):
        return False
    try:
        tokens = shlex.split(cmd_s)
    except ValueError:
        return False
    if not tokens:
        return False
    return tokens[0] in SAFE_PROGRAMS


class CodingAgentSkill(BaseSkill):
    name = "coding_agent"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")

        if action == "read":
            return self._read(args)
        elif action == "write":
            return self._write(args)
        elif action == "list":
            return self._list(args)
        elif action == "patch":
            return self._patch(args)
        elif action == "search":
            return await self._search(args)
        elif action == "run":
            return await self._run(args)

        return SkillResult(success=False, error=f"Unknown action: {action}")

    # ── read ────────────────────────────────────────────────────────────────
    def _read(self, args: dict) -> SkillResult:
        path = args.get("path")
        offset = int(args.get("offset", 0))
        limit = int(args.get("limit", 300))
        if not path or not _is_path_allowed(path):
            return SkillResult(success=False, error=f"Path not allowed or missing: {path}")
        try:
            with open(path, "r") as f:
                lines = f.readlines()
            chunk = lines[offset: offset + limit]
            numbered = "".join(f"{offset + i + 1:4d} | {l}" for i, l in enumerate(chunk))
            return SkillResult(
                success=True,
                output=numbered[:8000],
                data={"total_lines": len(lines), "showing": f"{offset + 1}-{offset + len(chunk)}"},
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── write ───────────────────────────────────────────────────────────────
    def _write(self, args: dict) -> SkillResult:
        path = args.get("path")
        content = args.get("content", "")
        if not path or not _is_path_allowed(path):
            return SkillResult(success=False, error=f"Path not allowed or missing: {path}")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return SkillResult(success=True, output=f"Written {len(content)} bytes to {path}")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── list ────────────────────────────────────────────────────────────────
    def _list(self, args: dict) -> SkillResult:
        directory = args.get("directory") or args.get("path")
        if not directory or not _is_path_allowed(directory):
            return SkillResult(success=False, error=f"Directory not allowed: {directory}")
        try:
            entries = []
            for name in sorted(os.listdir(directory)):
                tag = "/" if os.path.isdir(os.path.join(directory, name)) else ""
                entries.append(f"{name}{tag}")
            return SkillResult(success=True, output="\n".join(entries[:150]), data={"count": len(entries)})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── patch ───────────────────────────────────────────────────────────────
    def _patch(self, args: dict) -> SkillResult:
        """Apply a targeted search-and-replace patch.
        Args: path, old_str (exact text to find), new_str (replacement).
        """
        path = args.get("path")
        old_str = args.get("old_str", "")
        new_str = args.get("new_str", "")

        if not path or not _is_path_allowed(path):
            return SkillResult(success=False, error=f"Path not allowed or missing: {path}")
        if not old_str:
            return SkillResult(success=False, error="'old_str' is required for patch.")
        try:
            with open(path, "r") as f:
                original = f.read()

            if old_str not in original:
                return SkillResult(success=False,
                                   error=f"Pattern not found in {path} — cannot apply patch.")

            occurrences = original.count(old_str)
            if occurrences > 1:
                return SkillResult(
                    success=False,
                    error=f"Pattern appears {occurrences} times — provide more context to make it unique.",
                )

            patched = original.replace(old_str, new_str, 1)
            with open(path, "w") as f:
                f.write(patched)

            delta = len(patched) - len(original)
            return SkillResult(
                success=True,
                output=f"Patch applied to {path} ({delta:+d} bytes).",
                data={"path": path, "bytes_before": len(original), "bytes_after": len(patched)},
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── search ──────────────────────────────────────────────────────────────
    async def _search(self, args: dict) -> SkillResult:
        """Grep across allowed directories. Returns matching lines with filenames."""
        pattern = args.get("pattern", "")
        directory = args.get("directory") or ALLOWED_ROOTS[0]
        file_glob = args.get("file_glob", "*.py")

        if not pattern:
            return SkillResult(success=False, error="'pattern' is required for search.")
        if not _is_path_allowed(directory):
            return SkillResult(success=False, error=f"Directory not allowed: {directory}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "grep", "-rn", "--include", file_glob, pattern, directory,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            output = stdout.decode()[:5000]
            match_count = len(output.strip().splitlines()) if output.strip() else 0
            return SkillResult(
                success=True,
                output=output or f"No matches for '{pattern}' in {directory}",
                data={"matches": match_count, "pattern": pattern, "directory": directory},
            )
        except asyncio.TimeoutError:
            return SkillResult(success=False, error="Search timed out after 15s.")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── run ─────────────────────────────────────────────────────────────────
    async def _run(self, args: dict) -> SkillResult:
        """Execute a pre-approved read-only introspection command."""
        command = args.get("command", "").strip()
        if not command:
            return SkillResult(success=False, error="'command' is required.")
        if not _is_command_safe(command):
            return SkillResult(
                success=False,
                error=(
                    f"Command blocked by safety policy: {command!r}. "
                    "Only read-only commands (ls, cat, grep, du, pip list …) are allowed."
                ),
            )
        try:
            args = shlex.split(command)
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/var/www/ai.sanaa.co/backend",
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
            out = stdout.decode()[:4000]
            err = stderr.decode()[:500]
            success = proc.returncode == 0
            output = out if success else f"[Exit {proc.returncode}]\n{err or out}"
            return SkillResult(success=success, output=output, data={"exit_code": proc.returncode})
        except asyncio.TimeoutError:
            return SkillResult(success=False, error="Command timed out after 20s.")
        except Exception as e:
            return SkillResult(success=False, error=str(e))
