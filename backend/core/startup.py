"""
Sanaa AI — Application startup helpers and middleware setup.

Helpers extracted from main.py to keep it focused on app creation and router
registration. Everything here is import-side safe and does not rely on the
main module.
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from core.config import get_settings
from core.database import utcnow
from core.routes import deps as route_deps

logger = logging.getLogger(__name__)
settings = get_settings()


async def migrate_plaintext_api_keys() -> None:
    """One-time migration: encrypt any plaintext API keys in system_knowledge."""
    from core.database import SystemKnowledge, AsyncSessionLocal
    from sqlalchemy import select

    try:
        from core.utils.crypto import is_encrypted, encrypt_value
    except Exception as e:
        logger.warning(f"Crypto module unavailable, skipping API key migration: {e}")
        return

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SystemKnowledge).where(
                    SystemKnowledge.key.like("brain.api_key.%"),
                    SystemKnowledge.domain == "preference",
                )
            )
            rows = result.scalars().all()
            migrated = 0
            for row in rows:
                if row.value and not is_encrypted(row.value):
                    row.value = encrypt_value(row.value)
                    row.updated_at = utcnow()
                    migrated += 1
            if migrated:
                await session.commit()
                logger.info(f"Migrated {migrated} plaintext API key(s) to encrypted storage")
            else:
                logger.debug("No plaintext API keys to migrate")
    except Exception as e:
        logger.error(f"Failed to migrate plaintext API keys: {e}")


async def load_persisted_brain_config(brain) -> None:
    """Apply persisted brain settings from DB to runtime settings/brain on startup."""
    from core.database import SystemKnowledge
    from core.brain import get_shared_brain

    secret_pref_map = {
        "brain.api_key.anthropic": "anthropic",
        "brain.api_key.groq": "groq",
        "brain.api_key.openrouter": "openrouter",
    }
    for pref_key, provider in secret_pref_map.items():
        val = await SystemKnowledge.get_pref(pref_key, default=None)
        if val:
            route_deps._apply_runtime_secret(provider, val)

    model_pref_map = {
        "brain.model.local": "local",
        "brain.model.groq": "groq",
        "brain.model.anthropic_fast": "anthropic_fast",
        "brain.model.anthropic_premium": "anthropic_premium",
        "brain.model.openrouter": "openrouter",
    }
    for pref_key, model_key in model_pref_map.items():
        val = await SystemKnowledge.get_pref(pref_key, default=None)
        if val:
            route_deps._apply_runtime_brain_model(model_key, val)

    claude_source = await SystemKnowledge.get_pref("brain.claude_source", default=None)
    if claude_source in route_deps.CLAUDE_SOURCES:
        settings.brain_claude_source = claude_source

    auto_order = await SystemKnowledge.get_pref("brain.auto_provider_order", default=None)
    if auto_order:
        settings.brain_auto_provider_order = route_deps._normalize_provider_csv(auto_order)

    provider = await SystemKnowledge.get_pref("brain.provider", default="auto")
    if provider not in route_deps.BRAIN_PROVIDERS:
        provider = "auto"
    brain.switch_provider(provider)
    # Keep the shared brain singleton aligned because agents like NewsAgent
    # resolve their brain from get_shared_brain(), not the dashboard singleton.
    shared_brain = get_shared_brain()
    shared_brain.switch_provider(provider)


def setup_middleware(app: FastAPI, static_dir: Path) -> None:
    """Attach security, session, CORS and static-file middleware to the app."""
    # Audit middleware (optional)
    try:
        from core.security.audit_middleware import AuditMiddleware
        app.add_middleware(AuditMiddleware)
    except ImportError:
        logger.warning("AuditMiddleware not available — audit logging disabled")

    # Session middleware (added LAST so it runs FIRST — outermost)
    app.add_middleware(SessionMiddleware, secret_key=settings.app_secret, max_age=86400 * 7)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    # Static files
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
