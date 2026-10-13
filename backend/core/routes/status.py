"""
Sanaa AI — Status routes: health, system status, doctor, activities.
"""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from core.config import get_settings
from core.database import Alert, Command, DeviceReport, SystemKnowledge, AsyncSessionLocal
from core.routes import deps
from core.routes.deps import require_auth
from core.policies import run_doctor

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


@router.get("/api/health")
async def api_health():
    """Public health check (no auth required)."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": "2.2.0",
        "channels": list(deps.router_instance.channels.keys()),
    }


@router.get("/api/status")
async def api_status(user: dict = Depends(require_auth)):
    """Full system status."""

    health = await deps.server_health.get_snapshot()
    alerts = await Alert.get_recent(limit=50)
    devices = await DeviceReport.get_latest_all()

    brain_provider = await SystemKnowledge.get_pref("brain.provider", default="auto")

    fail_counts = []
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SystemKnowledge).where(SystemKnowledge.key.like("fail_count.%"))
        )
        for obj in result.scalars().all():
            if obj.value and int(obj.value) > 0:
                fail_counts.append({"metric": obj.key, "count": int(obj.value)})

    return {
        "server": health,
        "brain": {
            "active_provider": brain_provider,
            "status": "ready",
        },
        "healer": {
            "active_failures": fail_counts,
            "tier_thresholds": {
                "t2": deps.healer.TIER_2_THRESHOLD,
                "t3": deps.healer.TIER_3_THRESHOLD,
                "t4": deps.healer.TIER_4_THRESHOLD,
            },
        },
        "alerts": {
            "unacknowledged": len([a for a in alerts if not getattr(a, "acknowledged", False)]),
            "recent": len(alerts),
        },
        "devices": {
            "active": len(devices),
        },
        "channels": deps.router_instance.get_channel_status(),
    }


@router.get("/api/system/doctor")
async def get_system_doctor_api(user: dict = Depends(require_auth)):
    """Run doctor-style safety/config audit checks."""
    return await run_doctor(brain=deps.brain, workflow_loader=deps.workflow_loader)


@router.post("/api/system/doctor/run")
async def run_system_doctor_api(user: dict = Depends(require_auth)):
    """Explicit doctor run endpoint (same output as GET)."""
    return await run_doctor(brain=deps.brain, workflow_loader=deps.workflow_loader)


@router.get("/api/activities")
async def get_activities(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    user: dict = Depends(require_auth),
):
    """Get recent system activities for the dashboard feed."""
    activities = []

    for e in deps.get_recent_events(limit=limit, offset=offset):
        severity = e.get("severity", "info")
        icon = {
            "critical": "heroicon-m-exclamation-triangle",
            "high": "heroicon-m-exclamation-circle",
            "warning": "heroicon-m-shield-exclamation",
            "info": "heroicon-m-information-circle",
        }.get(severity, "heroicon-m-information-circle")
        status = "error" if severity in ("critical", "high") else "warning" if severity == "warning" else "success"
        activities.append({
            "type": "watchdog",
            "title": e.get("category", "Watchdog Event"),
            "description": e.get("message", ""),
            "time": e.get("timestamp", ""),
            "status": status,
            "icon": icon,
        })

    alerts = await Alert.get_recent(limit=limit)
    for a in alerts:
        status = "error" if a.severity in ("critical", "high") else "warning" if a.severity == "warning" else "info"
        activities.append({
            "type": "alert",
            "title": f"Alert: {a.metric or 'System'}",
            "description": a.message,
            "time": a.created_at.isoformat() if a.created_at else "",
            "status": status,
            "icon": "heroicon-m-bell-alert",
        })

    commands = await Command.get_recent(limit=limit)
    for c in commands:
        activities.append({
            "type": "command",
            "title": "Command Executed",
            "description": (c.text or "")[:100],
            "time": c.created_at.isoformat() if c.created_at else "",
            "status": "success" if c.status == "completed" else "error" if c.status == "failed" else "info",
            "icon": "heroicon-m-command-line",
        })

    activities.sort(key=lambda x: x.get("time", ""), reverse=True)
    return activities[:limit]
