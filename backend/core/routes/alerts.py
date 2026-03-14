"""
Sanaa AI — Alert routes: list alerts + CRUD for alert rules.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.database import Alert, AlertRule, AsyncSessionLocal
from core.routes.deps import require_auth
from sqlalchemy import select, desc

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Pydantic schemas ─────────────────────────────────────────────────────

class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    condition: str = Field(..., min_length=1, max_length=500)
    threshold: float
    severity: str = Field(..., pattern=r"^(low|medium|high|critical)$")
    recipients: List[str] = Field(..., min_length=1)
    escalation_policy: Optional[dict] = None
    quiet_hours: Optional[dict] = None
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    condition: Optional[str] = Field(None, min_length=1, max_length=500)
    threshold: Optional[float] = None
    severity: Optional[str] = Field(None, pattern=r"^(low|medium|high|critical)$")
    recipients: Optional[List[str]] = None
    escalation_policy: Optional[dict] = None
    quiet_hours: Optional[dict] = None
    enabled: Optional[bool] = None


# ── Helpers ──────────────────────────────────────────────────────────────

def _rule_to_dict(rule: AlertRule) -> dict:
    """Serialize an AlertRule to a JSON-safe dict."""
    return {
        "id": rule.id,
        "name": rule.name,
        "condition": rule.condition,
        "threshold": rule.threshold,
        "severity": rule.severity,
        "recipients": rule.recipients,
        "escalation_policy": rule.escalation_policy,
        "quiet_hours": rule.quiet_hours,
        "enabled": rule.enabled,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


# ── Existing alert list (preserved) ─────────────────────────────────────

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


# ── Alert Rule CRUD ─────────────────────────────────────────────────────

@router.post("/api/alert-rules", status_code=201)
async def create_alert_rule(payload: AlertRuleCreate, user: dict = Depends(require_auth)):
    """Create a new alert rule."""
    rule = await AlertRule.create(
        name=payload.name,
        condition=payload.condition,
        threshold=payload.threshold,
        severity=payload.severity,
        recipients=payload.recipients,
        escalation_policy=payload.escalation_policy,
        quiet_hours=payload.quiet_hours,
        enabled=payload.enabled,
    )
    return _rule_to_dict(rule)


@router.get("/api/alert-rules")
async def list_alert_rules(user: dict = Depends(require_auth)):
    """List all alert rules."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AlertRule).order_by(desc(AlertRule.created_at))
        )
        rules = result.scalars().all()
    return [_rule_to_dict(r) for r in rules]


@router.get("/api/alert-rules/{rule_id}")
async def get_alert_rule(rule_id: int, user: dict = Depends(require_auth)):
    """Get a single alert rule by ID."""
    rule = await AlertRule.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return _rule_to_dict(rule)


@router.put("/api/alert-rules/{rule_id}")
async def update_alert_rule(rule_id: int, payload: AlertRuleUpdate, user: dict = Depends(require_auth)):
    """Update an existing alert rule (partial update)."""
    rule = await AlertRule.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = await AlertRule.update_by_id(rule_id, **update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Alert rule not found")

    return _rule_to_dict(updated)


@router.delete("/api/alert-rules/{rule_id}")
async def delete_alert_rule(rule_id: int, user: dict = Depends(require_auth)):
    """Delete an alert rule."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AlertRule).where(AlertRule.id == rule_id)
        )
        rule = result.scalars().first()
        if not rule:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        await session.delete(rule)
        await session.commit()

    return {"detail": "Alert rule deleted", "id": rule_id}
