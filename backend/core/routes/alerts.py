"""
Sanaa AI — Alert routes: list alerts.
"""

import logging

from fastapi import APIRouter, Depends, Request

from core.database import Alert
from core.routes.deps import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/alerts")
async def list_alerts(request: Request, limit: int = 50, user: dict = Depends(require_auth)):
    alerts = await Alert.get_recent(limit=limit)
    return [
        {
            "id": a.id,
            "severity": a.severity,
            "message": a.message,
            "metric": a.metric,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]
