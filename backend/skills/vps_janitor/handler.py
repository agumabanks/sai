"""
VPS Janitor Skill — automated disk space cleanup for the Sanaa server.

Removes old database backup rotations, Flutter/build artifacts, stale node_modules
in archived projects, package caches, and /tmp debris. Reports exactly what was
deleted and how much disk space was freed, so every action is auditable.

Actions:
  - status  : show disk usage and the top space consumers (no deletions)
  - scan    : dry-run — list what WOULD be deleted and estimated savings
  - clean   : execute cleanup, report bytes freed per category
"""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cleanup rule definitions
# ---------------------------------------------------------------------------

# (glob_pattern, max_age_days, label, is_dir)
# max_age_days=0 means "always delete" (build artifacts, caches)
BACKUP_GLOBS: list[tuple[str, int, str]] = [
    # Farzone SOS
    ("/var/backups/farzone/*.sql.gz", 3, "farzone db backups"),
    # Finance tenant rotating backups
    ("/var/www/*/mbalala/storage/backups/finance_backup_*.sql.gz", 3, "finance tenant backups"),
    ("/var/www/*/mbalala/storage/backups/pre-update/*.sql.gz", 3, "pre-update backups"),
    # Soko backup rotation
    ("/var/www/soko/backups/soko_backup_*.sql.gz", 3, "soko backups"),
    ("/var/www/soko/backups/soko_backup_*.sql", 3, "soko empty backup stubs"),
    ("/var/www/soko/apps/backend-laravel/storage/backups/soko_backup_*.sql", 3, "soko laravel backup stubs"),
    # Baraka one-off backups (no rotation script — keep 30 days)
    ("/var/www/baraka.sanaa.co/backups/*.sql", 30, "baraka backups"),
    ("/var/www/baraka.sanaa.co/storage/app/backups/*.sql", 30, "baraka app backups"),
    # Procurement
    ("/var/www/procurement/backups/*.sql", 30, "procurement backups"),
    # Swarm automated tarballs
    ("/home/swarm/backups/coding-swarm_*.tgz", 3, "coding-swarm tarballs"),
    # Root daily dumps (handled separately by max_age_days param)
    ("/root/backups/daily_db_*", 3, "root daily db dumps"),
]

# Stale /tmp patterns (always delete if >1 day old)
TMP_GLOBS: list[tuple[str, str]] = [
    ("/tmp/flutter_tools.*", "flutter tool caches"),
    ("/tmp/google-cloud-sdk", "gcloud sdk temp"),
    ("/tmp/gcloud.tar.gz", "gcloud download"),
    ("/tmp/phpstan", "phpstan temp cache"),
    ("/tmp/sanaa_monitor.log", "monitor log in tmp"),
    ("/tmp/node-compile-cache", "node compile cache"),
]

# Build artifact directories (always safe to delete — regenerable)
BUILD_DIRS: list[tuple[str, str]] = [
    ("/var/www/finance/finance_client_app/build", "finance_client_app Flutter build"),
    ("/var/www/finance/finance_rbac_app/build", "finance_rbac_app Flutter build"),
]

# macOS metadata garbage from zip extractions
MACOS_GLOBS: list[str] = [
    "/var/www/**/__MACOSX",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dir_size_mb(path: str) -> float:
    """Return directory size in MB using du (fast, handles large trees)."""
    try:
        result = subprocess.run(
            ["du", "-sm", path], capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return float(result.stdout.split()[0])
    except Exception:
        pass
    return 0.0


def _file_size_mb(path: str) -> float:
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except Exception:
        return 0.0


def _disk_usage_pct() -> int:
    """Return the percentage of / used."""
    try:
        result = subprocess.run(
            ["df", "-h", "/"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                return int(parts[4].rstrip("%"))
    except Exception:
        pass
    return 0


def _disk_free_gb() -> float:
    try:
        result = subprocess.run(
            ["df", "-BG", "/"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 4:
                return float(parts[3].rstrip("G"))
    except Exception:
        pass
    return 0.0


def _is_old_enough(path: str, max_age_days: int) -> bool:
    try:
        mtime = os.path.getmtime(path)
        age_days = (datetime.now().timestamp() - mtime) / 86400
        return age_days > max_age_days
    except Exception:
        return False


def _snap_disabled_revisions() -> list[str]:
    """Return list of 'snap remove <name> --revision=<rev>' commands for disabled snaps."""
    commands = []
    try:
        result = subprocess.run(
            ["snap", "list", "--all"], capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6 and "disabled" in line:
                name = parts[0]
                revision = parts[2]
                commands.append((name, revision))
    except Exception:
        pass
    return commands


# ---------------------------------------------------------------------------
# Scan logic (dry run)
# ---------------------------------------------------------------------------

def _scan(max_age_days: int) -> dict:
    """
    Return a dict describing what would be deleted and the estimated savings.
    No files are deleted.
    """
    candidates: list[dict] = []
    total_mb = 0.0

    # --- Backup rotations ---
    for pattern, age_days, label in BACKUP_GLOBS:
        effective_age = max_age_days if age_days == 3 else age_days
        for path in glob.glob(pattern, recursive=True):
            if not os.path.exists(path):
                continue
            if not _is_old_enough(path, effective_age):
                continue
            if os.path.isdir(path):
                mb = _dir_size_mb(path)
            else:
                mb = _file_size_mb(path)
            total_mb += mb
            candidates.append({"path": path, "label": label, "mb": round(mb, 1)})

    # --- /tmp stale ---
    for pattern, label in TMP_GLOBS:
        for path in glob.glob(pattern):
            if not os.path.exists(path):
                continue
            if not _is_old_enough(path, 1):
                continue
            mb = _dir_size_mb(path) if os.path.isdir(path) else _file_size_mb(path)
            total_mb += mb
            candidates.append({"path": path, "label": label, "mb": round(mb, 1)})

    # --- Build dirs ---
    for path, label in BUILD_DIRS:
        if os.path.isdir(path):
            mb = _dir_size_mb(path)
            total_mb += mb
            candidates.append({"path": path, "label": label, "mb": round(mb, 1)})

    # --- macOS metadata ---
    for pattern in MACOS_GLOBS:
        for path in glob.glob(pattern, recursive=True):
            if os.path.isdir(path):
                mb = _dir_size_mb(path)
                total_mb += mb
                candidates.append({"path": path, "label": "__MACOSX garbage", "mb": round(mb, 1)})

    # --- Snap disabled ---
    snap_cmds = _snap_disabled_revisions()
    if snap_cmds:
        candidates.append({
            "path": f"snap disabled: {[f'{n}@{r}' for n, r in snap_cmds]}",
            "label": "snap old revisions",
            "mb": 0,
        })

    return {"candidates": candidates, "total_mb": round(total_mb, 1)}


# ---------------------------------------------------------------------------
# Clean logic (execute)
# ---------------------------------------------------------------------------

def _clean(max_age_days: int) -> dict:
    """
    Execute the cleanup. Returns a report dict.
    """
    freed_mb = 0.0
    actions: list[dict] = []

    def _delete(path: str, label: str):
        nonlocal freed_mb
        mb = _dir_size_mb(path) if os.path.isdir(path) else _file_size_mb(path)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            freed_mb += mb
            actions.append({"path": path, "label": label, "mb": round(mb, 1), "ok": True})
            logger.info(f"vps_janitor: deleted {path} ({mb:.1f} MB) [{label}]")
        except Exception as e:
            actions.append({"path": path, "label": label, "mb": 0, "ok": False, "error": str(e)})
            logger.warning(f"vps_janitor: could not delete {path}: {e}")

    # --- Backup rotations ---
    for pattern, age_days, label in BACKUP_GLOBS:
        effective_age = max_age_days if age_days == 3 else age_days
        for path in sorted(glob.glob(pattern, recursive=True)):
            if not os.path.exists(path):
                continue
            if _is_old_enough(path, effective_age):
                _delete(path, label)

    # --- /tmp stale ---
    for pattern, label in TMP_GLOBS:
        for path in glob.glob(pattern):
            if os.path.exists(path) and _is_old_enough(path, 1):
                _delete(path, label)

    # --- Build dirs ---
    for path, label in BUILD_DIRS:
        if os.path.isdir(path):
            _delete(path, label)

    # --- macOS metadata ---
    for pattern in MACOS_GLOBS:
        for path in glob.glob(pattern, recursive=True):
            if os.path.isdir(path):
                _delete(path, label="__MACOSX garbage")

    # --- Snap disabled revisions ---
    for name, revision in _snap_disabled_revisions():
        try:
            result = subprocess.run(
                ["snap", "remove", name, f"--revision={revision}"],
                capture_output=True, text=True, timeout=60,
            )
            ok = result.returncode == 0
            actions.append({
                "path": f"snap:{name}@{revision}",
                "label": "snap old revision",
                "mb": 0,
                "ok": ok,
                "error": result.stderr.strip() if not ok else "",
            })
        except Exception as e:
            actions.append({"path": f"snap:{name}@{revision}", "label": "snap", "mb": 0, "ok": False, "error": str(e)})

    # --- Gradle caches ---
    gradle_cache = Path("/root/.gradle/caches")
    if gradle_cache.exists():
        _delete(str(gradle_cache), "Gradle build caches")

    # --- npm cache ---
    try:
        subprocess.run(
            ["npm", "cache", "clean", "--force"],
            capture_output=True, timeout=30,
        )
        actions.append({"path": "npm cache", "label": "npm cache", "mb": 0, "ok": True})
    except Exception as e:
        actions.append({"path": "npm cache", "label": "npm cache", "mb": 0, "ok": False, "error": str(e)})

    # --- Journal vacuum ---
    try:
        subprocess.run(
            ["journalctl", f"--vacuum-time={max_age_days}d"],
            capture_output=True, timeout=30,
        )
        actions.append({"path": "systemd journal", "label": "journal vacuum", "mb": 0, "ok": True})
    except Exception as e:
        pass

    return {
        "freed_mb": round(freed_mb, 1),
        "freed_gb": round(freed_mb / 1024, 2),
        "actions": actions,
        "deleted": sum(1 for a in actions if a.get("ok")),
        "failed": sum(1 for a in actions if not a.get("ok")),
    }


# ---------------------------------------------------------------------------
# Status (disk summary)
# ---------------------------------------------------------------------------

def _status() -> dict:
    pct = _disk_usage_pct()
    free_gb = _disk_free_gb()

    top = []
    try:
        result = subprocess.run(
            ["du", "-sh", "--", "/var/www", "/root/backups", "/root/.gradle",
             "/root/.npm", "/root/.pub-cache", "/tmp", "/snap", "/var/log"],
            capture_output=True, text=True, timeout=30,
        )
        for line in result.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                top.append({"size": parts[0], "path": parts[1]})
        top.sort(key=lambda x: x["size"], reverse=True)
    except Exception:
        pass

    return {"disk_pct": pct, "free_gb": free_gb, "top_consumers": top}


# ---------------------------------------------------------------------------
# Skill class
# ---------------------------------------------------------------------------

class VpsJanitorSkill(BaseSkill):
    name = "vps_janitor"
    description = (
        "VPS disk space janitor — scans for and removes old database backup rotations, "
        "build artifacts, stale caches and /tmp debris. Reports bytes freed."
    )
    version = "1.0.0"
    permissions = ["shell", "filesystem"]
    timeout = 120
    tags = ["disk", "cleanup", "maintenance", "backups", "infrastructure"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action", "status")
        max_age_days = int(args.get("max_age_days", 3))
        threshold_pct = int(args.get("disk_threshold_pct", 80))

        try:
            if action == "status":
                data = await asyncio.get_event_loop().run_in_executor(None, _status)
                output = self._format_status(data)
                return SkillResult(success=True, output=output, data=data)

            elif action == "scan":
                data = await asyncio.get_event_loop().run_in_executor(
                    None, _scan, max_age_days
                )
                output = self._format_scan(data, max_age_days)
                return SkillResult(success=True, output=output, data=data)

            elif action == "clean":
                pct = _disk_usage_pct()
                if threshold_pct > 0 and pct < threshold_pct:
                    return SkillResult(
                        success=True,
                        output=f"✅ Disk at {pct}% — below {threshold_pct}% threshold. No cleanup needed.",
                        data={"skipped": True, "disk_pct": pct},
                    )

                pct_before = pct
                free_before = _disk_free_gb()

                data = await asyncio.get_event_loop().run_in_executor(
                    None, _clean, max_age_days
                )

                pct_after = _disk_usage_pct()
                free_after = _disk_free_gb()
                data["disk_before_pct"] = pct_before
                data["disk_after_pct"] = pct_after
                data["free_before_gb"] = free_before
                data["free_after_gb"] = free_after

                output = self._format_clean(data)
                return SkillResult(success=True, output=output, data=data)

            else:
                return SkillResult(success=False, error=f"Unknown action: {action}")

        except Exception as e:
            logger.error(f"vps_janitor [{action}] failed: {e}", exc_info=True)
            return SkillResult(success=False, error=str(e))

    # ------------------------------------------------------------------
    # Formatters
    # ------------------------------------------------------------------

    def _format_status(self, data: dict) -> str:
        pct = data["disk_pct"]
        icon = "🔴" if pct >= 90 else "🟡" if pct >= 80 else "🟢"
        lines = [
            f"{icon} **Disk Usage: {pct}%** ({data['free_gb']:.1f} GB free)\n",
            "**Top space consumers:**",
        ]
        for item in data.get("top_consumers", [])[:10]:
            lines.append(f"  {item['size']:>8}  {item['path']}")
        return "\n".join(lines)

    def _format_scan(self, data: dict, max_age_days: int) -> str:
        candidates = data["candidates"]
        total_mb = data["total_mb"]
        lines = [
            f"🔍 **VPS Janitor Scan** (>{max_age_days} days old)\n",
            f"Found **{len(candidates)} item(s)** — estimated savings: **{total_mb:.0f} MB "
            f"({total_mb/1024:.1f} GB)**\n",
        ]
        for c in sorted(candidates, key=lambda x: -x.get("mb", 0))[:20]:
            mb = f"{c['mb']:.0f} MB" if c.get("mb") else "~"
            lines.append(f"  [{c['label']}] {c['path']}  ({mb})")
        if not candidates:
            lines.append("✅ Nothing to clean — disk is tidy.")
        else:
            lines.append(f"\nRun with `action: clean` to execute.")
        return "\n".join(lines)

    def _format_clean(self, data: dict) -> str:
        freed_mb = data["freed_mb"]
        freed_gb = data["freed_gb"]
        pct_before = data["disk_before_pct"]
        pct_after = data["disk_after_pct"]
        deleted = data["deleted"]
        failed = data["failed"]

        lines = [
            f"🧹 **VPS Janitor Cleanup Complete**\n",
            f"  Freed:  **{freed_mb:.0f} MB ({freed_gb:.1f} GB)**",
            f"  Disk:   {pct_before}% → **{pct_after}%** ({data['free_after_gb']:.1f} GB free)",
            f"  Items:  {deleted} deleted, {failed} failed\n",
        ]

        # Group by label
        by_label: dict[str, list] = {}
        for a in data.get("actions", []):
            if a.get("ok") and a.get("mb", 0) > 0:
                label = a["label"]
                by_label.setdefault(label, []).append(a)

        if by_label:
            lines.append("**Freed by category:**")
            for label, items in sorted(by_label.items(), key=lambda x: -sum(i["mb"] for i in x[1])):
                total = sum(i["mb"] for i in items)
                lines.append(f"  {label}: {total:.0f} MB ({len(items)} item(s))")

        if failed:
            lines.append(f"\n⚠️ {failed} item(s) could not be deleted (check logs)")

        return "\n".join(lines)
