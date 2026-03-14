"""
Sanaa AI — Intelligence routes: briefings, signals, wisdom, scan.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from sqlalchemy import select, desc

from core.database import IntelligenceBriefing, StrategicSignal, SystemKnowledge, AsyncSessionLocal
from core.routes import deps
from core.routes.deps import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/intelligence/latest-signals")
async def get_latest_signals(limit: int = 10, user: dict = Depends(require_auth)):
    """Fetch structured strategic signals for the dashboard."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(StrategicSignal)
            .order_by(desc(StrategicSignal.created_at))
            .limit(limit)
        )
        signals = result.scalars().all()
        return [
            {
                "id": s.id,
                "title": s.title,
                "summary": s.summary,
                "score": s.score,
                "classification": s.classification,
                "business_impact": s.business_impact,
                "source": s.source,
                "link": s.link,
                "tags": s.tags,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in signals
        ]


@router.get("/api/intelligence/wisdom")
async def get_system_wisdom(user: dict = Depends(require_auth)):
    """Fetch the latest architectural wisdom/insight from the WisdomAgent."""
    from core.agents.wisdom import WisdomAgent
    agent = WisdomAgent()
    wisdom = await agent.get_latest_insight()
    return wisdom or {"message": "System is too stable to provide specific wisdom yet."}


@router.get("/api/intelligence/advisor/watchdog")
async def get_watchdog_advisor(user: dict = Depends(require_auth)):
    """Fetch the latest sanaa-clade watchdog advisory."""
    val = await SystemKnowledge.get_pref("watchdog.advisor.latest", default=None, domain="wisdom")
    if not val:
        return {"message": "No watchdog advisory available yet."}
    try:
        return json.loads(val)
    except Exception:
        return {"raw": val}


@router.get("/api/intelligence/briefings/qa/latest")
async def get_latest_briefing_qa(user: dict = Depends(require_auth)):
    """Fetch the latest news briefing QA/repair assessment."""
    val = await SystemKnowledge.get_pref("briefing.latest.qa", default=None, domain="news")
    if not val:
        return {"message": "No briefing QA available yet."}
    try:
        return json.loads(val)
    except Exception:
        return {"raw": val}


@router.get("/api/intelligence/briefings")
async def list_briefings(request: Request, limit: int = 20):
    user = require_auth(request)
    briefings = await IntelligenceBriefing.get_recent(limit=limit)
    return [
        {
            "id": b.id,
            "title": b.title,
            "created_at": b.created_at.isoformat(),
            "metadata": b.metadata_ or {"article_count": 0},
            "pdf_path": b.pdf_path,
        }
        for b in briefings
    ]


@router.get("/api/intelligence/latest-signal")
async def get_latest_signal(request: Request):
    """Internal API for FAB badge."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(StrategicSignal).order_by(StrategicSignal.created_at.desc()).limit(1)
        )
        signal = result.scalars().first()
        if not signal:
            return {"status": "none"}
        return {
            "id": signal.id,
            "title": signal.title,
            "score": signal.score,
            "created_at": signal.created_at.isoformat(),
        }


@router.get("/api/intelligence/briefing/{id}")
async def get_briefing(id: int, request: Request):
    user = require_auth(request)
    briefing = await IntelligenceBriefing.get(id)
    if not briefing:
        raise HTTPException(404)
    return {
        "title": briefing.title,
        "content": briefing.content,
        "created_at": briefing.created_at.isoformat(),
        "pdf_path": briefing.pdf_path,
    }


@router.post("/api/intelligence/scan")
async def trigger_scan(request: Request, background_tasks: BackgroundTasks, user: dict = Depends(require_auth)):
    """Trigger an autonomous intelligence scan."""
    background_tasks.add_task(deps.scanner.scan_all)
    if "hx-request" in request.headers:
        return HTMLResponse('<div class="text-2xl font-bold text-blue-400 animate-pulse">Scanning...</div>')
    return {"status": "started", "message": "Intelligence scan initiated"}
