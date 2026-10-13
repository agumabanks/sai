"""
Sanaa AI — Config routes: brain config, tool policy, session policy, system state, preferences.
"""

import logging

from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

from core.brain import get_shared_brain
from core.config import get_settings
from core.database import AuditLog
from core.routes import deps
from core.routes.deps import require_auth, require_user_admin, RateLimit
from core.policies import (
    get_tool_policy,
    save_tool_policy,
    build_skill_catalog,
    get_session_policy,
    save_session_policy,
)

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


class ToolPolicyUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[str] = None
    allow: Optional[list[str]] = None
    deny: Optional[list[str]] = None
    groups: Optional[dict] = None
    by_provider: Optional[dict] = None
    by_channel: Optional[dict] = None


class SessionPolicyUpdateRequest(BaseModel):
    dm_scope: Optional[str] = None
    reset: Optional[dict] = None
    send_policy: Optional[dict] = None
    reset_triggers: Optional[list[str]] = None


@router.get("/api/system/state")
async def get_system_state(request: Request, user: dict = Depends(require_auth)):
    """Get HTML fragment for the Visual Control Center."""

    current_provider = deps.brain.get_current_provider()

    providers = ["auto", "claude", "groq", "openrouter", "local"]
    provider_html = ""

    for p in providers:
        active_class = "bg-blue-600 text-white shadow-lg" if p == current_provider else "text-gray-400 hover:text-white hover:bg-white/5"
        provider_html += f"""
        <button
            hx-post="/api/system/brain/provider"
            hx-vals='{{"provider": "{p}"}}'
            hx-target="#control-center"
            class="flex-1 py-1.5 text-xs font-medium rounded-md transition-all duration-200 {active_class}">
            {p.title()}
        </button>
        """

    if current_provider == "local":
        provider_desc = settings.ollama_model
    elif current_provider == "groq":
        provider_desc = f"Groq / {settings.groq_model}"
    elif current_provider == "claude":
        provider_desc = f"Claude mode via {settings.brain_claude_source.title()}"
    elif current_provider == "openrouter":
        provider_desc = f"OpenRouter / {settings.openrouter_model}"
    else:
        provider_desc = "Auto routing"

    return HTMLResponse(f"""
    <div class="space-y-4">
        <!-- Brain Control -->
        <div class="space-y-2">
            <div class="flex justify-between items-center text-xs uppercase tracking-wider text-gray-400 font-semibold">
                <span>Active Brain</span>
                <span class="text-[10px] bg-blue-900/30 text-blue-400 px-1.5 py-0.5 rounded border border-blue-800/30">{current_provider.upper()}</span>
            </div>
            <div class="flex bg-black/40 p-1 rounded-lg border border-white/5">
                {provider_html}
            </div>
            <div class="text-[10px] text-gray-500 text-center mt-1">
                Currently using {provider_desc}
            </div>
        </div>

        <!-- Divider -->
        <div class="h-px bg-gradient-to-r from-transparent via-white/10 to-transparent"></div>

        <!-- System Toggles -->
        <div class="space-y-3">
            <div class="text-xs uppercase tracking-wider text-gray-400 font-semibold mb-2">System Preferences</div>

            <label class="flex items-center justify-between cursor-pointer group">
                <span class="text-sm text-gray-300 group-hover:text-white transition">Security Scanner</span>
                <input type="checkbox" checked class="sr-only peer">
                <div class="w-9 h-5 bg-gray-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-800 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
            </label>

            <label class="flex items-center justify-between cursor-pointer group">
                <span class="text-sm text-gray-300 group-hover:text-white transition">Autonomous Healer</span>
                <input type="checkbox" checked class="sr-only peer">
                <div class="w-9 h-5 bg-gray-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-green-800 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-green-600"></div>
            </label>
        </div>
    </div>
    """)


@router.get("/api/system/tool-policy")
async def get_tool_policy_api(user: dict = Depends(require_auth)):
    """Get current AI tool allowlist/denylist policy."""
    await deps.brain.ensure_skills_loaded()
    return {
        "policy": await get_tool_policy(),
        "skills": [s["name"] for s in await build_skill_catalog(deps.brain.skill_registry)],
    }


@router.post("/api/system/tool-policy")
async def update_tool_policy_api(
    body: ToolPolicyUpdateRequest,
    user: dict = Depends(require_auth),
    _rate: None = Depends(RateLimit(limit=30)),
):
    """Update AI tool policy (partial update)."""
    await deps.brain.ensure_skills_loaded()
    payload = body.model_dump(exclude_none=True)
    try:
        policy = await save_tool_policy(payload, source="admin_dashboard", skill_names=set(deps.brain.skill_registry._skills.keys()))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "success", "policy": policy}


@router.get("/api/system/session-policy")
async def get_session_policy_api(user: dict = Depends(require_auth)):
    """Get current session routing/reset/send policy."""
    return {"policy": await get_session_policy()}


@router.post("/api/system/session-policy")
async def update_session_policy_api(
    body: SessionPolicyUpdateRequest,
    user: dict = Depends(require_auth),
    _rate: None = Depends(RateLimit(limit=30)),
):
    """Update session safety/reset/send policy (partial update)."""
    payload = body.model_dump(exclude_none=True)
    policy = await save_session_policy(payload, source="admin_dashboard")
    return {"status": "success", "policy": policy}


@router.post("/api/system/brain/provider")
async def set_provider(
    request: Request,
    user: dict = Depends(require_auth),
    _rate: None = Depends(RateLimit(limit=30)),
):
    """Set the active LLM provider."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        provider = body.get("provider", "")
    else:
        form = await request.form()
        provider = form.get("provider", "")

    provider = provider.lower()
    if provider not in deps.BRAIN_PROVIDERS:
        raise HTTPException(400, "Invalid provider. Choose: auto, local, groq, claude, openrouter, soldier")

    deps.brain.switch_provider(provider)
    get_shared_brain().switch_provider(provider)
    from core.database import SystemKnowledge
    await SystemKnowledge.set_pref("brain.provider", provider, source="api")

    if "hx-request" in request.headers:
        return await get_system_state(request)

    return {"status": "success", "provider": provider}


@router.get("/api/system/brain/config")
async def get_brain_config(user: dict = Depends(require_auth)):
    """Get editable brain configuration for admin dashboard."""
    return await deps._brain_config_snapshot()


@router.post("/api/system/brain/config")
async def update_brain_config(
    request: Request,
    user: dict = Depends(require_auth),
    _rate: None = Depends(RateLimit(limit=30)),
):
    """Update brain provider/source/models/keys from admin dashboard."""
    require_user_admin(user)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Invalid request body")

    from core.database import SystemKnowledge

    provider = str(body.get("provider", "") or "").strip().lower()
    if provider:
        if provider not in deps.BRAIN_PROVIDERS:
            raise HTTPException(400, "Invalid provider")
        deps.brain.switch_provider(provider)
        await SystemKnowledge.set_pref("brain.provider", provider, source="admin_dashboard")

    claude_source = str(body.get("claude_source", "") or "").strip().lower()
    if claude_source:
        if claude_source not in deps.CLAUDE_SOURCES:
            raise HTTPException(400, "Invalid claude_source")
        settings.brain_claude_source = claude_source
        await SystemKnowledge.set_pref("brain.claude_source", claude_source, source="admin_dashboard")

    auto_provider_order = body.get("auto_provider_order")
    if auto_provider_order is not None:
        if isinstance(auto_provider_order, list):
            auto_provider_order = ",".join(str(v).strip() for v in auto_provider_order if str(v).strip())
        auto_provider_order = deps._normalize_provider_csv(str(auto_provider_order))
        settings.brain_auto_provider_order = auto_provider_order
        await SystemKnowledge.set_pref("brain.auto_provider_order", auto_provider_order, source="admin_dashboard")

    keys = body.get("keys") or {}
    if isinstance(keys, dict):
        for raw_provider, value in keys.items():
            secret = str(value or "").strip()
            if not secret:
                continue
            provider_key = raw_provider.lower().strip()
            if provider_key in {"claude", "anthropic"}:
                provider_key = "anthropic"
            if provider_key not in {"anthropic", "groq", "openrouter"}:
                continue
            deps._apply_runtime_secret(provider_key, secret)
            await SystemKnowledge.set_pref(f"brain.api_key.{provider_key}", secret, source="admin_dashboard")

    model_id = str(body.get("model_id", "") or "").strip()
    if model_id:
        target_provider = provider or deps.brain.get_current_provider() or "auto"
        models = body.get("models") or {}
        models[deps._model_key_for_provider(target_provider, claude_source or settings.brain_claude_source)] = model_id
        body["models"] = models

    models = body.get("models") or {}
    model_pref_map = {
        "local": "brain.model.local",
        "groq": "brain.model.groq",
        "anthropic_fast": "brain.model.anthropic_fast",
        "anthropic_premium": "brain.model.anthropic_premium",
        "openrouter": "brain.model.openrouter",
        "soldier": "brain.model.soldier",
    }
    if isinstance(models, dict):
        for model_key, pref_key in model_pref_map.items():
            if model_key not in models:
                continue
            model_value = str(models.get(model_key) or "").strip()
            if not model_value:
                continue
            deps._apply_runtime_brain_model(model_key, model_value)
            await SystemKnowledge.set_pref(pref_key, model_value, source="admin_dashboard")

    deps.brain.registry.models = deps.brain.registry._build_model_chain()
    shared_brain = get_shared_brain()
    shared_brain.switch_provider(deps.brain.get_current_provider())

    return {"status": "success", "config": await deps._brain_config_snapshot()}


@router.get("/api/system/preferences")
async def get_preferences(request: Request, keys: str = Query(..., description="Comma separated list of preference keys"), user: dict = Depends(require_auth)):
    """Fetch multiple system preferences from system_knowledge at once."""
    from core.database import SystemKnowledge
    keys_list = [k.strip() for k in keys.split(",") if k.strip()]
    results = {}
    for key in keys_list:
        val = await SystemKnowledge.get_pref(key, default=None)
        results[key] = val
    return results


@router.post("/api/system/preference")
async def update_preference(
    request: Request,
    user: dict = Depends(require_auth),
    _rate: None = Depends(RateLimit(limit=60)),
):
    """Update a system preference and persist it in system_knowledge."""
    body = await request.json()
    key = body.get("key")
    value = body.get("value")
    if not key:
        raise HTTPException(400, "Missing preference key")

    from core.database import SystemKnowledge
    await SystemKnowledge.set_pref(key, value, source="user_preference")
    return {"status": "success", "key": key, "value": value}
