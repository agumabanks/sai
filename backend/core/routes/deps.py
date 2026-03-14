"""
Sanaa AI — Shared route dependencies and state.
Centralizes objects that multiple routers need (brain, agents, adapters, etc.)
so they can be imported without circular dependencies via main.py.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
security = HTTPBearer(auto_error=False)

# ── Shared singleton objects (wired at startup in main.py) ──────────────
# These are set via `init_shared_state()` called from main.py lifespan.

brain = None
router_instance = None  # MessageRouter
web_channel = None
whatsapp_adapter = None
telegram_adapter = None
whatsapp_saas = None
rate_limiter = None

# Agents
server_health = None
watchdog = None
healer = None

# Intelligence
scanner = None
skill_mapper = None
workflow_loader = None
workflow_runtime = None

# In-memory event store for dashboard live feed
_recent_events: list[dict] = []
MAX_EVENTS = 50

BRAIN_PROVIDERS = {"auto", "local", "groq", "claude", "openrouter"}
CLAUDE_SOURCES = {"anthropic", "groq", "openrouter"}


def init_shared_state(
    *,
    brain_inst,
    router_inst,
    web_channel_inst,
    whatsapp_saas_inst,
    rate_limiter_inst,
    server_health_inst,
    watchdog_inst,
    healer_inst,
    scanner_inst,
    skill_mapper_inst,
    workflow_loader_inst,
    workflow_runtime_inst,
):
    """Called once from main.py to wire all singletons into the deps module."""
    global brain, router_instance, web_channel, whatsapp_saas, rate_limiter
    global server_health, watchdog, healer, scanner, skill_mapper
    global workflow_loader, workflow_runtime

    brain = brain_inst
    router_instance = router_inst
    web_channel = web_channel_inst
    whatsapp_saas = whatsapp_saas_inst
    rate_limiter = rate_limiter_inst
    server_health = server_health_inst
    watchdog = watchdog_inst
    healer = healer_inst
    scanner = scanner_inst
    skill_mapper = skill_mapper_inst
    workflow_loader = workflow_loader_inst
    workflow_runtime = workflow_runtime_inst


def set_whatsapp_adapter(adapter):
    global whatsapp_adapter
    whatsapp_adapter = adapter


def set_telegram_adapter(adapter):
    global telegram_adapter
    telegram_adapter = adapter


# ── Auth helpers ─────────────────────────────────────────────────────────

def get_current_user(request: Request) -> Optional[dict]:
    """Get user from signed session cookie. Returns None if not authenticated."""
    email = request.session.get("email")
    if not email:
        return None
    return {
        "email": email,
        "logged_in_at": request.session.get("logged_in_at", ""),
    }


def require_auth(request: Request) -> dict:
    """Dependency: require session user OR valid Bearer token."""
    user = get_current_user(request)
    if user:
        return user

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        if token == settings.mac_client_api_key:
            return {"email": "system@bridge", "is_bridge": True}

    raise HTTPException(status_code=401, detail="Not authenticated")


def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify Bearer token for device/API access."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing API key")
    if credentials.credentials != settings.mac_client_api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return credentials.credentials


async def check_rate_limit(request: Request, limit: int = 60):
    """Rate limit check dependency."""
    client_ip = request.client.host if request.client else "unknown"
    key = f"ip:{client_ip}"
    allowed = await rate_limiter.check(key, limit=limit)
    if not allowed:
        remaining = await rate_limiter.get_remaining(key, limit=limit)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again in 60 seconds.",
            headers={"Retry-After": "60", "X-RateLimit-Remaining": str(remaining)},
        )


def verify_whatsapp_api_key(request: Request):
    """Verify Bearer token for WhatsApp API bridge access."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = auth.split(" ", 1)[1]
    if token not in (settings.whatsapp_api_key, settings.mac_client_api_key):
        raise HTTPException(403, "Invalid API key")
    if not settings.whatsapp_saas_enabled:
        raise HTTPException(503, "WhatsApp service not available")
    return token


def verify_soko_provision_key(request: Request):
    """Verify Bearer token for Soko provisioning API."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = auth.split(" ", 1)[1]
    if not settings.soko_provision_key or token != settings.soko_provision_key:
        raise HTTPException(403, "Invalid provisioning key")
    return token


# ── Brain config helpers (used by commands.py and config.py) ────────────

def _normalize_provider_csv(value: str) -> str:
    items = [p.strip().lower() for p in (value or "").split(",") if p.strip()]
    normalized = []
    for item in items:
        if item in ("anthropic", "groq", "openrouter", "local", "openai") and item not in normalized:
            normalized.append(item)
    if "local" not in normalized:
        normalized.append("local")
    return ",".join(normalized or ["groq", "anthropic", "openrouter", "local"])


def _apply_runtime_secret(provider: str, key: str):
    provider = provider.lower().strip()
    key = (key or "").strip()
    if not key:
        return

    if provider in ("anthropic", "claude"):
        settings.anthropic_api_key = key
        import os
        os.environ["ANTHROPIC_API_KEY"] = key
        return
    if provider == "groq":
        settings.groq_api_key = key
        import os
        os.environ["GROQ_API_KEY"] = key
        return
    if provider == "openrouter":
        settings.openrouter_api_key = key
        import os
        os.environ["OPENROUTER_API_KEY"] = key
        return


def _apply_runtime_brain_model(key: str, value: str):
    model_value = (value or "").strip()
    if not model_value:
        return
    if key == "local":
        settings.ollama_model = model_value
    elif key == "groq":
        settings.groq_model = model_value
    elif key == "anthropic_fast":
        settings.anthropic_model_fast = model_value
    elif key == "anthropic_premium":
        settings.anthropic_model_premium = model_value
    elif key == "openrouter":
        settings.openrouter_model = model_value


async def _brain_config_snapshot() -> dict:
    from core.database import SystemKnowledge

    persisted_provider = await SystemKnowledge.get_pref("brain.provider", default=brain.get_current_provider() or "auto")
    persisted_claude_source = await SystemKnowledge.get_pref("brain.claude_source", default=settings.brain_claude_source)
    persisted_auto_order = await SystemKnowledge.get_pref("brain.auto_provider_order", default=settings.brain_auto_provider_order)

    return {
        "provider": persisted_provider,
        "current_provider": brain.get_current_provider(),
        "claude_source": persisted_claude_source,
        "auto_provider_order": _normalize_provider_csv(persisted_auto_order),
        "models": {
            "local": settings.ollama_model,
            "groq": settings.groq_model,
            "anthropic_fast": settings.anthropic_model_fast,
            "anthropic_premium": settings.anthropic_model_premium,
            "openrouter": settings.openrouter_model,
        },
        "keys": {
            "anthropic_configured": bool(settings.anthropic_api_key),
            "groq_configured": bool(settings.groq_api_key),
            "openrouter_configured": bool(settings.openrouter_api_key),
        },
    }
