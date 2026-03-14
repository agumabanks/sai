"""
Sanaa AI — Operations Agent
Main FastAPI application with session auth, dashboard, and multi-channel routing.

Routes are split into modular APIRouter files under core/routes/.
This file handles app creation, middleware, lifespan, and router includes.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from core.config import get_settings
from core.database import init_db, utcnow
from core.integrations.whatsapp_saas_manager import WhatsAppSaaSManager

from core.agents.server_health import ServerHealthAgent
from core.agents.app_monitor import AppMonitorAgent
from core.agents.email_agent import EmailInboxAgent
from core.agents.news_agent import NewsAgent
from core.agents.web_test_agent import WebTestAgent
from core.agents.report_agent import ReportAgent
from core.agents.device_agent import DeviceAgent
from core.brain.engine import Brain

from core.utils.password import hash_password, is_bcrypt_hash
from core.security.rate_limiter import RateLimiter
from core.router.message_router import MessageRouter
from core.channels.web.adapter import WebChannelAdapter
from core.agents.watchdog import ServerWatchdog
from core.agents.healer import SelfHealer
from core.intelligence.scanner import IntelligenceScanner
from core.intelligence.skills import AutonomousSkillMapper
from core.workflows.loader import WorkflowLoader
from core.workflows.runtime import WorkflowRuntime

# Route modules
from core.routes import deps as route_deps
from core.routes.auth import router as auth_router
from core.routes.commands import router as commands_router
from core.routes.skills import router as skills_router
from core.routes.status import router as status_router
from core.routes.channels import router as channels_router
from core.routes.intelligence import router as intelligence_router
from core.routes.devices import router as devices_router
from core.routes.alerts import router as alerts_router
from core.routes.sessions import router as sessions_router
from core.routes.config import router as config_router
from core.routes.workflows import router as workflows_router
from core.routes.watchdog import router as watchdog_router
from core.routes.sellers import router as sellers_router

logger = logging.getLogger(__name__)
settings = get_settings()

# Resolve static file directory
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "web" / "static"


# ==================== AGENTS & CHANNELS ====================

brain = Brain()
server_health = ServerHealthAgent()
app_monitor = AppMonitorAgent()
email_agent = EmailInboxAgent()
news_agent = NewsAgent()
web_test = WebTestAgent()
report_agent = ReportAgent()
device_agent = DeviceAgent()

web_channel = WebChannelAdapter()
router = MessageRouter(brain=brain)
router.register_channel(web_channel)

rate_limiter = RateLimiter(redis_url=settings.redis_url, default_rpm=60)

watchdog = ServerWatchdog()
healer = SelfHealer()

scanner = IntelligenceScanner()
skill_mapper = AutonomousSkillMapper()
workflow_loader = WorkflowLoader()
workflow_runtime = WorkflowRuntime(skill_registry=brain.skill_registry, brain=brain)

whatsapp_saas = WhatsAppSaaSManager(
    source_path=settings.whatsapp_saas_source_path,
    base_url=settings.whatsapp_saas_base_url,
    vendor_uid=settings.whatsapp_saas_vendor_uid,
    api_token=settings.whatsapp_saas_api_token,
)

# Wire shared state into route_deps so all routers can access singletons
route_deps.init_shared_state(
    brain_inst=brain,
    router_inst=router,
    web_channel_inst=web_channel,
    whatsapp_saas_inst=whatsapp_saas,
    rate_limiter_inst=rate_limiter,
    server_health_inst=server_health,
    watchdog_inst=watchdog,
    healer_inst=healer,
    scanner_inst=scanner,
    skill_mapper_inst=skill_mapper,
    workflow_loader_inst=workflow_loader,
    workflow_runtime_inst=workflow_runtime,
)


# ==================== STARTUP HELPERS ====================

async def _migrate_plaintext_api_keys():
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


async def _load_persisted_brain_config():
    """Apply persisted brain settings from DB to runtime settings/brain on startup."""
    from core.database import SystemKnowledge

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


# ==================== LIFESPAN ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    app.state.rate_limiter = rate_limiter

    # Auto-migrate admin password to bcrypt hash on first run
    if settings.admin_password and settings.admin_password != "CHANGE_THIS":
        if not settings.admin_password_hash or not is_bcrypt_hash(settings.admin_password_hash):
            hashed = hash_password(settings.admin_password)
            settings.admin_password_hash = hashed
            logger.info("Admin password auto-migrated to bcrypt hash")

    await _migrate_plaintext_api_keys()
    await _load_persisted_brain_config()
    await web_channel.connect()

    # WhatsApp (optional)
    if settings.whatsapp_enabled:
        try:
            from core.channels.whatsapp.adapter import WhatsAppAdapter
            wa = WhatsAppAdapter(
                sidecar_url=settings.whatsapp_sidecar_url,
                allowed_numbers=settings.whatsapp_allowed_list or None,
                on_message=lambda msg: router.route(msg),
            )
            route_deps.set_whatsapp_adapter(wa)
            router.register_channel(wa)
            await wa.connect()
            logger.info("WhatsApp channel enabled")
        except Exception as e:
            logger.warning(f"WhatsApp channel failed to start: {e}")

    # Telegram (optional)
    if settings.telegram_enabled and settings.telegram_bot_token:
        try:
            from core.channels.telegram.adapter import TelegramAdapter
            tg = TelegramAdapter(
                bot_token=settings.telegram_bot_token,
                allowed_chat_ids=settings.telegram_allowed_chat_list or None,
                on_message=lambda msg: router.route(msg),
            )
            route_deps.set_telegram_adapter(tg)
            router.register_channel(tg)
            await tg.connect()
            logger.info("Telegram channel enabled")
        except Exception as e:
            logger.warning(f"Telegram channel failed to start: {e}")

    if settings.whatsapp_saas_enabled:
        health = await whatsapp_saas.health_check()
        logger.info(f"WhatsApp SaaS (wa.sanaa.co) health: {'OK' if health.get('healthy') else 'DOWN'}")

    print(f"Sanaa AI is online ({settings.app_env}) — channels: {list(router.channels.keys())}")
    yield

    # Shutdown
    if route_deps.whatsapp_adapter:
        await route_deps.whatsapp_adapter.disconnect()
    if route_deps.telegram_adapter:
        await route_deps.telegram_adapter.disconnect()
    await web_channel.disconnect()
    print("Sanaa AI shutting down")


# ==================== APP INIT ====================

app = FastAPI(
    title=settings.app_name,
    description="Sanaa AI Operations Agent",
    version="2.2.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_debug else None,
    redoc_url=None,
)

# Audit Middleware
try:
    from core.security.audit_middleware import AuditMiddleware
    app.add_middleware(AuditMiddleware)
except ImportError:
    logger.warning("AuditMiddleware not available — audit logging disabled")

# Session middleware (added LAST so it runs FIRST — outermost)
app.add_middleware(SessionMiddleware, secret_key=settings.app_secret, max_age=86400 * 7)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ai.sanaa.co"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ==================== REGISTER ROUTERS ====================

app.include_router(auth_router)
app.include_router(commands_router)
app.include_router(skills_router)
app.include_router(status_router)
app.include_router(channels_router)
app.include_router(intelligence_router)
app.include_router(devices_router)
app.include_router(alerts_router)
app.include_router(sessions_router)
app.include_router(config_router)
app.include_router(workflows_router)
app.include_router(watchdog_router)
app.include_router(sellers_router)
