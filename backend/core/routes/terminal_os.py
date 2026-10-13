"""
Sanaa OS — Secure Terminal Backend
Sandboxed command execution with allowlists, timeouts, and audit logging.
"""

import re
import shlex
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.routes.deps import require_auth, is_admin, RateLimit
from core.database import AuditLog

logger = logging.getLogger(__name__)
router = APIRouter()

# Commands that are NEVER allowed
BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/",
    r">\s*/dev/null",
    r"mkfs",
    r"dd\s+if=.*of=/dev",
    r"\|\s*sh",
    r"\|\s*bash",
    r"eval\s*\(",
    r"exec\s*\(",
    r"wget.*\|\s*sh",
    r"curl.*\|\s*sh",
    r"curl.*\|\s*bash",
    r"base64.*\|\s*sh",
    r";\s*rm\s+-rf",
    r"sudo\s+su",
    r"passwd",
    r"userdel",
    r"groupdel",
]

# Allowed base commands (whitelist approach for safety)
ALLOWED_COMMANDS = {
    # System info
    "ps", "top", "htop", "df", "du", "free", "uptime", "whoami", "uname",
    "ls", "cat", "head", "tail", "less", "more", "wc", "sort", "uniq",
    "grep", "rg", "find", "which", "whereis", "file", "stat",
    "pwd", "cd", "echo", "date", "cal", "clear", "env", "printenv",
    "hostname", "id", "groups", "who", "w", "last", "history",
    # Network
    "ping", "curl", "wget", "netstat", "ss", "ip", "ifconfig", "traceroute",
    "nslookup", "dig", "host", "whois", "nc", "nmap",
    # Process
    "kill", "pkill", "pgrep", "nice", "renice", "nohup",
    # Disk / files
    "mount", "umount", "fdisk", "lsblk", "blkid", "mkdir", "touch", "cp", "mv", "ln",
    "chmod", "chown", "tee", "xargs", "realpath", "readlink", "basename", "dirname",
    # Git
    "git", "gitk", "gh",
    # Python / Node / PHP
    "python", "python3", "pip", "pip3", "pipx", "uv", "uvicorn", "node", "npm", "npx", "pnpm",
    "php", "composer", "artisan",
    # Containers / orchestration
    "docker", "docker-compose", "kubectl", "helm",
    # Services
    "systemctl", "service", "journalctl", "supervisorctl",
    # Compression
    "tar", "gzip", "gunzip", "zip", "unzip", "bzip2", "zstd",
    # Text / JSON
    "sed", "awk", "cut", "tr", "diff", "patch", "vim", "nano", "jq", "yq",
    # DB
    "psql", "mysql", "mariadb", "redis-cli", "mongo", "sqlite3",
    # Monitoring
    "htop", "iotop", "nethogs", "iftop", "vnstat", "watch",
    # Sanaa / ops
    "sanaa", "nginx", "redis-server", "make", "tree", "lsof", "lsb_release",
    "timedatectl", "crontab", "bat", "htpasswd", "openssl", "ssh", "scp", "rsync",
    "pytest", "celery", "certbot", "fail2ban-client", "ufw",
}

WORKSPACE_ROOTS = [
    "/var/www/ai.sanaa.co",
    "/var/www/soko",
    "/var/www",
    "/etc/nginx",
    "/var/log",
]

TERMINAL_SNIPPETS = [
    {"id": "status", "label": "Status", "command": "systemctl is-active sanaa-ai-web.service nginx php8.3-fpm"},
    {"id": "logs", "label": "AI logs", "command": "tail -n 80 /var/www/ai.sanaa.co/backend/logs/uvicorn.log"},
    {"id": "docker", "label": "Docker", "command": "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'"},
    {"id": "disk", "label": "Disk", "command": "df -h / /var/www"},
    {"id": "soko", "label": "Soko DB", "command": "mysql -e 'SELECT COUNT(*) AS orders FROM soko.orders'"},
    {"id": "git", "label": "Git status", "command": "git -C /var/www/ai.sanaa.co status -sb"},
    {"id": "git-log", "label": "Git log", "command": "git -C /var/www/ai.sanaa.co log -1 --oneline"},
    {"id": "nginx", "label": "Nginx test", "command": "nginx -t"},
    {"id": "skills", "label": "Skills", "command": "ls /var/www/ai.sanaa.co/backend/skills"},
]

# Maximum output size
MAX_OUTPUT_BYTES = 500_000
OPERATOR_MAX_OUTPUT_BYTES = 1_500_000
ADMIN_MAX_OUTPUT_BYTES = 2_000_000
COMMAND_TIMEOUT = 30
OPERATOR_COMMAND_TIMEOUT = 120
ADMIN_COMMAND_TIMEOUT = 180


class TerminalExecRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=4000)
    cwd: Optional[str] = "/var/www/ai.sanaa.co"


class TerminalExecResponse(BaseModel):
    stdout: str
    stderr: str
    returncode: int
    executed_at: str
    command: str
    duration_ms: int


def _blocked_reason(command: str) -> str | None:
    lower_cmd = command.lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, lower_cmd):
            return f"Command matches blocked pattern: {pattern}"
    return None


def _normalize_cwd(cwd: str | None) -> str:
    path = (cwd or "/var/www/ai.sanaa.co").strip().rstrip("/") or "/"
    if ".." in path or not path.startswith("/"):
        raise HTTPException(400, "Invalid working directory")
    for root in WORKSPACE_ROOTS:
        if path == root or path.startswith(root + "/"):
            return path
    raise HTTPException(400, f"Working directory must be under: {', '.join(WORKSPACE_ROOTS)}")


def _is_command_safe(command: str) -> tuple[bool, str]:
    """Check if a command passes security filters.

    The user's role is re-derived from the signed session outside this helper;
    no client-sent privilege flag is trusted here.
    """
    blocked = _blocked_reason(command)
    if blocked:
        return False, blocked

    try:
        parts = shlex.split(command)
        if not parts:
            return False, "Empty command"
        base = parts[0]
    except ValueError:
        return False, "Invalid shell syntax"

    if base in ALLOWED_COMMANDS:
        return True, ""

    if base.startswith("/") and base.split("/")[-1] in ALLOWED_COMMANDS:
        return True, ""

    return False, f"Command '{base}' is not in the allowed command list."


@router.get("/api/terminal/context")
async def terminal_context(user: dict = Depends(require_auth)):
    """Terminal capabilities, workspaces, and quick snippets for the OS shell."""
    role = str(user.get("role", "operator")).lower()
    admin_mode = is_admin(user)
    operator_mode = role == "operator"
    return {
        "role": role,
        "email": user.get("email"),
        "admin_shell": admin_mode,
        "operator_shell": operator_mode,
        "can_execute": role in ("admin", "operator"),
        "workspaces": [
            {"id": "sanaa", "label": "Sanaa AI", "path": "/var/www/ai.sanaa.co"},
            {"id": "sanaa-backend", "label": "Backend", "path": "/var/www/ai.sanaa.co/backend"},
            {"id": "sanaa-frontend", "label": "Frontend", "path": "/var/www/ai.sanaa.co/frontend"},
            {"id": "soko", "label": "Soko", "path": "/var/www/soko"},
            {"id": "www", "label": "/var/www", "path": "/var/www"},
            {"id": "nginx", "label": "Nginx", "path": "/etc/nginx"},
            {"id": "logs", "label": "Logs", "path": "/var/log"},
        ],
        "snippets": TERMINAL_SNIPPETS,
        "timeout_seconds": ADMIN_COMMAND_TIMEOUT if admin_mode else (OPERATOR_COMMAND_TIMEOUT if operator_mode else COMMAND_TIMEOUT),
        "max_output_kb": (ADMIN_MAX_OUTPUT_BYTES if admin_mode else (OPERATOR_MAX_OUTPUT_BYTES if operator_mode else MAX_OUTPUT_BYTES)) // 1024,
    }


@router.post("/api/terminal/exec", response_model=TerminalExecResponse)
async def terminal_exec(
    body: TerminalExecRequest,
    user: dict = Depends(require_auth),
    _rate: None = Depends(RateLimit(limit=30)),
):
    """Execute a shell command securely.

    Admin/operator privileges are re-derived from the signed session only;
    no client-sent privilege flag is accepted or trusted.
    """
    command = body.command.strip()
    email = user.get("email", "unknown")
    role = str(user.get("role", "operator")).lower()
    admin_mode = is_admin(user)
    operator_elevated = role == "operator"

    if role in ("viewer", "seller"):
        raise HTTPException(403, "Your role cannot execute shell commands")

    safe, reason = _is_command_safe(command)
    if not safe:
        logger.warning(f"Terminal blocked command from {email}: {command} — {reason}")
        raise HTTPException(403, f"Command blocked: {reason}")

    cwd = _normalize_cwd(body.cwd)

    # Convert the command string into an explicit argument list for shell=False.
    # This rejects shell metacharacters and injection patterns.
    try:
        from core.utils.sanitize import sanitize_command_string

        cmd_args = sanitize_command_string(command)
    except ValueError as exc:
        logger.warning(f"Terminal blocked command from {email}: {command} — {exc}")
        raise HTTPException(403, f"Command blocked: {exc}")

    if admin_mode:
        timeout = ADMIN_COMMAND_TIMEOUT
        max_output = ADMIN_MAX_OUTPUT_BYTES
    elif operator_elevated:
        timeout = OPERATOR_COMMAND_TIMEOUT
        max_output = OPERATOR_MAX_OUTPUT_BYTES
    else:
        timeout = COMMAND_TIMEOUT
        max_output = MAX_OUTPUT_BYTES

    logger.info(
        f"Terminal exec by {email} ({role}, admin_mode={admin_mode}): {command} (cwd={cwd})"
    )

    start_time = datetime.now(timezone.utc)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        stdout = stdout_bytes.decode(errors="replace")[:max_output]
        stderr = stderr_bytes.decode(errors="replace")[:max_output]

        # Async audit log
        try:
            await AuditLog.create(
                action="terminal.exec",
                actor=email,
                resource=command,
                details={
                    "cwd": cwd,
                    "role": role,
                    "admin_mode": admin_mode,
                    "returncode": proc.returncode,
                    "duration_ms": duration_ms,
                    "stdout_preview": stdout[:500],
                    "stderr_preview": stderr[:500],
                },
            )
        except Exception:
            pass

        return TerminalExecResponse(
            stdout=stdout,
            stderr=stderr,
            returncode=proc.returncode,
            executed_at=start_time.isoformat(),
            command=command,
            duration_ms=duration_ms,
        )

    except asyncio.TimeoutError:
        logger.warning(f"Terminal command timed out: {command}")
        try:
            proc.kill()
        except Exception:
            pass
        raise HTTPException(408, f"Command timed out after {timeout} seconds")
    except Exception as e:
        logger.error(f"Terminal exec error: {e}")
        raise HTTPException(500, f"Execution error: {str(e)}")


@router.get("/api/terminal/history")
async def terminal_history(limit: int = 50, user: dict = Depends(require_auth)):
    """Get recent terminal commands from audit log."""
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import select, desc

        async with AsyncSessionLocal() as session:
            from core.database import AuditLog as AL
            stmt = select(AL).where(AL.action == "terminal.exec").order_by(desc(AL.created_at)).limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return {
                "commands": [
                    {
                        "command": r.resource,
                        "actor": r.actor,
                        "returncode": r.details.get("returncode") if r.details else None,
                        "duration_ms": r.details.get("duration_ms") if r.details else None,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in rows
                ]
            }
    except Exception as e:
        logger.error(f"Terminal history error: {e}")
        return {"commands": []}
