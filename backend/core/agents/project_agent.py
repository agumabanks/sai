"""
SanaaEngine Project Agent
==========================
Robust Python agent that runs INSIDE each project and reports state to the brain.
Installed as a runnable module: python -m core.agents.project_agent /var/www/finance

Replaces the bash project agent with proper error handling, retries, logging.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("project_agent")

BRAIN_URL = "http://127.0.0.1:8100/api/memory/add"
ENGINE_KEY_FILE = Path("/var/www/ai.sanaa.co/backend/.env")
STALE_HOURS = 24  # Report if project state hasn't changed in 24h


def _get_engine_key() -> Optional[str]:
    try:
        with open(ENGINE_KEY_FILE) as f:
            for line in f:
                if "SANAA_ENGINE_KEY=" in line:
                    return line.split("=", 1)[1].strip()
    except Exception as e:
        logger.error(f"Cannot read engine key: {e}")
    return None


def _detect_project(path: Path) -> dict:
    """Detect project metadata by inspecting the directory."""
    name = path.name
    # Handle finance/mbalala layout
    if (path / "mbalala").exists():
        name = "sanaa_finance"
        path = path / "mbalala"

    stack = []
    if (path / "artisan").exists():
        stack.append("laravel")
    if (path / "pubspec.yaml").exists():
        stack.append("flutter")
    if (path / "package.json").exists():
        stack.append("node")
    if (path / "composer.json").exists():
        stack.append("php")
    if (path / "requirements.txt").exists() or (path / "setup.py").exists():
        stack.append("python")

    return {"name": name, "path": str(path), "stack": ",".join(stack) if stack else "unknown"}


def _get_git_state(path: Path) -> dict:
    """Get git branch, last commit, ahead count."""
    git_dir = path / ".git"
    if not git_dir.exists():
        return {"branch": "no-git", "commit": "", "ahead": 0}

    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(path), capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=str(path), capture_output=True, text=True, timeout=5,
        ).stdout.strip()[:100]
        ahead = subprocess.run(
            ["git", "rev-list", "--count", "@{upstream}..HEAD"],
            cwd=str(path), capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return {"branch": branch, "commit": commit, "ahead": int(ahead) if ahead.isdigit() else 0}
    except Exception as e:
        return {"branch": "error", "commit": str(e), "ahead": 0}


def _get_laravel_state(path: Path) -> dict:
    """Get Laravel-specific state if applicable."""
    if not (path / "artisan").exists():
        return {}

    state = {}
    env_file = path / ".env"
    if env_file.exists():
        try:
            with open(env_file) as f:
                for line in f:
                    if line.startswith("APP_ENV="):
                        state["env"] = line.split("=", 1)[1].strip()
                    elif line.startswith("APP_DEBUG="):
                        state["debug"] = line.split("=", 1)[1].strip()
        except Exception:
            pass

    # Check queue worker
    for svc in [f"{path.name}-worker", "mbalala-worker"]:
        try:
            r = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True, text=True, timeout=3,
            )
            if r.stdout.strip() == "active":
                state["queue"] = "active"
                break
        except Exception:
            pass

    # Check recent errors
    log_dir = path / "storage" / "logs"
    if log_dir.exists():
        error_count = 0
        try:
            result = subprocess.run(
                ["grep", "-c", "ERROR\\|Exception", str(log_dir / "laravel.log")],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                error_count = int(result.stdout.strip() or 0)
        except Exception:
            pass
        if error_count > 0:
            state["recent_errors"] = error_count

    return state


def _build_report(project_path: Path) -> dict:
    """Build a full report for a project."""
    project = _detect_project(project_path)
    git = _get_git_state(Path(project["path"]))
    laravel = _get_laravel_state(Path(project["path"]))

    report = {
        "project": project["name"],
        "stack": project["stack"],
        "path": project["path"],
        "git_branch": git["branch"],
        "git_commit": git["commit"],
        "git_ahead": git["ahead"],
    }
    if laravel.get("env"):
        report["laravel_env"] = laravel["env"]
    if laravel.get("queue"):
        report["queue"] = laravel["queue"]
    if laravel.get("recent_errors"):
        report["errors"] = laravel["recent_errors"]

    return report


def _report_text(report: dict) -> str:
    """Generate a one-line summary for the brain."""
    parts = [f"[Project Agent] {report['project']}: {report['stack']}"]
    parts.append(f"branch={report['git_branch']}")

    if report.get("git_commit"):
        parts.append(f"commit={report['git_commit'][:60]}")
    if report.get("laravel_env"):
        parts.append(f"env={report['laravel_env']}")
    if report.get("queue"):
        parts.append(f"queue={report['queue']}")
    if report.get("errors"):
        parts.append(f"errors={report['errors']}")

    return " | ".join(parts)


async def report_to_brain(report: dict, engine_key: str) -> Optional[int]:
    """Send project report to the brain. Returns memory ID or None."""
    import httpx

    content = _report_text(report)
    meta = {"type": "project_agent_report", "project": report["project"], "stack": report["stack"]}
    if report.get("errors"):
        meta["errors"] = report["errors"]

    payload = {
        "content": content,
        "category": "project_status",
        "project": report["project"],
        "source": "project_agent",
        "confidence": 0.9,
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    BRAIN_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {engine_key}"},
                )
                if resp.status_code == 201:
                    data = resp.json()
                    return data.get("id")
                elif resp.status_code == 409 or (
                    resp.status_code == 200 and resp.json().get("dedup")
                ):
                    return resp.json().get("existing_id")
                else:
                    logger.warning(f"Attempt {attempt+1} failed: HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} error: {e}")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)

    return None


async def run(project_path_str: str) -> dict:
    """Main entry point: scan project and report to brain."""
    path = Path(project_path_str).resolve()
    if not path.exists():
        return {"error": f"Path does not exist: {path}", "project": project_path_str}

    engine_key = _get_engine_key()
    if not engine_key:
        return {"error": "No SANAA_ENGINE_KEY found"}

    report = _build_report(path)
    memory_id = await report_to_brain(report, engine_key)

    result = {
        "project": report["project"],
        "memory_id": memory_id,
        "stack": report["stack"],
        "git_branch": report["git_branch"],
    }
    if report.get("errors"):
        result["errors"] = report["errors"]

    return result


def main():
    """CLI entry point: python -m core.agents.project_agent /var/www/finance"""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: python -m core.agents.project_agent <project-path>")
        sys.exit(1)

    result = asyncio.run(run(sys.argv[1]))
    print(json.dumps(result, indent=2))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
