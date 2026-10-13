"""
Sanaa AI — Operations Agent
Main FastAPI application with session auth, dashboard, and multi-channel routing.

Routes are split into modular APIRouter files under core/routes/.
This file handles app creation, lifespan, and router includes.
Startup helpers and middleware setup live in core.startup to keep this file small.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from core.config import get_settings, validate_production_secrets
from core.database import init_db
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
from core.skills.hot_reload import SkillFileWatcher

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
from core.routes.tenants import router as tenants_router, seed_initial_tenants
from core.routes.marketing import router as marketing_router
from core.routes.audit import router as audit_router
from core.routes.system_os import router as system_os_router
from core.routes.extras import router as extras_router
from core.routes.auth_os import router as auth_os_router
from core.routes.terminal_os import router as terminal_os_router
from core.routes.browser_os import router as browser_os_router
from core.routes.notes_os import router as notes_os_router
from core.routes.users_os import router as users_os_router
from core.routes.contacts_os import router as contacts_os_router
from core.routes.files_os import router as files_os_router
from core.routes.cloud_os import router as cloud_os_router
from core.routes.analytics_os import router as analytics_os_router
from core.routes.soko_os import router as soko_os_router
from core.routes.papers_os import router as papers_os_router
from core.routes.app_launcher_os import router as app_launcher_router
from core.routes.telemetry_os import router as telemetry_router
from core.routes.memory import router as memory_router
from core.routes.brain_intelligence import router as brain_intelligence_router
from core.routes.brain_graph import router as brain_graph_router
from core.routes.device_army import router as device_army_router
from core.routes.account_os import router as account_os_router
from core.routes.wallpapers_os import router as wallpapers_os_router
from core.services.device_ws_manager import ensure_watchdog_running, router as device_ws_router
from core.services.device_orchestrator import orchestrator as device_orchestrator

from core.startup import migrate_plaintext_api_keys, load_persisted_brain_config, setup_middleware

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
route_deps.init_recent_events_store(settings.redis_url)

watchdog = ServerWatchdog()
healer = SelfHealer()

scanner = IntelligenceScanner()
skill_mapper = AutonomousSkillMapper()
workflow_loader = WorkflowLoader()
workflow_runtime = WorkflowRuntime(skill_registry=brain.skill_registry, brain=brain)

skill_watcher = SkillFileWatcher(
    skills_dir=str(BASE_DIR / "skills"),
    skill_registry=brain.skill_registry,
)

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


# ==================== LIFESPAN ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fatal startup guard: reject default/placeholder secrets in production.
    validate_production_secrets()

    await init_db()
    await seed_initial_tenants()
    app.state.rate_limiter = rate_limiter

    # Auto-migrate admin password to bcrypt hash on first run
    if settings.admin_password and settings.admin_password != "CHANGE_THIS":
        if not settings.admin_password_hash or not is_bcrypt_hash(settings.admin_password_hash):
            hashed = hash_password(settings.admin_password)
            settings.admin_password_hash = hashed
            logger.info("Admin password auto-migrated to bcrypt hash")

    await migrate_plaintext_api_keys()
    await load_persisted_brain_config(brain)
    await route_deps.load_recent_events()
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

    # Start skill hot-reload file watcher (background daemon thread)
    try:
        skill_watcher.start()
    except Exception as e:
        logger.warning(f"Skill hot-reload watcher failed to start: {e}")

    # Start Device Army WebSocket watchdog
    try:
        await ensure_watchdog_running()
        logger.info("Device Army WS watchdog started")
    except Exception as e:
        logger.warning(f"Device Army WS watchdog failed to start: {e}")

    # Start Device Army orchestrator scheduler
    try:
        await device_orchestrator.start_scheduler()
        logger.info("Device Army orchestrator scheduler started")
    except Exception as e:
        logger.warning(f"Device Army orchestrator scheduler failed to start: {e}")

    print(f"Sanaa AI is online ({settings.app_env}) — channels: {list(router.channels.keys())}")
    yield

    # Shutdown
    skill_watcher.stop()
    if route_deps.whatsapp_adapter:
        await route_deps.whatsapp_adapter.disconnect()
    if route_deps.telegram_adapter:
        await route_deps.telegram_adapter.disconnect()
    await route_deps.close_recent_events_store()
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

setup_middleware(app, STATIC_DIR)


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
app.include_router(tenants_router)
app.include_router(marketing_router)
app.include_router(audit_router)
app.include_router(system_os_router)
app.include_router(extras_router)
app.include_router(auth_os_router)
app.include_router(notes_os_router)
app.include_router(users_os_router)
app.include_router(contacts_os_router)
app.include_router(files_os_router)
app.include_router(cloud_os_router)
app.include_router(analytics_os_router)
app.include_router(soko_os_router)
app.include_router(papers_os_router)
app.include_router(app_launcher_router)
app.include_router(telemetry_router)
app.include_router(terminal_os_router)
app.include_router(browser_os_router)
app.include_router(memory_router)
app.include_router(brain_intelligence_router)
app.include_router(brain_graph_router)
app.include_router(device_army_router)
app.include_router(account_os_router)
app.include_router(wallpapers_os_router)
app.include_router(device_ws_router)
