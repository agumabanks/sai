"""
Sanaa AI — Command routes: execute, poll, approve commands.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

from core.database import Command
from core.routes import deps
from core.routes.deps import require_auth, RateLimit
from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


class CommandRequest(BaseModel):
    command: str
    context: Optional[str] = None
    approval_required: bool = True


@router.post("/api/command")
async def execute_command(
    request: Request,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_auth),
    _rate: None = Depends(RateLimit(limit=30)),
):
    """Handle commands from both JSON API and htmx form submissions."""

    content_type = request.headers.get("content-type", "")
    body = {}

    if "application/json" in content_type:
        body = await request.json()
        command_text = body.get("command", "")
    else:
        form = await request.form()
        command_text = form.get("command", "")

    if not command_text.strip():
        raise HTTPException(status_code=400, detail="Empty command")

    # Honor provider from JSON body (e.g. Sanaa Chat dropdown) before routing
    requested_provider = (body.get("provider") or "").strip().lower()
    if requested_provider and requested_provider in deps.BRAIN_PROVIDERS:
        deps.brain.switch_provider(requested_provider)
        from core.database import SystemKnowledge
        await SystemKnowledge.set_pref("brain.provider", requested_provider, source="api_command")

    cmd = await Command.create(text=command_text, context=None, status="processing")

    # Intercept "briefing" / "news" commands
    if command_text.lower().strip() in ["briefing", "news", "generate briefing", "news briefing", "daily briefing"]:
        from core.agents.news_agent import NewsAgent

        async def _generate_briefing():
            try:
                agent = NewsAgent()
                summary = await agent.get_daily_summary()
                if summary and len(summary.strip()) > 100:
                    await agent.send_newsletter(summary)
                    logger.info("Briefing generated and newsletter sent successfully")
                else:
                    logger.warning(f"Briefing too short or empty: {len(summary) if summary else 0} chars")
            except Exception as e:
                logger.error(f"Briefing generation failed: {e}", exc_info=True)

        background_tasks.add_task(_generate_briefing)
        response_text = "📰 Intelligence Briefing generation started.\n\nFetching news from 8 RSS sources, running LLM synthesis.\nNewsletter will be sent to your email when ready."
        await Command.update_by_id(cmd.id, status="completed")
        if "hx-request" in request.headers:
            return HTMLResponse(f'<div class="text-green-400 whitespace-pre-wrap">{response_text}</div>')
        return JSONResponse({"id": cmd.id, "status": "completed", "response": response_text})

    # Intercept "scan" commands
    if command_text.lower().strip() in ["scan", "scan system", "run scan", "check security"]:
        background_tasks.add_task(deps.scanner.scan_all)
        response_text = "🚀 Intelligence Scan initiated.\n\nAuditing all repositories for:\n- Shell injection risks\n- Dynamic code execution\n- Credential leaks\n\nCheck the dashboard for live results."
        await Command.update_by_id(cmd.id, status="completed")
        if "hx-request" in request.headers:
            return HTMLResponse(f'<div class="text-green-400 whitespace-pre-wrap">{response_text}</div>')
        return JSONResponse({"id": cmd.id, "status": "completed", "response": response_text})

    # Intercept explicit skill commands: "run skill", "skill", "run <skill>"
    skill_prefix = None
    lowered = command_text.lower().strip()
    for prefix in ("run skill ", "skill "):
        if lowered.startswith(prefix):
            skill_prefix = prefix
            break

    if skill_prefix:
        await deps.brain.ensure_skills_loaded()
        raw = command_text[len(skill_prefix):].strip()
        skill_name = raw.split(" ", 1)[0].strip()
        args = {}
        if " " in raw:
            maybe_json = raw.split(" ", 1)[1].strip()
            if maybe_json.startswith("{"):
                try:
                    args = json.loads(maybe_json)
                except Exception:
                    args = {}
        result = await deps.brain.execute_skill(
            name=skill_name, args=args,
            session_id=f"cmd:{cmd.id}", channel="web",
            sender_id=user["email"],
            execution_mode="manual",
            sender_role=user.get("role", "operator"),
        )
        response_text = result.get("output") or result.get("error") or json.dumps(result.get("data") or {}, default=str)
        await Command.update_by_id(cmd.id, status="completed" if result.get("success") else "failed")
        if "hx-request" in request.headers:
            return HTMLResponse(f'<div class="text-green-400 whitespace-pre-wrap">{response_text}</div>')
        return JSONResponse({"id": cmd.id, "status": "completed" if result.get("success") else "failed", "result": result, "response": response_text})

    if lowered.startswith("run ") and not lowered.startswith("run workflow ") and not lowered.startswith("run skill "):
        await deps.brain.ensure_skills_loaded()
        raw = command_text[4:].strip()
        skill_name = raw.split(" ", 1)[0].strip()
        if skill_name and deps.brain.skill_registry.get(skill_name):
            args = {}
            if " " in raw:
                maybe_json = raw.split(" ", 1)[1].strip()
                if maybe_json.startswith("{"):
                    try:
                        args = json.loads(maybe_json)
                    except Exception:
                        args = {"action": maybe_json}
                else:
                    args = {"action": maybe_json}
            result = await deps.brain.execute_skill(
                name=skill_name,
                args=args,
                session_id=f"cmd:{cmd.id}",
                channel="web",
                sender_id=user["email"],
                execution_mode="manual",
                sender_role=user.get("role", "operator"),
            )
            response_text = result.get("output") or result.get("error") or json.dumps(result.get("data") or {}, default=str)
            await Command.update_by_id(cmd.id, status="completed" if result.get("success") else "failed")
            return JSONResponse({
                "id": cmd.id,
                "status": "completed" if result.get("success") else "failed",
                "result": result,
                "response": response_text,
            })

    # Intercept "run workflow <name> [json]"
    if command_text.lower().startswith("run workflow "):
        await deps.brain.ensure_skills_loaded()
        raw = command_text[len("run workflow "):].strip()
        workflow_name = raw.split(" ", 1)[0].strip()
        wf_args = {}
        if " " in raw:
            maybe_json = raw.split(" ", 1)[1].strip()
            if maybe_json.startswith("{"):
                try:
                    wf_args = json.loads(maybe_json)
                except Exception:
                    wf_args = {}
        workflow = None
        for w in deps.workflow_loader.discover():
            if w.name == workflow_name:
                workflow = w
                break
        if not workflow:
            await Command.update_by_id(cmd.id, status="failed")
            raise HTTPException(404, f"Workflow not found: {workflow_name}")
        run_id = await deps.workflow_runtime.start(
            workflow, args=wf_args, started_by=user["email"], channel="web",
        )
        response_text = f"🔁 Workflow '{workflow_name}' started (run_id={run_id})"
        await Command.update_by_id(cmd.id, status="completed")
        if "hx-request" in request.headers:
            return HTMLResponse(f'<div class="text-green-400 whitespace-pre-wrap">{response_text}</div>')
        return JSONResponse({"id": cmd.id, "status": "completed", "run_id": run_id, "response": response_text})

    # Intercept "use brain" command
    if command_text.lower().startswith("use brain"):
        provider = command_text.lower().split("use brain")[-1].strip()
        if provider in deps.BRAIN_PROVIDERS:
            deps.brain.switch_provider(provider)
            from core.database import SystemKnowledge
            await SystemKnowledge.set_pref("brain.provider", provider, source="user_command")
            response_text = f"🧠 Brain switched to **{provider.upper()}** mode."
            await Command.update_by_id(cmd.id, status="completed")
            if "hx-request" in request.headers:
                return HTMLResponse(f'<div class="text-blue-400 whitespace-pre-wrap">{response_text}</div>')
            return JSONResponse({"id": cmd.id, "status": "completed", "response": response_text})
        else:
            response_text = "❌ Invalid provider. Use: auto, local, groq, claude, or openrouter."
            await Command.update_by_id(cmd.id, status="failed")
            if "hx-request" in request.headers:
                return HTMLResponse(f'<div class="text-red-400 whitespace-pre-wrap">{response_text}</div>')
            return JSONResponse({"id": cmd.id, "status": "failed", "response": response_text})

    # Intercept "configure <provider> <api-key>" command
    if command_text.lower().startswith("configure "):
        parts = command_text.strip().split(maxsplit=2)
        if len(parts) >= 3:
            target = parts[1].lower()
            key = parts[2].strip()
            if target in {"anthropic", "claude", "groq", "openrouter"}:
                provider = "anthropic" if target == "claude" else target
                deps._apply_runtime_secret(provider, key)
                from core.database import SystemKnowledge
                await SystemKnowledge.set_pref(f"brain.api_key.{provider}", key, source="user_command")
                deps.brain.registry.models = deps.brain.registry._build_model_chain()
                response_text = f"🔑 {provider.title()} API key configured successfully."
                await Command.update_by_id(cmd.id, status="completed")
                if "hx-request" in request.headers:
                    return HTMLResponse(f'<div class="text-green-400 whitespace-pre-wrap">{response_text}</div>')
                return JSONResponse({"id": cmd.id, "status": "completed", "response": response_text})

    # Check if caller wants async mode
    is_async = body.get("async", False) if "application/json" in content_type else False

    if is_async:
        async def _process_command_async(cmd_id: str, command_txt: str, actor: dict):
            try:
                msg = await deps.web_channel.receive_message({
                    "command": command_txt,
                    "email": actor.get("email", "web_user"),
                    "name": actor.get("name", actor.get("email", "web_user")),
                    "role": actor.get("role", "operator"),
                })
                if not msg:
                    await Command.update_by_id(cmd_id, status="failed", response="Invalid command")
                    return
                response_text = await deps.router_instance.route(msg)
                await Command.update_by_id(cmd_id, status="completed", response=response_text)
            except Exception as e:
                logger.error(f"Async command {cmd_id} failed: {e}", exc_info=True)
                await Command.update_by_id(cmd_id, status="failed", response=f"Error: {str(e)}")

        background_tasks.add_task(_process_command_async, cmd.id, command_text, user)
        return JSONResponse({"id": cmd.id, "status": "processing"})

    # Synchronous mode
    msg = await deps.web_channel.receive_message({
        "command": command_text,
        "email": user["email"],
        "name": user.get("name", user["email"]),
        "role": user.get("role", "operator"),
    })
    if not msg:
        raise HTTPException(status_code=400, detail="Invalid command")

    response_text = await deps.router_instance.route(msg)
    await Command.update_by_id(cmd.id, status="completed", response=response_text)

    if "hx-request" in request.headers:
        return HTMLResponse(f'<div class="text-green-400 whitespace-pre-wrap">{response_text}</div>')

    return JSONResponse({
        "id": cmd.id,
        "status": "completed",
        "response": response_text,
    })


@router.get("/api/command/{cmd_id}")
async def get_command_status(cmd_id: str, user: dict = Depends(require_auth)):
    """Poll for command status and response."""
    cmd = await Command.get(cmd_id)
    if not cmd:
        raise HTTPException(404, "Command not found")
    return {
        "id": cmd.id,
        "status": cmd.status,
        "response": cmd.response,
        "text": cmd.text,
    }


@router.post("/api/command/{cmd_id}/approve")
async def approve_command(cmd_id: str, request: Request, background_tasks: BackgroundTasks, user: dict = Depends(require_auth), _rate: None = Depends(RateLimit(limit=30))):
    cmd = await Command.get(cmd_id)
    if not cmd:
        raise HTTPException(404, "Command not found")
    if cmd.status != "awaiting_approval":
        raise HTTPException(400, "Command not awaiting approval")

    background_tasks.add_task(deps.brain.execute_plan, cmd.id, cmd.proposed_plan or [])
    await Command.update_by_id(cmd.id, status="executing")

    if "hx-request" in request.headers:
        return HTMLResponse('<div class="text-green-400">Approved. Executing now...</div>')

    return {"status": "approved", "message": "Executing now"}
