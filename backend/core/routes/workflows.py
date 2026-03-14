"""
Sanaa AI — Workflow routes: list, run, status, resume, cancel, create.
"""

import logging
import os
import re

import yaml
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, desc

from core.database import WorkflowRun, AsyncSessionLocal, AuditLog
from core.routes import deps
from core.routes.deps import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()


class WorkflowRunRequest(BaseModel):
    args: dict = {}
    channel: str = "web"
    started_by: str = "admin"


class WorkflowResumeRequest(BaseModel):
    approved: bool = True
    resume_token: str


@router.get("/api/workflows")
async def list_workflows_api(user: dict = Depends(require_auth)):
    """List discovered workflow definitions."""
    workflows = deps.workflow_loader.discover()
    return {
        "count": len(workflows),
        "workflows": [
            {
                "name": w.name,
                "description": w.description,
                "version": w.version,
                "path": w.path,
                "step_count": len(w.steps),
                "steps": [
                    {
                        "id": s.id,
                        "action": s.action,
                        "approval": s.approval,
                        "on_failure": s.on_failure,
                        "description": s.description,
                    }
                    for s in w.steps
                ],
            }
            for w in workflows
        ],
    }


@router.post("/api/workflows")
async def create_workflow_api(request: Request, user: dict = Depends(require_auth)):
    """Create or update a workflow from YAML content.

    Accepts raw YAML body (Content-Type: application/x-yaml or text/plain).
    Validates the YAML, writes it to the workflows directory, and re-discovers.
    """
    body_bytes = await request.body()
    yaml_content = body_bytes.decode("utf-8", errors="replace").strip()

    if not yaml_content:
        raise HTTPException(400, "Empty YAML body")

    # Parse and validate
    try:
        parsed = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Invalid YAML: {e}")

    if not isinstance(parsed, dict):
        raise HTTPException(400, "YAML must be a mapping (dict)")

    name = parsed.get("name")
    if not name or not isinstance(name, str):
        raise HTTPException(400, "Workflow YAML must contain a 'name' field")

    # Sanitise name for filesystem safety
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.strip())
    if not safe_name:
        raise HTTPException(400, "Invalid workflow name")

    # Must have steps
    steps = parsed.get("steps")
    if not steps or not isinstance(steps, list):
        raise HTTPException(400, "Workflow must have at least one step")

    # Validate via the loader (catches schema issues)
    try:
        deps.workflow_loader._parse_definition(parsed, f"{safe_name}.yaml")
    except (ValueError, KeyError) as e:
        raise HTTPException(400, f"Workflow validation failed: {e}")

    # Write to workflows directory
    workflows_dir = deps.workflow_loader.workflows_dir
    filepath = os.path.join(workflows_dir, f"{safe_name}.yaml")
    with open(filepath, "w") as f:
        f.write(yaml_content)

    logger.info(f"Workflow saved: {safe_name} -> {filepath}")

    try:
        await AuditLog.log(
            actor=user.get("email", "admin"),
            action="workflow.create",
            resource=safe_name,
            details={"path": filepath, "step_count": len(steps)},
            success=True,
        )
    except Exception:
        pass

    return {"status": "saved", "name": safe_name, "path": filepath, "step_count": len(steps)}


@router.post("/api/workflows/{workflow_name}/run")
async def run_workflow_api(workflow_name: str, body: WorkflowRunRequest, user: dict = Depends(require_auth)):
    """Start a workflow run."""
    await deps.brain.ensure_skills_loaded()
    workflows = {w.name: w for w in deps.workflow_loader.discover()}
    workflow = workflows.get(workflow_name)
    if not workflow:
        raise HTTPException(404, f"Workflow not found: {workflow_name}")

    run_id = await deps.workflow_runtime.start(
        workflow,
        args=body.args or {},
        started_by=body.started_by or user.get("email", "admin"),
        channel=body.channel or "web",
    )
    return {"run_id": run_id, "workflow": workflow_name, "status": "started"}


@router.get("/api/workflows/runs/{run_id}")
async def workflow_run_status_api(run_id: int, user: dict = Depends(require_auth)):
    """Get workflow run status and step results."""
    state = await deps.workflow_runtime.get_status(run_id)
    if not state:
        raise HTTPException(404, "Workflow run not found")
    return {
        "run_id": state.run_id,
        "workflow_name": state.workflow_name,
        "status": state.status,
        "current_step": state.current_step,
        "resume_token": state.resume_token,
        "input_args": state.input_args,
        "output": state.output,
        "step_results": {
            k: {
                "success": v.success,
                "output": v.output,
                "error": v.error,
                "skipped": v.skipped,
                "duration_ms": v.duration_ms,
            }
            for k, v in state.step_results.items()
        },
    }


@router.get("/api/workflows/runs")
async def workflow_runs_list_api(limit: int = 50, user: dict = Depends(require_auth)):
    """List recent workflow runs."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkflowRun)
            .order_by(desc(WorkflowRun.started_at))
            .limit(max(1, min(limit, 200)))
        )
        runs = result.scalars().all()

    return {
        "count": len(runs),
        "runs": [
            {
                "id": r.id,
                "workflow_name": r.workflow_name,
                "started_by": r.started_by,
                "channel": r.channel,
                "status": r.status,
                "current_step": r.current_step,
                "resume_token": r.resume_token,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "paused_at": r.paused_at.isoformat() if r.paused_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "state": r.state or {},
                "output": r.output or [],
            }
            for r in runs
        ],
    }


@router.get("/api/workflows/runs/{run_id}/approval")
async def workflow_run_approval_api(run_id: int, user: dict = Depends(require_auth)):
    """Return pending approval details for a paused workflow run."""
    state = await deps.workflow_runtime.get_status(run_id)
    if not state:
        raise HTTPException(404, "Workflow run not found")
    if state.status != "paused":
        return {"status": state.status, "approval": None}

    approval_entry = None
    for item in reversed(state.output or []):
        if isinstance(item, dict) and item.get("type") == "approval_request":
            approval_entry = item
            break

    workflow = next((w for w in deps.workflow_loader.discover() if w.name == state.workflow_name), None)
    step_meta = None
    if workflow and 0 <= state.current_step < len(workflow.steps):
        step = workflow.steps[state.current_step]
        step_meta = {
            "id": step.id,
            "description": step.description,
            "action": step.action,
            "approval": step.approval,
        }

    return {
        "status": state.status,
        "run_id": state.run_id,
        "workflow_name": state.workflow_name,
        "resume_token": state.resume_token,
        "approval": approval_entry,
        "current_step": step_meta,
    }


@router.post("/api/workflows/runs/{run_id}/resume")
async def workflow_run_resume_api(run_id: int, body: WorkflowResumeRequest, user: dict = Depends(require_auth)):
    """Resume a paused workflow run after approval decision."""
    state = await deps.workflow_runtime.get_status(run_id)
    if not state:
        raise HTTPException(404, "Workflow run not found")
    if state.status != "paused":
        raise HTTPException(400, f"Workflow run is not paused (status={state.status})")
    if body.resume_token != (state.resume_token or ""):
        raise HTTPException(400, "Invalid resume token")

    workflow = next((w for w in deps.workflow_loader.discover() if w.name == state.workflow_name), None)
    if not workflow:
        raise HTTPException(404, f"Workflow definition not found: {state.workflow_name}")

    ok = await deps.workflow_runtime.resume(run_id, workflow, approved=body.approved)
    if not ok:
        raise HTTPException(400, "Failed to resume workflow")

    try:
        await AuditLog.log(
            actor=user.get("email", "admin"),
            action="workflow.approval_decision",
            resource=state.workflow_name,
            details={"run_id": run_id, "approved": body.approved},
            success=True,
        )
    except Exception:
        pass
    return {"status": "success", "run_id": run_id, "approved": body.approved}


@router.post("/api/workflows/runs/{run_id}/cancel")
async def workflow_run_cancel_api(run_id: int, user: dict = Depends(require_auth)):
    """Cancel a running or paused workflow run."""
    ok = await deps.workflow_runtime.cancel(run_id)
    if not ok:
        raise HTTPException(404, "Workflow run not found")
    return {"status": "success", "run_id": run_id, "cancelled": True}
