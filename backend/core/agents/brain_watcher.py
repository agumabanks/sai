"""
SanaaEngine Brain Watcher
==========================
Self-learning agent that autonomously scans the VPS for changes and
creates memory entries. Runs on a Celery schedule.

Scans:
  1. /var/www/ project directories — detect new/modified projects
  2. Skills directory — detect new/modified skills
  3. Recent git commits across projects
  4. File changes in monitored directories
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Projects to monitor
VPS_ROOT = Path("/var/www")
KNOWN_PROJECTS = {
    "sanaa_finance": VPS_ROOT / "finance",
    "soko24": VPS_ROOT / "soko24",
    "farzone": VPS_ROOT / "farzone",
    "baraka24": VPS_ROOT / "baraka24",
    "antigravity": VPS_ROOT / "ai.sanaa.co",
}
SKILLS_DIR = VPS_ROOT / "ai.sanaa.co" / "backend" / "skills"
BRAIN_API = "http://127.0.0.1:8100/api/memory/add"
ENGINE_KEY_FILE = VPS_ROOT / "ai.sanaa.co" / "backend" / ".env"


def _get_engine_key() -> Optional[str]:
    """Read SANAA_ENGINE_KEY from .env."""
    try:
        with open(ENGINE_KEY_FILE) as f:
            for line in f:
                if "SANAA_ENGINE_KEY=" in line:
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _discover_projects() -> list[dict]:
    """Scan /var/www/ for project directories with meaningful content."""
    projects = []
    try:
        for entry in sorted(VPS_ROOT.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name
            # Skip system dirs
            if name.startswith(".") or name in ("cloud-cache", "backups"):
                continue

            # Check for meaningful content
            has_backend = (
                (entry / "app").exists()
                or (entry / "backend").exists()
                or (entry / "mbalala" / "app").exists()
            )
            has_frontend = (
                (entry / "resources" / "js").exists()
                or (entry / "frontend").exists()
            )
            is_flutter = (
                list(entry.glob("*.dart")) != []
                or (entry / "lib").exists()
                or (entry / "android").exists()
            )

            # Count files
            file_count = sum(1 for _ in entry.rglob("*") if _.is_file())

            projects.append({
                "name": name,
                "path": str(entry),
                "has_backend": has_backend,
                "has_frontend": has_frontend,
                "is_flutter": is_flutter,
                "file_count": file_count,
                "detected_at": _utcnow_iso(),
            })
    except Exception as e:
        logger.error(f"Project discovery failed: {e}")

    return projects


def _discover_skills() -> list[dict]:
    """Scan skills directory and return metadata about each skill."""
    skills = []
    try:
        for entry in sorted(SKILLS_DIR.iterdir()):
            if not entry.is_dir() or entry.name.startswith("__"):
                continue

            py_files = list(entry.glob("*.py"))
            yaml_files = list(entry.glob("*.yaml")) + list(entry.glob("*.yml"))
            has_main = (entry / "main.py").exists()
            has_handler = (entry / "handler.py").exists()

            # Extract skill name from first py file
            description = ""
            for pf in py_files[:1]:
                try:
                    with open(pf) as f:
                        first_lines = f.read()[:500]
                    for line in first_lines.split("\n"):
                        if '"""' in line or "# " in line:
                            description = line.strip(' "#"""')
                            break
                except Exception:
                    pass

            skills.append({
                "name": entry.name,
                "path": str(entry),
                "py_files": len(py_files),
                "has_main": has_main,
                "has_handler": has_handler,
                "has_yaml": len(yaml_files) > 0,
                "description": description[:100],
                "detected_at": _utcnow_iso(),
            })
    except Exception as e:
        logger.error(f"Skill discovery failed: {e}")

    return skills


def _check_adb_devices() -> list[dict]:
    """Check connected Android devices via ADB."""
    devices = []
    try:
        result = subprocess.run(
            ["adb", "devices", "-l"],
            capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().split("\n")
        for line in lines[1:]:  # skip "List of devices attached"
            line = line.strip()
            if not line or "no permissions" in line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                device_id = parts[0]
                status = parts[1]
                model = ""
                for p in parts[2:]:
                    if p.startswith("model:"):
                        model = p.replace("model:", "", 1)
                devices.append({
                    "id": device_id,
                    "status": status,
                    "model": model,
                    "detected_at": _utcnow_iso(),
                })
    except FileNotFoundError:
        pass  # ADB not installed
    except Exception as e:
        logger.debug(f"ADB check failed: {e}")
    return devices


def _check_git_changes(project_path: Path, hours: int = 24) -> list[dict]:
    """Check recent git commits in a project directory."""
    changes = []
    git_dir = project_path / ".git"
    if not git_dir.exists():
        return changes

    try:
        result = subprocess.run(
            ["git", "log", f"--since={hours} hours ago", "--oneline", "-20"],
            cwd=str(project_path),
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                parts = line.strip().split(" ", 1)
                changes.append({
                    "hash": parts[0] if len(parts) > 0 else "?",
                    "message": parts[1] if len(parts) > 1 else line.strip(),
                })
    except Exception as e:
        logger.debug(f"Git check failed for {project_path.name}: {e}")

    return changes


async def scan_and_learn(hours_back: int = 24) -> dict:
    """
    Main entry point. Scans VPS and creates memory entries.
    Called by Celery task or directly.
    """
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    engine_key = _get_engine_key()
    if not engine_key:
        logger.warning("No SANAA_ENGINE_KEY found, cannot store memories")
        return {"error": "no_engine_key"}

    memories_created = 0
    findings = []
    changes_found = 0

    # 1. Discover projects
    projects = _discover_projects()
    findings.append(f"Scanned {len(projects)} VPS projects")

    # Check each known project for git changes
    for proj_name, proj_path in KNOWN_PROJECTS.items():
        if proj_path.exists():
            commits = _check_git_changes(proj_path, hours=hours_back)
            if commits:
                changes_found += len(commits)
                content = (
                    f"[Brain Watcher] {proj_name}: {len(commits)} commits "
                    f"in the last {hours_back}h. Latest: {commits[0]['message'][:100]}"
                )
                try:
                    async with AsyncSessionLocal() as session:
                        await session.execute(
                            text("""
                                INSERT INTO agent_memory
                                    (content, category, source, confidence, metadata,
                                     created_at, updated_at, access_count, verified)
                                VALUES
                                    (:content, 'vcs_change', 'brain_watcher', 0.85, :meta,
                                     NOW(), NOW(), 0, false)
                            """),
                            {
                                "content": content,
                                "meta": json.dumps({
                                    "project": proj_name,
                                    "type": "git_commits",
                                    "commit_count": len(commits),
                                    "latest": commits[0]["message"][:100],
                                    "hours_back": hours_back,
                                }),
                            },
                        )
                        await session.commit()
                    memories_created += 1
                except Exception as e:
                    logger.warning(f"Failed to store git change memory: {e}")

    # 2. Discover skills
    skills = _discover_skills()
    findings.append(f"Scanned {len(skills)} skills")

    # Store skill summary if significant
    new_skills = [s for s in skills if s["py_files"] > 0]
    if new_skills:
        categories = {}
        for s in new_skills:
            prefix = s["name"].split("_")[0] if "_" in s["name"] else s["name"][:5]
            categories[prefix] = categories.get(prefix, 0) + 1

        content = (
            f"[Brain Watcher] Skills fleet: {len(new_skills)} active skills. "
            f"Categories: {json.dumps(categories)}."
        )
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("""
                        INSERT INTO agent_memory
                            (content, category, source, confidence, metadata,
                             created_at, updated_at, access_count, verified)
                        VALUES
                            (:content, 'skill_fleet', 'brain_watcher', 0.9, :meta,
                             NOW(), NOW(), 0, false)
                    """),
                    {
                        "content": content,
                        "meta": json.dumps({
                            "type": "skill_fleet_snapshot",
                            "total": len(new_skills),
                            "categories": categories,
                            "scanned_at": _utcnow_iso(),
                        }),
                    },
                )
                await session.commit()
            memories_created += 1
        except Exception as e:
            logger.warning(f"Failed to store skill fleet memory: {e}")

    # 3. Check for new projects (not in KNOWN_PROJECTS)
    known_names = set(KNOWN_PROJECTS.keys())
    new_projects = [
        p for p in projects
        if p["name"] not in known_names
        and p["file_count"] > 10
        and p["name"] not in ("ai.sanaa.co",)
    ]
    if new_projects:
        for np in new_projects[:5]:
            content = f"[Brain Watcher] New project detected: {np['name']} at {np['path']} ({np['file_count']} files)"
            try:
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        text("""
                            INSERT INTO agent_memory
                                (content, category, source, confidence, metadata,
                                 created_at, updated_at, access_count, verified)
                            VALUES
                                (:content, 'project_discovery', 'brain_watcher', 0.8, :meta,
                                 NOW(), NOW(), 0, false)
                        """),
                        {
                            "content": content,
                            "meta": json.dumps({
                                "project": np["name"],
                                "path": np["path"],
                                "type": "new_project",
                                "file_count": np["file_count"],
                                "has_backend": np["has_backend"],
                                "is_flutter": np["is_flutter"],
                            }),
                        },
                    )
                    await session.commit()
                memories_created += 1
            except Exception as e:
                logger.warning(f"Failed to store new project memory: {e}")

    # 4. Check ADB devices (scrcpy-inspired — watch connected Android devices)
    devices_found = 0
    try:
        adb_devices = _check_adb_devices()
        if adb_devices:
            devices_found = len(adb_devices)
            for dev in adb_devices[:3]:
                content = (
                    f"[Brain Watcher] ADB device {'connected' if dev['status'] == 'device' else dev['status']}: "
                    f"{dev['model'] or dev['id'][:20]}"
                )
                try:
                    async with AsyncSessionLocal() as session:
                        await session.execute(
                            text("""
                                INSERT INTO agent_memory
                                    (content, category, source, confidence, metadata,
                                     created_at, updated_at, access_count, verified)
                                VALUES
                                    (:content, 'device_status', 'brain_watcher', 0.9, :meta,
                                     NOW(), NOW(), 0, false)
                            """),
                            {
                                "content": content,
                                "meta": json.dumps({
                                    "type": "adb_device",
                                    "device_id": dev["id"][:30],
                                    "model": dev["model"],
                                    "status": dev["status"],
                                }),
                            },
                        )
                        await session.commit()
                    memories_created += 1
                except Exception as e:
                    logger.warning(f"Failed to store ADB device memory: {e}")
    except Exception as e:
        logger.debug(f"ADB check failed: {e}")

    logger.info(
        f"Brain Watcher scan complete: {memories_created} memories, "
        f"{changes_found} changes, {len(findings)} findings, "
        f"{devices_found} ADB devices"
    )
    return {
        "memories_created": memories_created,
        "changes_found": changes_found,
        "projects_scanned": len(projects),
        "skills_scanned": len(skills),
        "new_projects": len(new_projects),
        "adb_devices": devices_found,
    }
