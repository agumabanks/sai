"""
Sanaa OS — Container App Launcher
On-demand Docker Compose apps that boot when opened and stop when closed.
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from typing import Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.routes.deps import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()

APPS_BASE = "/var/www/ai.sanaa.co/apps"

# App registry: each entry defines how to launch and health-check a container app
CONTAINER_APPS: Dict[str, dict] = {
    "vaultwarden": {
        "name": "Sanaa Vault",
        "dir": "vaultwarden",
        "port": 8201,
        "health_path": "/vault/api/alive",
        "boot_timeout": 15,
        "proxy_path": "/vault/",
    },
    "metabase": {
        "name": "Sanaa Insights",
        "dir": "metabase",
        "port": 8202,
        "health_path": "/api/health",
        "boot_timeout": 60,
        "proxy_path": "/insights/",
    },
    "bookstack": {
        "name": "Sanaa Library",
        "dir": "bookstack",
        "port": 8203,
        "health_path": "/login",
        "boot_timeout": 30,
        "proxy_path": "/library/",
    },
    "penpot": {
        "name": "Sanaa Studio",
        "dir": "penpot",
        "port": 8204,
        "health_path": "/api/rpc/command/get-profile",
        "boot_timeout": 45,
        "proxy_path": "/studio/",
    },
    "jitsi": {
        "name": "Sanaa Meet",
        "dir": "jitsi",
        "port": 8205,
        "health_path": "/",
        "boot_timeout": 90,
        "proxy_path": "/meet/",
    },
    "erpnext": {
        "name": "Sanaa ERP",
        "dir": "erpnext",
        "port": 8206,
        "health_path": "/api/method/ping",
        "boot_timeout": 180,
        "proxy_path": "/erp/",
    },
}

# Track runtime state per app
_app_state: Dict[str, dict] = {}


def _app_dir(app_id: str) -> str:
    if app_id not in CONTAINER_APPS:
        raise HTTPException(404, f"Unknown app: {app_id}")
    return os.path.join(APPS_BASE, CONTAINER_APPS[app_id]["dir"])


def _run(cmd: list, cwd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a shell command safely."""
    try:
        return subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"Command timed out: {' '.join(cmd)}")


@router.get("/api/apps/launcher/registry")
async def list_container_apps(user: dict = Depends(require_auth)):
    """List all available container apps with their status."""
    result = []
    for app_id, cfg in CONTAINER_APPS.items():
        state = _app_state.get(app_id, {})
        result.append({
            "id": app_id,
            "name": cfg["name"],
            "status": state.get("status", "stopped"),
            "boot_timeout": cfg["boot_timeout"],
            "proxy_path": cfg["proxy_path"],
        })
    return {"apps": result}


@router.post("/api/apps/launcher/{app_id}/start")
async def start_app(app_id: str, user: dict = Depends(require_auth)):
    """Start a container app's Docker Compose stack."""
    cfg = CONTAINER_APPS.get(app_id)
    if not cfg:
        raise HTTPException(404, f"Unknown app: {app_id}")

    app_dir = _app_dir(app_id)
    if not os.path.isfile(os.path.join(app_dir, "docker-compose.yml")):
        raise HTTPException(503, f"App not deployed: {app_id}")

    state = _app_state.setdefault(app_id, {})
    state["started_by"] = user.get("email")
    state["started_at"] = time.time()
    state["status"] = "booting"

    # docker compose up -d
    proc = _run(["docker", "compose", "up", "-d", "--remove-orphans"], cwd=app_dir, timeout=120)
    if proc.returncode != 0:
        state["status"] = "error"
        state["error"] = proc.stderr or proc.stdout
        logger.error(f"Failed to start {app_id}: {proc.stderr}")
        raise HTTPException(500, f"Failed to start {app_id}: {proc.stderr}")

    logger.info(f"Started container app {app_id} for {user.get('email')}")
    return {"status": "booting", "app": app_id, "timeout": cfg["boot_timeout"]}


@router.get("/api/apps/launcher/{app_id}/status")
async def app_status(app_id: str, user: dict = Depends(require_auth)):
    """Check if a container app is ready."""
    cfg = CONTAINER_APPS.get(app_id)
    if not cfg:
        raise HTTPException(404, f"Unknown app: {app_id}")

    app_dir = _app_dir(app_id)
    state = _app_state.get(app_id, {})

    # Check if containers are actually running
    proc = _run(["docker", "compose", "ps", "--format", "json"], cwd=app_dir, timeout=15)
    containers = []
    if proc.returncode == 0 and proc.stdout.strip():
        try:
            raw = json.loads(proc.stdout)
            containers = raw if isinstance(raw, list) else [raw]
        except json.JSONDecodeError:
            # docker compose ps --format json sometimes outputs NDJSON
            for line in proc.stdout.strip().splitlines():
                if line.strip():
                    try:
                        containers.append(json.loads(line))
                    except Exception:
                        pass

    running = any(c.get("State") == "running" for c in containers)

    if not running:
        state["status"] = "stopped"
        return {"status": "stopped", "app": app_id, "running_containers": 0}

    # Health-check via HTTP if we have a port
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"http://127.0.0.1:{cfg['port']}{cfg['health_path']}",
                follow_redirects=True,
            )
            if resp.status_code < 500:
                state["status"] = "ready"
                return {
                    "status": "ready",
                    "app": app_id,
                    "url": cfg["proxy_path"],
                    "running_containers": len(containers),
                }
    except Exception:
        pass

    state["status"] = "booting"
    elapsed = time.time() - state.get("started_at", 0)
    return {
        "status": "booting",
        "app": app_id,
        "elapsed": round(elapsed, 1),
        "timeout": cfg["boot_timeout"],
        "running_containers": len(containers),
    }


@router.post("/api/apps/launcher/{app_id}/stop")
async def stop_app(app_id: str, user: dict = Depends(require_auth)):
    """Stop a container app's Docker Compose stack."""
    cfg = CONTAINER_APPS.get(app_id)
    if not cfg:
        raise HTTPException(404, f"Unknown app: {app_id}")

    app_dir = _app_dir(app_id)
    state = _app_state.get(app_id, {})

    proc = _run(["docker", "compose", "down"], cwd=app_dir, timeout=60)
    if proc.returncode != 0:
        logger.warning(f"Stop {app_id} had issues: {proc.stderr}")

    state["status"] = "stopped"
    state.pop("started_at", None)
    logger.info(f"Stopped container app {app_id}")
    return {"status": "stopped", "app": app_id}


# Auto-stop idle apps after 10 minutes of inactivity
async def _auto_stop_idle_apps():
    """Background task: stop apps that have been idle > 10 minutes."""
    while True:
        await asyncio.sleep(60)
        now = time.time()
        for app_id, state in list(_app_state.items()):
            if state.get("status") != "ready":
                continue
            started_at = state.get("started_at", 0)
            if now - started_at > 600:  # 10 minutes
                cfg = CONTAINER_APPS.get(app_id)
                if cfg:
                    app_dir = _app_dir(app_id)
                    _run(["docker", "compose", "down"], cwd=app_dir, timeout=60)
                    state["status"] = "stopped"
                    logger.info(f"Auto-stopped idle app {app_id}")


@router.on_event("startup")
async def _start_auto_stop():
    asyncio.create_task(_auto_stop_idle_apps())
