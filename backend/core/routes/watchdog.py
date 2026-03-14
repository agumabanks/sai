"""
Sanaa AI — Watchdog routes: events, run, live feed.
"""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from core.database import Alert
from core.routes import deps
from core.routes.deps import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/watchdog/events")
async def get_watchdog_events(request: Request, user: dict = Depends(require_auth)):
    """Get recent watchdog events for the live feed."""
    return deps._recent_events


@router.post("/api/watchdog/run")
async def run_watchdog_now(request: Request, user: dict = Depends(require_auth)):
    """Manually trigger a watchdog check + heal cycle."""
    from core.routes import deps

    events, checked_metrics = await deps.watchdog.run_full_check()
    event_dicts = [e.to_dict() for e in events]

    # Store in recent events — mutate the shared list in deps
    deps._recent_events[:] = (event_dicts + deps._recent_events)[:deps.MAX_EVENTS]

    # Auto-heal
    actions = await deps.healer.process_events(events, checked_metrics)

    # Persist critical alerts to database
    for e in events:
        if e.severity in ("critical", "high"):
            await Alert.create(
                severity=e.severity,
                message=e.message,
                metric=e.metric,
            )

    if "hx-request" in request.headers:
        if not events:
            return HTMLResponse(
                '<div class="text-green-400 text-sm p-2">All clear — no issues detected</div>'
            )
        html_parts = []
        for e in events:
            color = {
                "critical": "text-red-400", "high": "text-orange-400",
                "warning": "text-yellow-400", "info": "text-blue-300",
            }.get(e.severity, "text-gray-400")
            badge_bg = {
                "critical": "bg-red-900/50", "high": "bg-orange-900/50",
                "warning": "bg-yellow-900/50", "info": "bg-blue-900/50",
            }.get(e.severity, "bg-gray-800")
            html_parts.append(
                f'<div class="flex items-start gap-2 p-2 rounded bg-gray-900/50 text-sm">'
                f'<span class="shrink-0 px-1.5 py-0.5 rounded text-xs {badge_bg} {color}">{e.severity}</span>'
                f'<span class="{color}">{e.message}</span>'
                f'</div>'
            )
        if actions:
            for a in actions:
                status = "text-green-400" if a.get("success") else "text-red-400"
                html_parts.append(
                    f'<div class="flex items-start gap-2 p-2 rounded bg-gray-900/50 text-sm">'
                    f'<span class="shrink-0 px-1.5 py-0.5 rounded text-xs bg-purple-900/50 text-purple-400">healed</span>'
                    f'<span class="{status}">{a["action"]}: {a.get("target", "")} — {"OK" if a.get("success") else "FAILED"}</span>'
                    f'</div>'
                )
        return HTMLResponse("\n".join(html_parts))

    return {
        "events": event_dicts,
        "actions": actions,
        "event_count": len(events),
        "critical_count": len([e for e in events if e.severity == "critical"]),
    }


@router.get("/api/watchdog/events-feed")
async def watchdog_events_htmx(request: Request, user: dict = Depends(require_auth)):
    """htmx-friendly live event feed fragment."""

    if not deps._recent_events:
        return HTMLResponse(
            '<div class="text-gray-500 text-sm italic p-3 text-center">No events yet — waiting for next watchdog cycle</div>'
        )

    html_parts = []
    for e in deps._recent_events[:15]:
        color = {
            "critical": "text-red-400", "high": "text-orange-400",
            "warning": "text-yellow-400", "info": "text-blue-300",
        }.get(e.get("severity", ""), "text-gray-400")
        badge_bg = {
            "critical": "bg-red-900/50", "high": "bg-orange-900/50",
            "warning": "bg-yellow-900/50", "info": "bg-blue-900/50",
        }.get(e.get("severity", ""), "bg-gray-800")
        ts = e.get("timestamp", "")[:19].replace("T", " ")
        html_parts.append(
            f'<div class="flex items-start gap-2 p-2 rounded bg-gray-900/50 text-sm">'
            f'<span class="shrink-0 px-1.5 py-0.5 rounded text-xs {badge_bg} {color}">{e.get("severity","")}</span>'
            f'<div class="flex-1">'
            f'<span class="{color}">{e.get("message","")}</span>'
            f'<div class="text-xs text-gray-600 mt-0.5">{ts} &middot; {e.get("category","")}</div>'
            f'</div>'
            f'</div>'
        )
    return HTMLResponse("\n".join(html_parts))
