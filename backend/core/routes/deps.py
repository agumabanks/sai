"""
Sanaa AI — Shared route dependencies and state.
Centralizes objects that multiple routers need (brain, agents, adapters, etc.)
so they can be imported without circular dependencies via main.py.
"""

from __future__ import annotations

import json
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

# ── Recent event store (Redis-backed with in-memory cache) ───────────────
# Events are kept in memory for fast reads and persisted to Redis so the
# dashboard live feed survives restarts.
_recent_events: list[dict] = []
MAX_EVENTS = 50
RECENT_EVENTS_REDIS_KEY = "sanaa:recent_events"
RECENT_EVENTS_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
_recent_event_redis: Optional[object] = None  # redis.asyncio.Redis when available

BRAIN_PROVIDERS = {"auto", "local", "groq", "claude", "openrouter", "soldier"}
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


# ── Recent event store helpers ───────────────────────────────────────────

def init_recent_events_store(redis_url: str = None):
    """Initialize the Redis client for recent events. Safe to call repeatedly."""
    global _recent_event_redis
    if _recent_event_redis is not None:
        return
    if not redis_url:
        return
    try:
        import redis.asyncio as aioredis
        _recent_event_redis = aioredis.from_url(redis_url, decode_responses=True)
        logger.info("Recent events store using Redis backend")
    except Exception as e:
        logger.warning(f"Redis unavailable for recent events store, using memory only: {e}")


async def close_recent_events_store():
    """Gracefully close the Redis client for recent events."""
    global _recent_event_redis
    if _recent_event_redis is not None:
        try:
            await _recent_event_redis.close()
        except Exception:
            pass
        _recent_event_redis = None


async def load_recent_events():
    """Load the recent event cache from Redis on startup."""
    global _recent_events
    if _recent_event_redis is not None:
        try:
            raw = await _recent_event_redis.get(RECENT_EVENTS_REDIS_KEY)
            if raw:
                loaded = json.loads(raw)
                if isinstance(loaded, list):
                    _recent_events[:] = loaded[:MAX_EVENTS]
                    logger.info(f"Loaded {len(_recent_events)} recent events from Redis")
                    return
        except Exception as e:
            logger.warning(f"Failed to load recent events from Redis: {e}")
    _recent_events[:] = []


async def _persist_recent_events():
    """Persist the in-memory event cache to Redis."""
    if _recent_event_redis is not None:
        try:
            await _recent_event_redis.set(
                RECENT_EVENTS_REDIS_KEY,
                json.dumps(_recent_events, default=str),
                ex=RECENT_EVENTS_TTL_SECONDS,
            )
        except Exception as e:
            logger.warning(f"Failed to persist recent events to Redis: {e}")


async def add_recent_events(events: list[dict]):
    """Prepend events to the in-memory cache and persist to Redis."""
    if not events:
        return
    _recent_events[:] = (list(events) + _recent_events)[:MAX_EVENTS]
    await _persist_recent_events()


def get_recent_events(limit: int = MAX_EVENTS, offset: int = 0) -> list[dict]:
    """Return a slice of the recent event cache."""
    return _recent_events[offset:offset + limit]


# ── Auth helpers ─────────────────────────────────────────────────────────

def get_current_user(request: Request) -> Optional[dict]:
    """Get user from signed session cookie. Returns None if not authenticated."""
    email = request.session.get("email")
    if not email:
        return None
    role = request.session.get("role")
    if not role:
        if email.lower() == (settings.root_admin_email or "banks@sanaa.co").lower():
            role = "admin"
        elif email.lower() == (settings.admin_email or "").lower():
            role = "admin"
        else:
            role = "operator"
    return {
        "email": email,
        "role": role,
        "name": request.session.get("name") or email,
        "logged_in_at": request.session.get("logged_in_at", ""),
        "auth_method": request.session.get("auth_method", "session"),
        "is_root": email.lower() == (settings.root_admin_email or "banks@sanaa.co").lower(),
    }


def resolve_actor(request: Request) -> dict:
    """Resolve the authenticated actor from session or trusted bridge headers."""
    user = get_current_user(request)
    if user:
        return user

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if token == settings.mac_client_api_key:
            email = (request.headers.get("X-Sanaa-User") or "system@bridge").strip()
            role = (request.headers.get("X-Sanaa-Role") or "admin").strip().lower()
            if role not in {"admin", "operator", "viewer", "seller"}:
                role = "admin"
            return {
                "email": email,
                "role": role,
                "name": (request.headers.get("X-Sanaa-Name") or email).strip(),
                "is_bridge": True,
            }

    raise HTTPException(status_code=401, detail="Not authenticated")


def require_auth(request: Request) -> dict:
    """Dependency: require session user OR valid Bearer token."""
    return resolve_actor(request)


def is_admin(actor: dict) -> bool:
    return str(actor.get("role", "")).lower() == "admin"


def is_root_admin(actor: dict) -> bool:
    email = str(actor.get("email", "")).strip().lower()
    return email == (settings.root_admin_email or "banks@sanaa.co").lower()


def is_user_admin(actor: dict) -> bool:
    return is_admin(actor) or is_root_admin(actor)


def require_user_admin(actor: dict) -> dict:
    if not is_user_admin(actor):
        raise HTTPException(status_code=403, detail="Administrator access required")
    return actor


def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify Bearer token for device/API access."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing API key")
    if credentials.credentials != settings.mac_client_api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return credentials.credentials


class RateLimit:
    """Configurable rate-limit dependency.

    Usage:
        @router.post("/api/example")
        async def example(_rate: None = Depends(RateLimit(limit=30))):
            ...
    """

    def __init__(self, limit: int = 60, fail_closed: bool = True):
        self.limit = limit
        self.fail_closed = fail_closed

    async def __call__(self, request: Request):
        client_ip = request.client.host if request.client else "unknown"
        key = f"ip:{client_ip}"
        allowed = await rate_limiter.check(key, limit=self.limit, fail_closed=self.fail_closed)
        if not allowed:
            remaining = await rate_limiter.get_remaining(key, limit=self.limit)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again in 60 seconds.",
                headers={"Retry-After": "60", "X-RateLimit-Remaining": str(remaining)},
            )


async def check_rate_limit(request: Request, limit: int = 60):
    """Backwards-compatible rate limit check dependency (fail-closed)."""
    return await RateLimit(limit=limit, fail_closed=True)(request)


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
    return ",".join(normalized or ["groq"])


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
    elif key == "soldier":
        settings.soldier_model = model_value


def _current_model_for_provider(provider: str, claude_source: str) -> str:
    """Return the canonical model string shown for a provider in the admin pane."""
    if provider == "local":
        return settings.ollama_model
    if provider == "groq":
        return settings.groq_model
    if provider == "openrouter":
        return settings.openrouter_model
    if provider == "soldier":
        return settings.soldier_model
    if provider == "claude":
        cs = (claude_source or settings.brain_claude_source or "anthropic").lower()
        if cs == "groq":
            return settings.groq_model
        if cs == "openrouter":
            return settings.openrouter_model
        return settings.anthropic_model_premium
    return ""


def _model_key_for_provider(provider: str, claude_source: str) -> str:
    """Return the models-map key that should be updated for a provider."""
    if provider == "local":
        return "local"
    if provider == "groq":
        return "groq"
    if provider == "openrouter":
        return "openrouter"
    if provider == "soldier":
        return "soldier"
    if provider == "claude":
        cs = (claude_source or settings.brain_claude_source or "anthropic").lower()
        if cs == "groq":
            return "groq"
        if cs == "openrouter":
            return "openrouter"
        return "anthropic_premium"
    return ""


async def _brain_config_snapshot() -> dict:
    from core.database import SystemKnowledge

    persisted_provider = await SystemKnowledge.get_pref("brain.provider", default=brain.get_current_provider() or "auto")
    persisted_claude_source = await SystemKnowledge.get_pref("brain.claude_source", default=settings.brain_claude_source)
    persisted_auto_order = await SystemKnowledge.get_pref("brain.auto_provider_order", default=settings.brain_auto_provider_order)

    return {
        "provider": persisted_provider,
        "current_provider": brain.get_current_provider(),
        "providers": sorted(BRAIN_PROVIDERS),
        "claude_source": persisted_claude_source,
        "auto_provider_order": _normalize_provider_csv(persisted_auto_order),
        "models": {
            "local": settings.ollama_model,
            "groq": settings.groq_model,
            "anthropic_fast": settings.anthropic_model_fast,
            "anthropic_premium": settings.anthropic_model_premium,
            "openrouter": settings.openrouter_model,
            "soldier": settings.soldier_model,
        },
        "current_model": _current_model_for_provider(persisted_provider, persisted_claude_source),
        "model_key": _model_key_for_provider(persisted_provider, persisted_claude_source),
        "keys": {
            "anthropic_configured": bool(settings.anthropic_api_key),
            "groq_configured": bool(settings.groq_api_key),
            "openrouter_configured": bool(settings.openrouter_api_key),
        },
    }
