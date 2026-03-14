"""
Sanaa AI — Session routes: list, detail, reset, send-policy.
"""

import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core.database import AuditLog
from core.routes.deps import require_auth
from core.policies import (
    get_session_policy,
    list_sessions,
    get_session_detail,
    reset_session_by_id,
    set_session_send_override,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class SessionSendPolicyRequest(BaseModel):
    mode: str  # on|off|inherit


@router.get("/api/sessions")
async def list_sessions_api(limit: int = 100, user: dict = Depends(require_auth)):
    """List recent sessions with basic metadata and send overrides."""
    sessions = await list_sessions(limit=limit)
    return {"count": len(sessions), "sessions": sessions, "policy": await get_session_policy()}


@router.get("/api/sessions/{session_id}")
async def get_session_detail_api(session_id: str, user: dict = Depends(require_auth)):
    """Get recent messages and policy context for a session."""
    try:
        return await get_session_detail(session_id, limit=100)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/api/sessions/{session_id}/reset")
async def reset_session_api(session_id: str, user: dict = Depends(require_auth)):
    """Rotate a session route to a new session ID."""
    try:
        data = await reset_session_by_id(session_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    try:
        await AuditLog.log(
            actor=user.get("email", "admin"),
            action="session.reset",
            resource=session_id,
            details=data,
            success=True,
        )
    except Exception:
        pass
    return {"status": "success", **data}


@router.post("/api/sessions/{session_id}/send-policy")
async def set_session_send_policy_api(session_id: str, body: SessionSendPolicyRequest, user: dict = Depends(require_auth)):
    """Set per-session send override (on|off|inherit)."""
    try:
        mode = await set_session_send_override(session_id, body.mode, source="admin_dashboard")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "success", "session_id": session_id, "mode": mode}
