"""
Backup Automation Skill — scheduled database and config backups.

Actions:
  - backup_postgres: pg_dump PostgreSQL databases to /var/backups/sanaa/postgres/
  - backup_mysql: mysqldump finance tenant databases to /var/backups/sanaa/mysql/
  - backup_configs: archive key config files to /var/backups/sanaa/configs/
  - backup_status: report last backup time, size, success/failure per target
  - schedule_backup: register Celery periodic task for automated backups
"""

import asyncio
import glob
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BACKUP_ROOT = "/var/backups/sanaa"
POSTGRES_BACKUP_DIR = os.path.join(BACKUP_ROOT, "postgres")
MYSQL_BACKUP_DIR = os.path.join(BACKUP_ROOT, "mysql")
CONFIGS_BACKUP_DIR = os.path.join(BACKUP_ROOT, "configs")

STATUS_FILE = os.path.join(BACKUP_ROOT, "backup_status.json")

# Default database for PostgreSQL backups
DEFAULT_PG_DATABASE = "antigravity_db"
DEFAULT_PG_HOST = "localhost"
DEFAULT_PG_PORT = "5432"

# MySQL settings (same as finance_monitor)
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = "3306"
MYSQL_USER = "root"
MYSQL_PASS = "root"

# nginx config dirs for finance tenant discovery
NGINX_AVAILABLE = "/etc/nginx/sites-available"
NGINX_ENABLED = "/etc/nginx/sites-enabled"

# Config files to back up
CONFIG_PATHS = [
    "/var/www/ai.sanaa.co/backend/.env",
    "/var/www/ai.sanaa.co/frontend/.env",
    "/etc/nginx/nginx.conf",
    "/etc/nginx/sites-available/",
    "/etc/systemd/system/antigravity-web.service",
    "/etc/systemd/system/antigravity-worker.service",
    "/etc/systemd/system/antigravity-beat.service",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _run_cmd(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    """Run a command as a subprocess with timeout.

    Uses shell=False with explicit argument list for safety.
    Returns (returncode, stdout, stderr).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace").strip(),
            stderr.decode("utf-8", errors="replace").strip(),
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return -1, "", "Command timed out"
    except FileNotFoundError as e:
        return -1, "", f"Command not found: {e}"
    except Exception as e:
        return -1, "", str(e)


def _ensure_dir(path: str) -> None:
    """Create directory if it doesn't exist."""
    os.makedirs(path, mode=0o750, exist_ok=True)


def _file_size_human(size_bytes: int) -> str:
    """Convert bytes to human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _load_status() -> dict:
    """Load backup status from the JSON file."""
    if os.path.isfile(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_status(status: dict) -> None:
    """Persist backup status to JSON file."""
    _ensure_dir(BACKUP_ROOT)
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2, default=str)
    except OSError as e:
        logger.error(f"[BackupAutomation] Failed to save status: {e}")


def _record_result(
    target: str,
    success: bool,
    path: str = "",
    size: int = 0,
    error: str = "",
) -> None:
    """Record the result of a backup operation in the status file."""
    status = _load_status()
    status[target] = {
        "last_backup": datetime.now(timezone.utc).isoformat(),
        "success": success,
        "path": path,
        "size_bytes": size,
        "size_human": _file_size_human(size) if size else "0 B",
        "error": error,
    }
    _save_status(status)


def _discover_finance_tenants() -> list[dict]:
    """Discover finance tenant databases from nginx configs.

    Mirrors the logic in finance_monitor to find active tenants.
    Returns a list of dicts with 'domain' and 'db_name' keys.
    """
    tenants = []
    if not os.path.isdir(NGINX_AVAILABLE):
        return tenants

    for f in sorted(os.listdir(NGINX_AVAILABLE)):
        if not (f.endswith(".conf") and "sanaa" in f):
            continue

        domain = f.replace(".conf", "")
        enabled_link = os.path.join(NGINX_ENABLED, f)
        if not os.path.islink(enabled_link):
            continue

        conf_path = os.path.join(NGINX_AVAILABLE, f)
        app_root = None
        try:
            with open(conf_path) as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("root ") and "mbalala/public" in line:
                        root_path = line.split("root ", 1)[1].rstrip(";").strip()
                        if root_path.endswith("/public"):
                            app_root = root_path[:-7]
                        break
        except Exception:
            continue

        if not app_root or not os.path.isdir(app_root):
            continue

        # Read DB_DATABASE from .env
        env_file = os.path.join(app_root, ".env")
        db_name = domain.split(".")[0]
        if os.path.isfile(env_file):
            try:
                with open(env_file) as ef:
                    for line in ef:
                        if line.strip().startswith("DB_DATABASE="):
                            db_name = line.strip().split("=", 1)[1].strip()
                            break
            except Exception:
                pass

        tenants.append({"domain": domain, "db_name": db_name})

    return tenants


def _timestamp() -> str:
    """Return a filename-safe UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# Skill Implementation
# ---------------------------------------------------------------------------

class BackupAutomationSkill(BaseSkill):
    """Scheduled database and configuration backup automation."""

    name = "backup_automation"
    description = (
        "Automated backup management: PostgreSQL dumps, MySQL dumps for "
        "finance tenants, config file archives, backup status reports, "
        "and scheduled backup registration via Celery."
    )
    version = "1.0.0"
    permissions = ["shell"]
    requires_approval = True
    timeout = 300
    tags = ["backup", "database", "automation", "infrastructure", "system"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")

        if action == "backup_postgres":
            return await self._backup_postgres(args)
        elif action == "backup_mysql":
            return await self._backup_mysql(args)
        elif action == "backup_configs":
            return await self._backup_configs(args)
        elif action == "backup_status":
            return await self._backup_status(args)
        elif action == "schedule_backup":
            return await self._schedule_backup(args)

        return SkillResult(
            success=False,
            error=(
                f"Unknown action: {action}. "
                "Valid actions: backup_postgres, backup_mysql, backup_configs, "
                "backup_status, schedule_backup"
            ),
        )

    # ------------------------------------------------------------------
    # backup_postgres
    # ------------------------------------------------------------------
    async def _backup_postgres(self, args: dict) -> SkillResult:
        """Dump a PostgreSQL database using pg_dump."""
        database = args.get("database", DEFAULT_PG_DATABASE)
        ts = _timestamp()
        dump_file = os.path.join(POSTGRES_BACKUP_DIR, f"{database}_{ts}.sql.gz")

        # Verify pg_dump exists
        if not shutil.which("pg_dump"):
            error_msg = "pg_dump not found on PATH"
            _record_result(f"postgres:{database}", False, error=error_msg)
            return SkillResult(success=False, error=error_msg)

        try:
            _ensure_dir(POSTGRES_BACKUP_DIR)
        except OSError as e:
            error_msg = f"Cannot create backup directory: {e}"
            _record_result(f"postgres:{database}", False, error=error_msg)
            return SkillResult(success=False, error=error_msg)

        # pg_dump piped through gzip — use shell=False by running
        # pg_dump to stdout then writing through gzip in a pipeline.
        # We use a two-step approach: dump to temp, then compress.
        temp_file = dump_file.replace(".sql.gz", ".sql")
        cmd = [
            "pg_dump",
            "-h", DEFAULT_PG_HOST,
            "-p", DEFAULT_PG_PORT,
            "-U", "postgres",
            "--no-password",
            "-d", database,
            "-f", temp_file,
        ]

        returncode, stdout, stderr = await _run_cmd(cmd, timeout=180)

        if returncode != 0:
            error_msg = f"pg_dump failed (exit {returncode}): {stderr}"
            _record_result(f"postgres:{database}", False, error=error_msg)
            # Clean up partial dump
            if os.path.isfile(temp_file):
                os.remove(temp_file)
            return SkillResult(success=False, error=error_msg)

        # Compress with gzip
        gzip_ret, _, gzip_err = await _run_cmd(["gzip", "-f", temp_file], timeout=60)
        if gzip_ret != 0:
            # gzip failed — keep the uncompressed file
            dump_file = temp_file
            logger.warning(f"[BackupAutomation] gzip failed: {gzip_err}")

        if os.path.isfile(dump_file):
            size = os.path.getsize(dump_file)
        else:
            size = 0

        _record_result(f"postgres:{database}", True, path=dump_file, size=size)

        return SkillResult(
            success=True,
            output=(
                f"PostgreSQL backup completed for '{database}'.\n"
                f"File: {dump_file}\n"
                f"Size: {_file_size_human(size)}"
            ),
            data={
                "database": database,
                "path": dump_file,
                "size_bytes": size,
                "size_human": _file_size_human(size),
            },
        )

    # ------------------------------------------------------------------
    # backup_mysql
    # ------------------------------------------------------------------
    async def _backup_mysql(self, args: dict) -> SkillResult:
        """Dump MySQL finance tenant databases using mysqldump."""
        specific_db = args.get("database")

        # Verify mysqldump exists
        if not shutil.which("mysqldump"):
            error_msg = "mysqldump not found on PATH"
            _record_result("mysql:all", False, error=error_msg)
            return SkillResult(success=False, error=error_msg)

        try:
            _ensure_dir(MYSQL_BACKUP_DIR)
        except OSError as e:
            error_msg = f"Cannot create backup directory: {e}"
            _record_result("mysql:all", False, error=error_msg)
            return SkillResult(success=False, error=error_msg)

        # Discover finance tenants
        tenants = _discover_finance_tenants()
        if specific_db:
            tenants = [{"domain": specific_db, "db_name": specific_db}]
        elif not tenants:
            # No tenants found is not a failure — just report it
            _record_result("mysql:all", True, error="No finance tenant databases found")
            return SkillResult(
                success=True,
                output="No finance tenant databases found to back up.",
                data={"tenants_found": 0, "backups": []},
            )

        ts = _timestamp()
        results = []

        for tenant in tenants:
            db_name = tenant["db_name"]
            dump_file = os.path.join(MYSQL_BACKUP_DIR, f"{db_name}_{ts}.sql.gz")
            temp_file = dump_file.replace(".sql.gz", ".sql")

            cmd = [
                "mysqldump",
                f"-h{MYSQL_HOST}",
                f"-P{MYSQL_PORT}",
                f"-u{MYSQL_USER}",
                f"-p{MYSQL_PASS}",
                "--single-transaction",
                "--routines",
                "--triggers",
                db_name,
                f"--result-file={temp_file}",
            ]

            returncode, stdout, stderr = await _run_cmd(cmd, timeout=180)

            if returncode != 0:
                error_msg = f"mysqldump failed for {db_name} (exit {returncode}): {stderr}"
                _record_result(f"mysql:{db_name}", False, error=error_msg)
                results.append({"database": db_name, "success": False, "error": error_msg})
                if os.path.isfile(temp_file):
                    os.remove(temp_file)
                continue

            # Compress
            gzip_ret, _, _ = await _run_cmd(["gzip", "-f", temp_file], timeout=60)
            final_file = dump_file if gzip_ret == 0 else temp_file

            size = os.path.getsize(final_file) if os.path.isfile(final_file) else 0
            _record_result(f"mysql:{db_name}", True, path=final_file, size=size)
            results.append({
                "database": db_name,
                "success": True,
                "path": final_file,
                "size_bytes": size,
                "size_human": _file_size_human(size),
            })

        succeeded = sum(1 for r in results if r.get("success"))
        failed = len(results) - succeeded

        output_lines = [
            f"MySQL backup completed: {succeeded} succeeded, {failed} failed.",
        ]
        for r in results:
            if r.get("success"):
                output_lines.append(
                    f"  ✓ {r['database']}: {r.get('size_human', '?')} → {r.get('path', '?')}"
                )
            else:
                output_lines.append(f"  ✗ {r['database']}: {r.get('error', 'unknown error')}")

        return SkillResult(
            success=failed == 0,
            output="\n".join(output_lines),
            data={"tenants_found": len(tenants), "backups": results},
        )

    # ------------------------------------------------------------------
    # backup_configs
    # ------------------------------------------------------------------
    async def _backup_configs(self, args: dict) -> SkillResult:
        """Archive key configuration files into a tarball."""
        ts = _timestamp()
        archive_name = f"configs_{ts}.tar.gz"
        archive_path = os.path.join(CONFIGS_BACKUP_DIR, archive_name)

        if not shutil.which("tar"):
            error_msg = "tar not found on PATH"
            _record_result("configs", False, error=error_msg)
            return SkillResult(success=False, error=error_msg)

        try:
            _ensure_dir(CONFIGS_BACKUP_DIR)
        except OSError as e:
            error_msg = f"Cannot create backup directory: {e}"
            _record_result("configs", False, error=error_msg)
            return SkillResult(success=False, error=error_msg)

        # Collect existing config paths
        existing_paths = []
        for p in CONFIG_PATHS:
            if os.path.exists(p):
                existing_paths.append(p)
            else:
                logger.info(f"[BackupAutomation] Config path not found, skipping: {p}")

        if not existing_paths:
            error_msg = "No config files found to back up"
            _record_result("configs", False, error=error_msg)
            return SkillResult(success=False, error=error_msg)

        cmd = ["tar", "-czf", archive_path] + existing_paths

        returncode, stdout, stderr = await _run_cmd(cmd, timeout=60)

        if returncode != 0:
            error_msg = f"tar failed (exit {returncode}): {stderr}"
            _record_result("configs", False, error=error_msg)
            return SkillResult(success=False, error=error_msg)

        size = os.path.getsize(archive_path) if os.path.isfile(archive_path) else 0
        _record_result("configs", True, path=archive_path, size=size)

        return SkillResult(
            success=True,
            output=(
                f"Config backup completed.\n"
                f"Archive: {archive_path}\n"
                f"Size: {_file_size_human(size)}\n"
                f"Files included: {len(existing_paths)}"
            ),
            data={
                "path": archive_path,
                "size_bytes": size,
                "size_human": _file_size_human(size),
                "files_count": len(existing_paths),
                "files": existing_paths,
            },
        )

    # ------------------------------------------------------------------
    # backup_status
    # ------------------------------------------------------------------
    async def _backup_status(self, args: dict) -> SkillResult:
        """Report the status of all recent backups."""
        status = _load_status()

        if not status:
            return SkillResult(
                success=True,
                output="No backup records found. Run a backup action first.",
                data={"targets": {}},
            )

        output_lines = ["📋 Backup Status Report", "=" * 40, ""]

        for target, info in sorted(status.items()):
            success_icon = "✓" if info.get("success") else "✗"
            last_time = info.get("last_backup", "unknown")
            size = info.get("size_human", "0 B")
            path = info.get("path", "")
            error = info.get("error", "")

            output_lines.append(f"  {success_icon} {target}")
            output_lines.append(f"    Last backup: {last_time}")
            output_lines.append(f"    Size: {size}")
            if path:
                output_lines.append(f"    Path: {path}")
            if error:
                output_lines.append(f"    Error: {error}")
            output_lines.append("")

        return SkillResult(
            success=True,
            output="\n".join(output_lines),
            data={"targets": status},
        )

    # ------------------------------------------------------------------
    # schedule_backup
    # ------------------------------------------------------------------
    async def _schedule_backup(self, args: dict) -> SkillResult:
        """Register a Celery periodic task for automated backups."""
        target = args.get("target", "all")
        schedule_expr = args.get("schedule", "0 2 * * *")

        # Parse cron expression (minute hour day month dow)
        parts = schedule_expr.strip().split()
        if len(parts) != 5:
            return SkillResult(
                success=False,
                error=(
                    f"Invalid cron expression: '{schedule_expr}'. "
                    "Expected 5 fields: minute hour day_of_month month day_of_week"
                ),
            )

        try:
            from celery.schedules import crontab
            from core.tasks import app as celery_app

            minute, hour, day_of_month, month_of_year, day_of_week = parts

            task_name = f"backup-{target}"
            celery_app.conf.beat_schedule[task_name] = {
                "task": "core.tasks.run_backup",
                "schedule": crontab(
                    minute=minute,
                    hour=hour,
                    day_of_month=day_of_month,
                    month_of_year=month_of_year,
                    day_of_week=day_of_week,
                ),
                "kwargs": {"target": target},
            }

            return SkillResult(
                success=True,
                output=(
                    f"Backup scheduled successfully.\n"
                    f"Target: {target}\n"
                    f"Schedule: {schedule_expr} (cron)\n"
                    f"Task name: {task_name}\n"
                    f"Note: Celery Beat must be restarted to pick up the new schedule."
                ),
                data={
                    "task_name": task_name,
                    "target": target,
                    "schedule": schedule_expr,
                },
            )

        except ImportError as e:
            return SkillResult(
                success=False,
                error=f"Celery not available: {e}",
            )
        except Exception as e:
            logger.error(f"[BackupAutomation] Failed to register schedule: {e}")
            return SkillResult(
                success=False,
                error=f"Failed to register backup schedule: {e}",
            )


# Register entry point
handler = BackupAutomationSkill
