"""
Sanaa AI — Skills routes: listing, running, enabling/disabling, ML endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from core.routes import deps
from core.routes.deps import require_auth
from core.policies import (
    get_tool_policy,
    build_skill_catalog,
    set_skill_enabled,
    set_skill_exposure,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class SkillRunRequest(BaseModel):
    args: dict = Field(default_factory=dict)
    session_id: Optional[str] = None
    channel: str = "web"
    sender_id: str = "admin"


class SkillExposureUpdateRequest(BaseModel):
    exposure: str


class SkillFeedbackRequest(BaseModel):
    rating: int = Field(..., ge=-1, le=5)
    feedback_type: str = "thumbs"
    comment: Optional[str] = None
    skill_run_id: Optional[int] = None
    session_id: Optional[str] = None
    input_args: Optional[dict] = None
    output_snapshot: Optional[str] = None


@router.get("/api/skills")
async def list_skills_api(user: dict = Depends(require_auth)):
    """List loaded skills and their schemas for dashboard/operator use."""
    await deps.brain.ensure_skills_loaded()
    effective_provider = deps.brain.get_effective_tool_provider() if hasattr(deps.brain, "get_effective_tool_provider") else deps.brain.get_current_provider()
    catalog = await build_skill_catalog(deps.brain.skill_registry, provider=effective_provider, channel="web")
    return {
        "count": deps.brain.skill_registry.count,
        "skills": catalog,
        "tools": deps.brain.skill_registry.list_tools(),
        "tool_policy": await get_tool_policy(),
        "effective_provider": effective_provider,
    }


@router.post("/api/skills/{skill_name}/run")
async def run_skill_api(skill_name: str, body: SkillRunRequest, user: dict = Depends(require_auth)):
    """Run a specific skill on demand."""
    await deps.brain.ensure_skills_loaded()
    result = await deps.brain.execute_skill(
        name=skill_name,
        args=body.args or {},
        session_id=body.session_id or f"skill:{skill_name}",
        channel=body.channel or "web",
        sender_id=body.sender_id or user.get("email", "admin"),
        execution_mode="manual",
        sender_role=user.get("role", "operator"),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/api/skills/{skill_name}/enable")
async def enable_skill_api(skill_name: str, user: dict = Depends(require_auth)):
    await deps.brain.ensure_skills_loaded()
    if not deps.brain.skill_registry.get(skill_name):
        raise HTTPException(404, "Skill not found")
    data = await set_skill_enabled(skill_name, True, source="admin_dashboard")
    return {"skill": skill_name, **data}


@router.post("/api/skills/{skill_name}/disable")
async def disable_skill_api(skill_name: str, user: dict = Depends(require_auth)):
    await deps.brain.ensure_skills_loaded()
    if not deps.brain.skill_registry.get(skill_name):
        raise HTTPException(404, "Skill not found")
    data = await set_skill_enabled(skill_name, False, source="admin_dashboard")
    return {"skill": skill_name, **data}


@router.post("/api/skills/{skill_name}/exposure")
async def set_skill_exposure_api(skill_name: str, body: SkillExposureUpdateRequest, user: dict = Depends(require_auth)):
    await deps.brain.ensure_skills_loaded()
    if not deps.brain.skill_registry.get(skill_name):
        raise HTTPException(404, "Skill not found")
    try:
        data = await set_skill_exposure(skill_name, body.exposure, source="admin_dashboard")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"skill": skill_name, **data}


# ==================== ML SELF-LEARNING ENDPOINTS ====================

@router.get("/api/skills/ml/scores")
async def skill_ml_scores_api(user: dict = Depends(require_auth)):
    """Get ML performance scores for all skills."""
    from core.intelligence.ml_engine import ml_engine
    scores = await ml_engine.get_all_scores()
    return {"scores": scores, "count": len(scores)}


@router.get("/api/skills/{skill_name}/ml/score")
async def skill_ml_score_api(skill_name: str, user: dict = Depends(require_auth)):
    """Get detailed ML score and insights for a specific skill."""
    from core.intelligence.ml_engine import ml_engine
    return await ml_engine.get_skill_score(skill_name)


@router.get("/api/skills/{skill_name}/ml/metrics")
async def skill_ml_metrics_api(
    skill_name: str,
    period: str = "daily",
    limit: int = 30,
    user: dict = Depends(require_auth),
):
    """Get historical performance metrics for a skill."""
    from core.database import SkillMetrics
    history = await SkillMetrics.get_history(skill_name, period, limit)
    return {
        "skill_name": skill_name,
        "period": period,
        "metrics": [
            {
                "period_start": m.period_start.isoformat(),
                "total_runs": m.total_runs,
                "success_rate": round(m.success_rate, 3),
                "avg_duration_ms": round(m.avg_duration_ms, 1),
                "p95_duration_ms": round(m.p95_duration_ms, 1),
                "performance_score": round(m.performance_score, 3),
                "trend": m.trend,
                "avg_user_rating": round(m.avg_user_rating, 2) if m.avg_user_rating else None,
                "error_categories": m.error_categories or {},
            }
            for m in history
        ],
    }


@router.post("/api/skills/{skill_name}/ml/feedback")
async def skill_ml_feedback_api(
    skill_name: str,
    body: SkillFeedbackRequest,
    user: dict = Depends(require_auth),
):
    """Submit user feedback on a skill execution for ML learning."""
    from core.intelligence.ml_engine import ml_engine
    result = await ml_engine.submit_feedback(
        skill_name=skill_name,
        rating=body.rating,
        feedback_type=body.feedback_type,
        comment=body.comment,
        skill_run_id=body.skill_run_id,
        session_id=body.session_id,
        input_args=body.input_args,
        output_snapshot=body.output_snapshot,
    )
    return result


@router.get("/api/skills/{skill_name}/ml/parameters")
async def skill_ml_parameters_api(skill_name: str, user: dict = Depends(require_auth)):
    """Get learned optimal parameters for a skill."""
    from core.intelligence.ml_engine import ml_engine
    insights = await ml_engine.analyze_parameters(skill_name)
    return {"skill_name": skill_name, "parameters": insights}


@router.get("/api/skills/{skill_name}/ml/learning")
async def skill_ml_learning_api(
    skill_name: str,
    limit: int = 20,
    user: dict = Depends(require_auth),
):
    """Get learning event log for a skill."""
    from core.database import SkillLearningLog
    events = await SkillLearningLog.get_recent(skill_name, limit)
    return {
        "skill_name": skill_name,
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "description": e.description,
                "confidence": round(e.confidence, 2),
                "impact": e.impact,
                "applied": e.applied,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    }


@router.post("/api/skills/ml/analyze")
async def skill_ml_analyze_api(user: dict = Depends(require_auth)):
    """Trigger a full ML analysis cycle across all skills."""
    from core.intelligence.ml_engine import ml_engine
    summary = await ml_engine.run_full_analysis()
    return summary


@router.get("/api/skills/ml/learning-log")
async def skill_ml_learning_log_api(limit: int = 50, user: dict = Depends(require_auth)):
    """Get the global learning log across all skills."""
    from core.database import SkillLearningLog
    events = await SkillLearningLog.get_recent(limit=limit)
    return {
        "events": [
            {
                "id": e.id,
                "skill_name": e.skill_name,
                "event_type": e.event_type,
                "description": e.description,
                "confidence": round(e.confidence, 2),
                "impact": e.impact,
                "applied": e.applied,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    }
