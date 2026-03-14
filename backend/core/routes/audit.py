"""
Sanaa AI — Audit log routes: paginated, filterable audit trail.
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, func, and_, cast, String

from core.database import AuditLog, AsyncSessionLocal
from core.routes.deps import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()


def _entry_to_dict(entry: AuditLog) -> dict:
    """Serialize an AuditLog row to a JSON-safe dict."""
    details = entry.details or {}
    return {
        "id": entry.id,
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        "actor": entry.actor,
        "action": entry.action,
        "resource": entry.resource,
        "channel": entry.channel,
        "ip_address": details.get("ip") or entry.ip_address,
        "user_agent": details.get("user_agent"),
        "elapsed_ms": details.get("elapsed_ms"),
        "success": entry.success,
        "error": details.get("error"),
        "details": details,
    }


@router.get("/api/audit-logs")
async def list_audit_logs(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    date_from: Optional[str] = Query(None, description="Start date (ISO format)"),
    date_to: Optional[str] = Query(None, description="End date (ISO format)"),
    action: Optional[str] = Query(None, description="Filter by action type (e.g. GET, POST, PUT, DELETE)"),
    actor: Optional[str] = Query(None, description="Filter by actor (user/IP)"),
    path: Optional[str] = Query(None, description="Filter by resource path (substring match)"),
    success: Optional[bool] = Query(None, description="Filter by success/failure"),
    user: dict = Depends(require_auth),
):
    """List audit log entries with filtering and pagination."""
    async with AsyncSessionLocal() as session:
        # Build filter conditions
        conditions = []

        if date_from:
            try:
                dt_from = datetime.fromisoformat(date_from)
                conditions.append(AuditLog.timestamp >= dt_from)
            except ValueError:
                pass

        if date_to:
            try:
                dt_to = datetime.fromisoformat(date_to)
                conditions.append(AuditLog.timestamp <= dt_to)
            except ValueError:
                pass

        if action:
            # Match the HTTP method part of the action field (e.g. "GET /api/...")
            conditions.append(AuditLog.action.ilike(f"{action}%"))

        if actor:
            conditions.append(AuditLog.actor.ilike(f"%{actor}%"))

        if path:
            conditions.append(AuditLog.resource.ilike(f"%{path}%"))

        if success is not None:
            conditions.append(AuditLog.success == success)

        where_clause = and_(*conditions) if conditions else True

        # Count total
        count_q = select(func.count(AuditLog.id)).where(where_clause)
        total_result = await session.execute(count_q)
        total = total_result.scalar() or 0

        # Fetch page
        offset = (page - 1) * per_page
        data_q = (
            select(AuditLog)
            .where(where_clause)
            .order_by(desc(AuditLog.timestamp))
            .offset(offset)
            .limit(per_page)
        )
        result = await session.execute(data_q)
        entries = result.scalars().all()

    return {
        "items": [_entry_to_dict(e) for e in entries],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
    }


@router.get("/api/audit-logs/{entry_id}")
async def get_audit_log_entry(entry_id: int, user: dict = Depends(require_auth)):
    """Get a single audit log entry by ID."""
    entry = await AuditLog.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Audit log entry not found")
    return _entry_to_dict(entry)
