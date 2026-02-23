"""
Sanaa AI — Operations Agent
Main FastAPI application with session auth, dashboard, and multi-channel routing.
"""

import os
import json
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urljoin

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks, Form, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy import select
import httpx

from core.config import get_settings
from core.database import init_db, get_db, Log, Command, DeviceReport, Alert, IntelligenceBriefing, StrategicSignal, SellerAccount, AuditLog
from core.integrations.whatsapp_saas_manager import WhatsAppSaaSManager

from core.agents.server_health import ServerHealthAgent
from core.agents.app_monitor import AppMonitorAgent
from core.agents.email_agent import EmailInboxAgent
from core.agents.news_agent import NewsAgent
from core.agents.web_test_agent import WebTestAgent
from core.agents.report_agent import ReportAgent
from core.agents.device_agent import DeviceAgent
from core.brain.engine import Brain

from core.router.message_router import MessageRouter
from core.router.internal_message import InternalMessage
from core.channels.web.adapter import WebChannelAdapter
from core.agents.watchdog import ServerWatchdog
from core.agents.healer import SelfHealer
from core.intelligence.scanner import IntelligenceScanner
from core.intelligence.skills import AutonomousSkillMapper
from core.workflows.loader import WorkflowLoader
from core.workflows.runtime import WorkflowRuntime
from core.policies import (
    get_tool_policy,
    save_tool_policy,
    build_skill_catalog,
    set_skill_enabled,
    set_skill_exposure,
    get_session_policy,
    save_session_policy,
    list_sessions,
    get_session_detail,
    reset_session_by_id,
    set_session_send_override,
    run_doctor,
)

logger = logging.getLogger(__name__)
settings = get_settings()
security = HTTPBearer(auto_error=False)

# Resolve template directory relative to this file
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "web" / "templates"
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

# Channel adapters
web_channel = WebChannelAdapter()
router = MessageRouter(brain=brain)
router.register_channel(web_channel)

# Watchdog + Healer
watchdog = ServerWatchdog()
healer = SelfHealer()

# Intelligence Security
scanner = IntelligenceScanner()
skill_mapper = AutonomousSkillMapper()
workflow_loader = WorkflowLoader()
workflow_runtime = WorkflowRuntime(skill_registry=brain.skill_registry, brain=brain)

# In-memory event store for dashboard live feed (bounded, last 50 events)
_recent_events: list[dict] = []
MAX_EVENTS = 50

BRAIN_PROVIDERS = {"auto", "local", "groq", "claude", "openrouter"}
CLAUDE_SOURCES = {"anthropic", "groq", "openrouter"}


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
        os.environ["ANTHROPIC_API_KEY"] = key
        return
    if provider == "groq":
        settings.groq_api_key = key
        os.environ["GROQ_API_KEY"] = key
        return
    if provider == "openrouter":
        settings.openrouter_api_key = key
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
            _apply_runtime_secret(provider, val)

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
            _apply_runtime_brain_model(model_key, val)

    claude_source = await SystemKnowledge.get_pref("brain.claude_source", default=None)
    if claude_source in CLAUDE_SOURCES:
        settings.brain_claude_source = claude_source

    auto_order = await SystemKnowledge.get_pref("brain.auto_provider_order", default=None)
    if auto_order:
        settings.brain_auto_provider_order = _normalize_provider_csv(auto_order)

    provider = await SystemKnowledge.get_pref("brain.provider", default="auto")
    if provider not in BRAIN_PROVIDERS:
        provider = "auto"
    brain.switch_provider(provider)


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

# Optional channels (connected during lifespan)
whatsapp_adapter = None
telegram_adapter = None

whatsapp_saas = WhatsAppSaaSManager(
    source_path=settings.whatsapp_saas_source_path,
    base_url=settings.whatsapp_saas_base_url,
    vendor_uid=settings.whatsapp_saas_vendor_uid,
    api_token=settings.whatsapp_saas_api_token,
)


# ==================== LIFESPAN ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global whatsapp_adapter, telegram_adapter

    await init_db()
    await _load_persisted_brain_config()
    await web_channel.connect()

    # WhatsApp (optional — only if enabled in config)
    if settings.whatsapp_enabled:
        try:
            from core.channels.whatsapp.adapter import WhatsAppAdapter
            whatsapp_adapter = WhatsAppAdapter(
                sidecar_url=settings.whatsapp_sidecar_url,
                allowed_numbers=settings.whatsapp_allowed_list or None,
                on_message=lambda msg: router.route(msg),
            )
            router.register_channel(whatsapp_adapter)
            await whatsapp_adapter.connect()
            logger.info("WhatsApp channel enabled")
        except Exception as e:
            logger.warning(f"WhatsApp channel failed to start: {e}")

    # Telegram (optional — only if token configured)
    if settings.telegram_enabled and settings.telegram_bot_token:
        try:
            from core.channels.telegram.adapter import TelegramAdapter
            telegram_adapter = TelegramAdapter(
                bot_token=settings.telegram_bot_token,
                allowed_chat_ids=settings.telegram_allowed_chat_list or None,
                on_message=lambda msg: router.route(msg),
            )
            router.register_channel(telegram_adapter)
            await telegram_adapter.connect()
            logger.info("Telegram channel enabled")
        except Exception as e:
            logger.warning(f"Telegram channel failed to start: {e}")

    if settings.whatsapp_saas_enabled:
        health = await whatsapp_saas.health_check()
        logger.info(f"WhatsApp SaaS (wa.sanaa.co) health: {'OK' if health.get('healthy') else 'DOWN'}")

    print(f"Sanaa AI is online ({settings.app_env}) — channels: {list(router.channels.keys())}")
    yield

    # Shutdown channels
    if whatsapp_adapter:
        await whatsapp_adapter.disconnect()
    if telegram_adapter:
        await telegram_adapter.disconnect()
    # WhatsJet runs independently via nginx/PHP-FPM — no stop needed
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

# Signed session cookies — survive restarts, cryptographically secure
# Audit Middleware — logs every request to audit_log table (must be inner to SessionMiddleware)
try:
    from core.security.audit_middleware import AuditMiddleware
    app.add_middleware(AuditMiddleware)
except ImportError:
    logger.warning("AuditMiddleware not available — audit logging disabled")

# Signed session cookies — survive restarts, cryptographically secure
# Added LAST so it runs FIRST (outermost)
app.add_middleware(SessionMiddleware, secret_key=settings.app_secret, max_age=86400 * 7)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ai.sanaa.co"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Templates — use the repo path, falls back to /opt/antigravity path
if TEMPLATE_DIR.exists():
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
else:
    templates = Jinja2Templates(directory="/opt/antigravity/web/templates")

# Static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ==================== AUTH HELPERS ====================

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
    # 1. Check session
    user = get_current_user(request)
    if user:
        return user
        
    # 2. Check Bearer token manually (more reliable for the bridge)
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


# ==================== LOGIN / LOGOUT ====================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    if email == settings.admin_email and password == settings.admin_password:
        request.session["email"] = email
        request.session["logged_in_at"] = datetime.now(timezone.utc).isoformat()
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Invalid email or password"}, status_code=401
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


# ==================== WEB DASHBOARD ====================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    health = await server_health.get_snapshot()
    recent_alerts = await Alert.get_recent(limit=20)
    recent_commands = await Command.get_recent(limit=10)
    devices = await DeviceReport.get_latest_all()
    channels_status = router.get_channel_status()

    briefings = await IntelligenceBriefing.get_recent(limit=5)
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "health": health,
        "alerts": recent_alerts,
        "commands": recent_commands,
        "devices": devices,
        "channels": channels_status,
        "briefings": briefings,
        "now": datetime.now(timezone.utc),
        "user": user,
    })


# ==================== COMMAND API (routed through channels) ====================

class CommandRequest(BaseModel):
    command: str
    context: Optional[str] = None
    approval_required: bool = True


class SkillRunRequest(BaseModel):
    args: dict = Field(default_factory=dict)
    session_id: Optional[str] = None
    channel: str = "web"
    sender_id: str = "admin"


class WorkflowRunRequest(BaseModel):
    args: dict = Field(default_factory=dict)
    channel: str = "web"
    started_by: str = "admin"


class ToolPolicyUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[str] = None
    allow: Optional[list[str]] = None
    deny: Optional[list[str]] = None
    groups: Optional[dict] = None
    by_provider: Optional[dict] = None
    by_channel: Optional[dict] = None


class SkillExposureUpdateRequest(BaseModel):
    exposure: str


class WorkflowResumeRequest(BaseModel):
    approved: bool = True
    resume_token: str


class SessionPolicyUpdateRequest(BaseModel):
    dm_scope: Optional[str] = None
    reset: Optional[dict] = None
    send_policy: Optional[dict] = None
    reset_triggers: Optional[list[str]] = None


class SessionSendPolicyRequest(BaseModel):
    mode: str  # on|off|inherit


@app.post("/api/command")
async def execute_command(
    request: Request, 
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_auth)
):
    """Handle commands from both JSON API and htmx form submissions.
    Now routes through the message router for memory + context integration."""

    content_type = request.headers.get("content-type", "")

    # Support both JSON (API clients) and form-encoded (htmx dashboard)
    if "application/json" in content_type:
        body = await request.json()
        command_text = body.get("command", "")
    else:
        form = await request.form()
        command_text = form.get("command", "")

    if not command_text.strip():
        raise HTTPException(status_code=400, detail="Empty command")

    # Log the command
    cmd = await Command.create(text=command_text, context=None, status="processing")

    # Intercept "briefing" / "news" commands for on-demand intelligence briefings
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

    # Intercept "scan" commands for Intelligence Scanner
    if command_text.lower().strip() in ["scan", "scan system", "run scan", "check security"]:
        background_tasks.add_task(scanner.scan_all)
        response_text = "🚀 Intelligence Scan initiated.\n\nAuditing all repositories for:\n- Shell injection risks\n- Dynamic code execution\n- Credential leaks\n\nCheck the dashboard for live results."
        
        await Command.update_by_id(cmd.id, status="completed")
        
        if "hx-request" in request.headers:
            return HTMLResponse(f'<div class="text-green-400 whitespace-pre-wrap">{response_text}</div>')
        return JSONResponse({"id": cmd.id, "status": "completed", "response": response_text})

    # Intercept "run skill <name> [json]" for quick operator actions
    if command_text.lower().startswith("run skill "):
        await brain.ensure_skills_loaded()
        raw = command_text[len("run skill "):].strip()
        skill_name = raw.split(" ", 1)[0].strip()
        args = {}
        if " " in raw:
            maybe_json = raw.split(" ", 1)[1].strip()
            if maybe_json.startswith("{"):
                try:
                    args = json.loads(maybe_json)
                except Exception:
                    args = {}
        result = await brain.execute_skill(
            name=skill_name,
            args=args,
            session_id=f"cmd:{cmd.id}",
            channel="web",
            sender_id=user["email"],
        )
        response_text = result.get("output") or result.get("error") or json.dumps(result.get("data") or {}, default=str)
        await Command.update_by_id(cmd.id, status="completed" if result.get("success") else "failed")
        if "hx-request" in request.headers:
            return HTMLResponse(f'<div class="text-green-400 whitespace-pre-wrap">{response_text}</div>')
        return JSONResponse({"id": cmd.id, "status": "completed" if result.get("success") else "failed", "result": result, "response": response_text})

    # Intercept "run workflow <name> [json]" for orchestration
    if command_text.lower().startswith("run workflow "):
        await brain.ensure_skills_loaded()
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
        for w in workflow_loader.discover():
            if w.name == workflow_name:
                workflow = w
                break
        if not workflow:
            await Command.update_by_id(cmd.id, status="failed")
            raise HTTPException(404, f"Workflow not found: {workflow_name}")
        run_id = await workflow_runtime.start(
            workflow,
            args=wf_args,
            started_by=user["email"],
            channel="web",
        )
        response_text = f"🔁 Workflow '{workflow_name}' started (run_id={run_id})"
        await Command.update_by_id(cmd.id, status="completed")
        if "hx-request" in request.headers:
            return HTMLResponse(f'<div class="text-green-400 whitespace-pre-wrap">{response_text}</div>')
        return JSONResponse({"id": cmd.id, "status": "completed", "run_id": run_id, "response": response_text})

    # Intercept "use brain" command
    if command_text.lower().startswith("use brain"):
        provider = command_text.lower().split("use brain")[-1].strip()
        if provider in BRAIN_PROVIDERS:
            brain.switch_provider(provider)
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
                _apply_runtime_secret(provider, key)
                from core.database import SystemKnowledge
                await SystemKnowledge.set_pref(f"brain.api_key.{provider}", key, source="user_command")
                brain.registry.models = brain.registry._build_model_chain()

                response_text = f"🔑 {provider.title()} API key configured successfully."
                await Command.update_by_id(cmd.id, status="completed")
                if "hx-request" in request.headers:
                    return HTMLResponse(f'<div class="text-green-400 whitespace-pre-wrap">{response_text}</div>')
                return JSONResponse({"id": cmd.id, "status": "completed", "response": response_text})

    # Build an InternalMessage and route through the channel system
    msg = await web_channel.receive_message({
        "command": command_text,
        "email": user["email"],
        "name": user["email"],
    })

    if not msg:
        raise HTTPException(status_code=400, detail="Invalid command")

    # Route through the brain with full memory/context
    response_text = await router.route(msg)

    # Update command record
    await Command.update_by_id(cmd.id, status="completed")

    # Return HTML fragment for htmx, JSON for API
    if "hx-request" in request.headers:
        return HTMLResponse(
            f'<div class="text-green-400 whitespace-pre-wrap">{response_text}</div>'
        )

    return JSONResponse({
        "id": cmd.id,
        "status": "completed",
        "response": response_text,
    })


@app.post("/api/command/{cmd_id}/approve")
async def approve_command(cmd_id: str, request: Request, background_tasks: BackgroundTasks, user: dict = Depends(require_auth)):

    cmd = await Command.get(cmd_id)
    if not cmd:
        raise HTTPException(404, "Command not found")
    if cmd.status != "awaiting_approval":
        raise HTTPException(400, "Command not awaiting approval")

    background_tasks.add_task(brain.execute_plan, cmd.id, cmd.proposed_plan or [])
    await Command.update_by_id(cmd.id, status="executing")

    if "hx-request" in request.headers:
        return HTMLResponse('<div class="text-green-400">Approved. Executing now...</div>')

    return {"status": "approved", "message": "Executing now"}


# ==================== STATUS API ====================

@app.get("/api/status")
async def api_status(user: dict = Depends(require_auth)):
    """Full system status — supports session and API key."""

    health = await server_health.get_snapshot()
    alerts = await Alert.get_recent(limit=50)
    devices = await DeviceReport.get_latest_all()
    
    from core.database import SystemKnowledge
    brain_provider = await SystemKnowledge.get_pref("brain.provider", default="auto")
    
    # Get active failure counters (from Healer logic)
    # We can peek at 'fail_count.*' keys
    from sqlalchemy import select
    from core.database import AsyncSessionLocal
    fail_counts = []
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SystemKnowledge).where(SystemKnowledge.key.like("fail_count.%"))
        )
        for obj in result.scalars().all():
            if obj.value and int(obj.value) > 0:
                fail_counts.append({"metric": obj.key, "count": int(obj.value)})

    return {
        "server": health,
        "brain": {
            "active_provider": brain_provider,
            "status": "ready"
        },
        "healer": {
            "active_failures": fail_counts,
            "tier_thresholds": {
                "t2": healer.TIER_2_THRESHOLD,
                "t3": healer.TIER_3_THRESHOLD,
                "t4": healer.TIER_4_THRESHOLD
            }
        },
        "alerts": {
            "unacknowledged": len([a for a in alerts if not getattr(a, "acknowledged", False)]),
            "recent": len(alerts),
        },
        "devices": {
            "active": len(devices),
        },
        "channels": router.get_channel_status(),
    }


@app.get("/api/health")
async def api_health():
    """Public health check (no auth required)."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": "2.2.0",
        "channels": list(router.channels.keys()),
    }


# ==================== CHANNEL API ====================

@app.get("/api/channels")
async def list_channels(request: Request, user: dict = Depends(require_auth)):
    """Get status of all registered channels."""

    status = router.get_channel_status()

    # Add extra detail for WhatsApp
    if whatsapp_adapter:
        status["whatsapp"]["detail"] = whatsapp_adapter.get_status()

    # Add extra detail for Telegram
    if telegram_adapter:
        status["telegram"]["detail"] = telegram_adapter.get_status()

    return status


@app.post("/api/channels/whatsapp/pair")
async def whatsapp_pair(request: Request, user: dict = Depends(require_auth)):
    """Initiate WhatsApp QR pairing."""

    if not whatsapp_adapter:
        raise HTTPException(400, "WhatsApp channel not enabled")

    if whatsapp_adapter.is_connected():
        return {"status": "already_connected", "phone": whatsapp_adapter.phone_number}

    # Request QR from sidecar
    await whatsapp_adapter._send({"type": "connect"})

    return {
        "status": "pairing",
        "qr": whatsapp_adapter.current_qr,
        "message": "Scan QR code with WhatsApp",
    }


@app.get("/api/channels/whatsapp/qr")
async def whatsapp_qr(request: Request, user: dict = Depends(require_auth)):
    """Get current WhatsApp QR code for dashboard display."""

    if not whatsapp_adapter:
        raise HTTPException(400, "WhatsApp channel not enabled")

    return {
        "qr": whatsapp_adapter.current_qr,
        "connected": whatsapp_adapter.is_connected(),
        "phone": whatsapp_adapter.phone_number,
    }


# ==================== INTEGRATIONS API ====================

# --- Internal (admin dashboard) ---

@app.get("/api/integrations/whatsapp-saas/status")
async def whatsapp_saas_status(user: dict = Depends(require_auth)):
    if not settings.whatsapp_saas_enabled:
        raise HTTPException(400, "WhatsApp SaaS integration is disabled")
    return await whatsapp_saas.status()


@app.get("/api/integrations/whatsapp-saas/routes")
async def whatsapp_saas_routes(user: dict = Depends(require_auth)):
    if not settings.whatsapp_saas_enabled:
        raise HTTPException(400, "WhatsApp SaaS integration is disabled")
    routes = whatsapp_saas.discover_api_routes()
    return {"count": len(routes), "routes": routes}


# ==================== WHATSAPP API BRIDGE ====================
# External API for Soko, FX, Cards and other Sanaa apps.
# Authenticated via WHATSAPP_API_KEY Bearer token.

def verify_whatsapp_api_key(request: Request):
    """Verify Bearer token for WhatsApp API bridge access."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = auth.split(" ", 1)[1]
    # Accept either the dedicated WhatsApp API key or admin API key
    if token not in (settings.whatsapp_api_key, settings.mac_client_api_key):
        raise HTTPException(403, "Invalid API key")
    if not settings.whatsapp_saas_enabled:
        raise HTTPException(503, "WhatsApp service not available")
    return token


@app.get("/api/whatsapp/status")
async def wa_bridge_status(token: str = Depends(verify_whatsapp_api_key)):
    """Health status of WhatsJet."""
    return await whatsapp_saas.status()


@app.get("/api/intelligence/latest-signals")
async def get_latest_signals(limit: int = 10, user: dict = Depends(require_auth)):
    """Fetch structured strategic signals for the dashboard."""
    from core.database import StrategicSignal, AsyncSessionLocal
    from sqlalchemy import select, desc
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(StrategicSignal)
            .order_by(desc(StrategicSignal.created_at))
            .limit(limit)
        )
        signals = result.scalars().all()
        return [
            {
                "id": s.id,
                "title": s.title,
                "summary": s.summary,
                "score": s.score,
                "classification": s.classification,
                "business_impact": s.business_impact,
                "source": s.source,
                "link": s.link,
                "tags": s.tags,
                "created_at": s.created_at.isoformat() if s.created_at else None
            }
            for s in signals
        ]


@app.get("/api/intelligence/wisdom")
async def get_system_wisdom(user: dict = Depends(require_auth)):
    """Fetch the latest architectural wisdom/insight from the WisdomAgent."""
    from core.agents.wisdom import WisdomAgent
    agent = WisdomAgent()
    wisdom = await agent.get_latest_insight()
    return wisdom or {"message": "System is too stable to provide specific wisdom yet."}


@app.get("/api/intelligence/advisor/watchdog")
async def get_watchdog_advisor(user: dict = Depends(require_auth)):
    """Fetch the latest sanaa-clade watchdog advisory (best-effort ops RCA/prediction)."""
    from core.database import SystemKnowledge
    val = await SystemKnowledge.get_pref("watchdog.advisor.latest", default=None, domain="wisdom")
    if not val:
        return {"message": "No watchdog advisory available yet."}
    try:
        return json.loads(val)
    except Exception:
        return {"raw": val}


@app.get("/api/intelligence/briefings/qa/latest")
async def get_latest_briefing_qa(user: dict = Depends(require_auth)):
    """Fetch the latest news briefing QA/repair assessment."""
    from core.database import SystemKnowledge
    val = await SystemKnowledge.get_pref("briefing.latest.qa", default=None, domain="news")
    if not val:
        return {"message": "No briefing QA available yet."}
    try:
        return json.loads(val)
    except Exception:
        return {"raw": val}


@app.get("/api/skills")
async def list_skills_api(user: dict = Depends(require_auth)):
    """List loaded skills and their schemas for dashboard/operator use."""
    await brain.ensure_skills_loaded()
    effective_provider = brain.get_effective_tool_provider() if hasattr(brain, "get_effective_tool_provider") else brain.get_current_provider()
    catalog = await build_skill_catalog(brain.skill_registry, provider=effective_provider, channel="web")
    return {
        "count": brain.skill_registry.count,
        "skills": catalog,
        "tools": brain.skill_registry.list_tools(),
        "tool_policy": await get_tool_policy(),
        "effective_provider": effective_provider,
    }


@app.post("/api/skills/{skill_name}/run")
async def run_skill_api(skill_name: str, body: SkillRunRequest, user: dict = Depends(require_auth)):
    """Run a specific skill on demand (safe path to expose to dashboard automation)."""
    await brain.ensure_skills_loaded()
    result = await brain.execute_skill(
        name=skill_name,
        args=body.args or {},
        session_id=body.session_id or f"skill:{skill_name}",
        channel=body.channel or "web",
        sender_id=body.sender_id or user.get("email", "admin"),
        execution_mode="manual",
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


@app.post("/api/skills/{skill_name}/enable")
async def enable_skill_api(skill_name: str, user: dict = Depends(require_auth)):
    await brain.ensure_skills_loaded()
    if not brain.skill_registry.get(skill_name):
        raise HTTPException(404, "Skill not found")
    data = await set_skill_enabled(skill_name, True, source="admin_dashboard")
    return {"skill": skill_name, **data}


@app.post("/api/skills/{skill_name}/disable")
async def disable_skill_api(skill_name: str, user: dict = Depends(require_auth)):
    await brain.ensure_skills_loaded()
    if not brain.skill_registry.get(skill_name):
        raise HTTPException(404, "Skill not found")
    data = await set_skill_enabled(skill_name, False, source="admin_dashboard")
    return {"skill": skill_name, **data}


@app.post("/api/skills/{skill_name}/exposure")
async def set_skill_exposure_api(skill_name: str, body: SkillExposureUpdateRequest, user: dict = Depends(require_auth)):
    await brain.ensure_skills_loaded()
    if not brain.skill_registry.get(skill_name):
        raise HTTPException(404, "Skill not found")
    try:
        data = await set_skill_exposure(skill_name, body.exposure, source="admin_dashboard")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"skill": skill_name, **data}


@app.get("/api/workflows")
async def list_workflows_api(user: dict = Depends(require_auth)):
    """List discovered workflow definitions."""
    workflows = workflow_loader.discover()
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


@app.post("/api/workflows/{workflow_name}/run")
async def run_workflow_api(workflow_name: str, body: WorkflowRunRequest, user: dict = Depends(require_auth)):
    """Start a workflow run so Sanaa can act on its reasoning (OpenClaw-style orchestration)."""
    await brain.ensure_skills_loaded()
    workflows = {w.name: w for w in workflow_loader.discover()}
    workflow = workflows.get(workflow_name)
    if not workflow:
        raise HTTPException(404, f"Workflow not found: {workflow_name}")

    run_id = await workflow_runtime.start(
        workflow,
        args=body.args or {},
        started_by=body.started_by or user.get("email", "admin"),
        channel=body.channel or "web",
    )
    return {"run_id": run_id, "workflow": workflow_name, "status": "started"}


@app.get("/api/workflows/runs/{run_id}")
async def workflow_run_status_api(run_id: int, user: dict = Depends(require_auth)):
    """Get workflow run status and step results."""
    state = await workflow_runtime.get_status(run_id)
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


@app.get("/api/workflows/runs")
async def workflow_runs_list_api(limit: int = 50, user: dict = Depends(require_auth)):
    """List recent workflow runs for admin/operator review."""
    from core.database import WorkflowRun, AsyncSessionLocal
    from sqlalchemy import select, desc

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


@app.get("/api/workflows/runs/{run_id}/approval")
async def workflow_run_approval_api(run_id: int, user: dict = Depends(require_auth)):
    """Return pending approval details for a paused workflow run."""
    state = await workflow_runtime.get_status(run_id)
    if not state:
        raise HTTPException(404, "Workflow run not found")
    if state.status != "paused":
        return {"status": state.status, "approval": None}

    approval_entry = None
    for item in reversed(state.output or []):
        if isinstance(item, dict) and item.get("type") == "approval_request":
            approval_entry = item
            break

    workflow = next((w for w in workflow_loader.discover() if w.name == state.workflow_name), None)
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


@app.post("/api/workflows/runs/{run_id}/resume")
async def workflow_run_resume_api(run_id: int, body: WorkflowResumeRequest, user: dict = Depends(require_auth)):
    """Resume a paused workflow run after approval decision."""
    state = await workflow_runtime.get_status(run_id)
    if not state:
        raise HTTPException(404, "Workflow run not found")
    if state.status != "paused":
        raise HTTPException(400, f"Workflow run is not paused (status={state.status})")
    if body.resume_token != (state.resume_token or ""):
        raise HTTPException(400, "Invalid resume token")

    workflow = next((w for w in workflow_loader.discover() if w.name == state.workflow_name), None)
    if not workflow:
        raise HTTPException(404, f"Workflow definition not found: {state.workflow_name}")

    ok = await workflow_runtime.resume(run_id, workflow, approved=body.approved)
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


@app.post("/api/workflows/runs/{run_id}/cancel")
async def workflow_run_cancel_api(run_id: int, user: dict = Depends(require_auth)):
    """Cancel a running or paused workflow run."""
    ok = await workflow_runtime.cancel(run_id)
    if not ok:
        raise HTTPException(404, "Workflow run not found")
    return {"status": "success", "run_id": run_id, "cancelled": True}


@app.post("/api/whatsapp/send-message")
async def wa_bridge_send_message(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Send a text message. Body: {"phone": "256...", "message": "Hello"}"""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    message = body.get("message")
    if not phone or not message:
        raise HTTPException(400, "phone and message are required")
    return await whatsapp_saas.send_message(phone, message)


@app.post("/api/whatsapp/send-media")
async def wa_bridge_send_media(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Send media. Body: {"phone": "...", "media_url": "...", "type": "image", "caption": ""}"""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    media_url = body.get("media_url") or body.get("media_link")
    media_type = body.get("type", "image")
    caption = body.get("caption", "")
    if not phone or not media_url:
        raise HTTPException(400, "phone and media_url are required")
    return await whatsapp_saas.send_media_message(phone, media_url, media_type, caption)


@app.post("/api/whatsapp/send-template")
async def wa_bridge_send_template(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Send a template. Body: {"phone": "...", "template_name": "...", "language": "en", "components": [...]}"""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    template_name = body.get("template_name")
    if not phone or not template_name:
        raise HTTPException(400, "phone and template_name are required")
    return await whatsapp_saas.send_template_message(
        phone, template_name,
        language=body.get("language", "en"),
        components=body.get("components"),
    )


@app.post("/api/whatsapp/send-interactive")
async def wa_bridge_send_interactive(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Send interactive message (buttons/lists). Body: {"phone": "...", ...interactive_data}"""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    if not phone:
        raise HTTPException(400, "phone is required")
    return await whatsapp_saas.send_interactive_message(phone, body)


@app.post("/api/whatsapp/send-carousel")
async def wa_bridge_send_carousel(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Send carousel template. Body: {"phone": "...", "template_name": "...", "components": [...]}"""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    template_name = body.get("template_name")
    if not phone or not template_name:
        raise HTTPException(400, "phone and template_name are required")
    return await whatsapp_saas.send_carousel_template(
        phone, template_name,
        language=body.get("language", "en"),
        components=body.get("components"),
    )


@app.post("/api/whatsapp/contacts")
async def wa_bridge_create_contact(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Create a contact. Body: {"phone": "...", "first_name": "", "last_name": "", "groups": ""}"""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    if not phone:
        raise HTTPException(400, "phone is required")
    return await whatsapp_saas.create_contact(
        phone,
        first_name=body.get("first_name", ""),
        last_name=body.get("last_name", ""),
        email=body.get("email", ""),
        groups=body.get("groups", ""),
    )


@app.put("/api/whatsapp/contacts/{phone}")
async def wa_bridge_update_contact(phone: str, request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Update a contact by phone number."""
    body = await request.json()
    return await whatsapp_saas.update_contact(phone, **body)


@app.get("/api/whatsapp/contacts")
async def wa_bridge_list_contacts(
    page: int = 1, per_page: int = 50,
    token: str = Depends(verify_whatsapp_api_key),
):
    """List contacts with pagination."""
    return await whatsapp_saas.get_contacts(page=page, per_page=per_page)


@app.get("/api/whatsapp/contacts/{phone}")
async def wa_bridge_get_contact(phone: str, token: str = Depends(verify_whatsapp_api_key)):
    """Get a single contact by phone number or email."""
    return await whatsapp_saas.get_contact(phone)


@app.post("/api/whatsapp/contacts/assign")
async def wa_bridge_assign_member(request: Request, token: str = Depends(verify_whatsapp_api_key)):
    """Assign a team member. Body: {"phone": "...", "user_id": 1}"""
    body = await request.json()
    phone = body.get("phone") or body.get("phone_number")
    user_id = body.get("user_id")
    if not phone or not user_id:
        raise HTTPException(400, "phone and user_id are required")
    return await whatsapp_saas.assign_team_member(phone, int(user_id))


# ==================== WHATSAPP WEBHOOK (AI BOT) ====================

@app.post("/api/whatsapp/webhook/incoming")
async def wa_webhook_incoming(request: Request, background_tasks: BackgroundTasks):
    """
    Receive forwarded webhooks from WhatsJet.
    Processes incoming messages through Sanaa AI Brain for auto-replies.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ignored", "reason": "invalid json"}

    # Extract incoming message from Meta webhook format
    entry = (payload.get("entry") or [{}])[0]
    changes = (entry.get("changes") or [{}])[0]
    value = changes.get("value", {})
    messages = value.get("messages", [])

    if not messages:
        return {"status": "ok", "reason": "no messages"}

    for msg in messages:
        phone = msg.get("from", "")
        msg_type = msg.get("type", "")
        text = ""
        if msg_type == "text":
            text = msg.get("text", {}).get("body", "")
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            text = (interactive.get("button_reply") or interactive.get("list_reply") or {}).get("title", "")

        if text and phone:
            background_tasks.add_task(_process_ai_reply, phone, text)

    return {"status": "ok", "processed": len(messages)}


async def _process_ai_reply(phone: str, text: str):
    """Background task: run incoming WhatsApp message through AI Brain and reply."""
    try:
        session_id = f"whatsapp:{phone}"
        response = await brain.think(
            prompt=text,
            complexity="auto",
            session_id=session_id,
            channel="whatsapp",
        )
        if response and whatsapp_saas.vendor_uid:
            result = await whatsapp_saas.send_message(phone, response)
            logger.info(f"AI reply sent to {phone}: {result.get('status', 'unknown')}")
        else:
            logger.warning(f"Cannot reply to {phone}: no vendor_uid configured or empty response")
    except Exception as e:
        logger.error(f"AI reply to {phone} failed: {e}")


# ==================== DEVICE API ====================

@app.post("/api/device/report")
async def receive_device_report(
    request: Request,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key),
):
    try:
        report = await request.json()
        device_id = report.get("device_id")
        device_name = report.get("device_name")

        await DeviceReport.create(
            device_id=device_id,
            device_name=device_name,
            data=report,
        )

        return {"status": "received", "device_id": device_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/devices")
async def list_devices(user: dict = Depends(require_auth)):
    devices = await DeviceReport.get_latest_all()
    return [
        {
            "device_id": d.device_id,
            "device_name": d.device_name,
            "last_report": d.created_at.isoformat() if d.created_at else None,
        }
        for d in devices
    ]


# ==================== ALERTS API ====================

@app.get("/api/alerts")
async def list_alerts(request: Request, limit: int = 50, user: dict = Depends(require_auth)):

    alerts = await Alert.get_recent(limit=limit)
    return [
        {
            "id": a.id,
            "severity": a.severity,
            "message": a.message,
            "metric": a.metric,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


# ==================== WATCHDOG API ====================

@app.get("/api/watchdog/events")
async def get_watchdog_events(request: Request, user: dict = Depends(require_auth)):
    """Get recent watchdog events for the live feed."""
    return _recent_events


@app.post("/api/watchdog/run")
async def run_watchdog_now(request: Request, user: dict = Depends(require_auth)):
    """Manually trigger a watchdog check + heal cycle."""

    events, checked_metrics = await watchdog.run_full_check()
    event_dicts = [e.to_dict() for e in events]

    # Store in recent events
    global _recent_events
    _recent_events = (event_dicts + _recent_events)[:MAX_EVENTS]

    # Auto-heal
    actions = await healer.process_events(events, checked_metrics)

    # Persist critical alerts to database
    for e in events:
        if e.severity in ("critical", "high"):
            await Alert.create(
                severity=e.severity,
                message=e.message,
                metric=e.metric,
            )

    # Return HTML for htmx or JSON
    if "hx-request" in request.headers:
        if not events:
            return HTMLResponse(
                '<div class="text-green-400 text-sm p-2">All clear — no issues detected</div>'
            )
        html_parts = []
        for e in events:
            color = {
                "critical": "text-red-400", "high": "text-orange-400",
                "warning": "text-yellow-400", "info": "text-blue-300",
            }.get(e.severity, "text-gray-400")
            badge_bg = {
                "critical": "bg-red-900/50", "high": "bg-orange-900/50",
                "warning": "bg-yellow-900/50", "info": "bg-blue-900/50",
            }.get(e.severity, "bg-gray-800")
            html_parts.append(
                f'<div class="flex items-start gap-2 p-2 rounded bg-gray-900/50 text-sm">'
                f'<span class="shrink-0 px-1.5 py-0.5 rounded text-xs {badge_bg} {color}">{e.severity}</span>'
                f'<span class="{color}">{e.message}</span>'
                f'</div>'
            )
        if actions:
            for a in actions:
                status = "text-green-400" if a.get("success") else "text-red-400"
                html_parts.append(
                    f'<div class="flex items-start gap-2 p-2 rounded bg-gray-900/50 text-sm">'
                    f'<span class="shrink-0 px-1.5 py-0.5 rounded text-xs bg-purple-900/50 text-purple-400">healed</span>'
                    f'<span class="{status}">{a["action"]}: {a.get("target", "")} — {"OK" if a.get("success") else "FAILED"}</span>'
                    f'</div>'
                )
        return HTMLResponse("\n".join(html_parts))

    return {
        "events": event_dicts,
        "actions": actions,
        "event_count": len(events),
        "critical_count": len([e for e in events if e.severity == "critical"]),
    }


@app.get("/api/watchdog/events-feed")
async def watchdog_events_htmx(request: Request, user: dict = Depends(require_auth)):
    """htmx-friendly live event feed fragment."""

    if not _recent_events:
        return HTMLResponse(
            '<div class="text-gray-500 text-sm italic p-3 text-center">No events yet — waiting for next watchdog cycle</div>'
        )

    html_parts = []
    for e in _recent_events[:15]:
        color = {
            "critical": "text-red-400", "high": "text-orange-400",
            "warning": "text-yellow-400", "info": "text-blue-300",
        }.get(e.get("severity", ""), "text-gray-400")
        badge_bg = {
            "critical": "bg-red-900/50", "high": "bg-orange-900/50",
            "warning": "bg-yellow-900/50", "info": "bg-blue-900/50",
        }.get(e.get("severity", ""), "bg-gray-800")
        ts = e.get("timestamp", "")[:19].replace("T", " ")
        html_parts.append(
            f'<div class="flex items-start gap-2 p-2 rounded bg-gray-900/50 text-sm">'
            f'<span class="shrink-0 px-1.5 py-0.5 rounded text-xs {badge_bg} {color}">{e.get("severity","")}</span>'
            f'<div class="flex-1">'
            f'<span class="{color}">{e.get("message","")}</span>'
            f'<div class="text-xs text-gray-600 mt-0.5">{ts} &middot; {e.get("category","")}</div>'
            f'</div>'
            f'</div>'
        )
    return HTMLResponse("\n".join(html_parts))
# ==================== INTELLIGENCE API ====================

@app.get("/api/intelligence/briefings")
async def list_briefings(request: Request, limit: int = 20):
    user = require_auth(request)
    briefings = await IntelligenceBriefing.get_recent(limit=limit)
    return [
        {
            "id": b.id,
            "title": b.title,
            "created_at": b.created_at.isoformat(),
            "metadata": b.metadata_ or {"article_count": 0},
            "pdf_path": b.pdf_path
        }
        for b in briefings
    ]

@app.get("/api/intelligence/latest-signal")
async def get_latest_signal(request: Request):
    """Internal API for FAB badge."""
    from core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(StrategicSignal).order_by(StrategicSignal.created_at.desc()).limit(1)
        )
        signal = result.scalars().first()
        if not signal:
            return {"status": "none"}
        return {
            "id": signal.id,
            "title": signal.title,
            "score": signal.score,
            "created_at": signal.created_at.isoformat()
        }

@app.get("/api/intelligence/briefing/{id}")
async def get_briefing(id: int, request: Request):
    user = require_auth(request)
    briefing = await IntelligenceBriefing.get(id)
    if not briefing:
        raise HTTPException(404)
    return {
        "title": briefing.title,
        "content": briefing.content,
        "created_at": briefing.created_at.isoformat(),
        "pdf_path": briefing.pdf_path
    }

@app.post("/api/intelligence/scan")
async def trigger_scan(request: Request, background_tasks: BackgroundTasks, user: dict = Depends(require_auth)):
    """Trigger an autonomous intelligence scan."""
        
    # Run scan in background to not block UI
    background_tasks.add_task(scanner.scan_all)
    
    if "hx-request" in request.headers:
        return HTMLResponse(f'<div class="text-2xl font-bold text-blue-400 animate-pulse">Scanning...</div>')
        
    return {"status": "started", "message": "Intelligence scan initiated"}


# ==================== ACTIVITIES API ====================

@app.get("/api/activities")
async def get_activities(request: Request, limit: int = 20, user: dict = Depends(require_auth)):
    """Get recent system activities for the dashboard feed.
    Merges watchdog events, alerts, and commands into a unified timeline."""
    activities = []

    # Include recent watchdog events
    for e in _recent_events[:limit]:
        severity = e.get("severity", "info")
        icon = {
            "critical": "heroicon-m-exclamation-triangle",
            "high": "heroicon-m-exclamation-circle",
            "warning": "heroicon-m-shield-exclamation",
            "info": "heroicon-m-information-circle",
        }.get(severity, "heroicon-m-information-circle")
        status = "error" if severity in ("critical", "high") else "warning" if severity == "warning" else "success"
        activities.append({
            "type": "watchdog",
            "title": e.get("category", "Watchdog Event"),
            "description": e.get("message", ""),
            "time": e.get("timestamp", ""),
            "status": status,
            "icon": icon,
        })

    # Include recent alerts from DB
    alerts = await Alert.get_recent(limit=limit)
    for a in alerts:
        status = "error" if a.severity in ("critical", "high") else "warning" if a.severity == "warning" else "info"
        activities.append({
            "type": "alert",
            "title": f"Alert: {a.metric or 'System'}",
            "description": a.message,
            "time": a.created_at.isoformat() if a.created_at else "",
            "status": status,
            "icon": "heroicon-m-bell-alert",
        })

    # Include recent commands
    commands = await Command.get_recent(limit=limit)
    for c in commands:
        activities.append({
            "type": "command",
            "title": f"Command Executed",
            "description": (c.text or "")[:100],
            "time": c.created_at.isoformat() if c.created_at else "",
            "status": "success" if c.status == "completed" else "error" if c.status == "failed" else "info",
            "icon": "heroicon-m-command-line",
        })

    # Sort by timestamp descending, take top N
    activities.sort(key=lambda x: x.get("time", ""), reverse=True)
    return activities[:limit]


# ==================== SYSTEM CONTROL API ====================

@app.get("/api/system/state")
async def get_system_state(request: Request, user: dict = Depends(require_auth)):
    """Get HTML fragment for the Visual Control Center."""
        
    current_provider = brain.get_current_provider()
    
    # Render the control center widget state
    # We construct the HTML manually here for HTMX fragment serving, 
    # but could also use a partial template if we had one.
    
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
        
    # Mock preferences for now (runtime only)
    # In a real app, fetch from DB or Settings
    prefs = {
        "security_scanner": True,
        "auto_heal": True
    }
    
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


@app.get("/api/system/tool-policy")
async def get_tool_policy_api(user: dict = Depends(require_auth)):
    """Get current AI tool allowlist/denylist policy."""
    await brain.ensure_skills_loaded()
    return {
        "policy": await get_tool_policy(),
        "skills": [s["name"] for s in await build_skill_catalog(brain.skill_registry)],
    }


@app.post("/api/system/tool-policy")
async def update_tool_policy_api(body: ToolPolicyUpdateRequest, user: dict = Depends(require_auth)):
    """Update AI tool policy (partial update)."""
    await brain.ensure_skills_loaded()
    payload = body.model_dump(exclude_none=True)
    try:
        policy = await save_tool_policy(payload, source="admin_dashboard", skill_names=set(brain.skill_registry._skills.keys()))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "success", "policy": policy}


@app.get("/api/system/session-policy")
async def get_session_policy_api(user: dict = Depends(require_auth)):
    """Get current session routing/reset/send policy."""
    return {"policy": await get_session_policy()}


@app.post("/api/system/session-policy")
async def update_session_policy_api(body: SessionPolicyUpdateRequest, user: dict = Depends(require_auth)):
    """Update session safety/reset/send policy (partial update)."""
    payload = body.model_dump(exclude_none=True)
    policy = await save_session_policy(payload, source="admin_dashboard")
    return {"status": "success", "policy": policy}


@app.get("/api/system/doctor")
async def get_system_doctor_api(user: dict = Depends(require_auth)):
    """Run doctor-style safety/config audit checks."""
    return await run_doctor(brain=brain, workflow_loader=workflow_loader)


@app.post("/api/system/doctor/run")
async def run_system_doctor_api(user: dict = Depends(require_auth)):
    """Explicit doctor run endpoint (same output as GET, useful for UI actions)."""
    return await run_doctor(brain=brain, workflow_loader=workflow_loader)


@app.get("/api/sessions")
async def list_sessions_api(limit: int = 100, user: dict = Depends(require_auth)):
    """List recent sessions with basic metadata and send overrides."""
    sessions = await list_sessions(limit=limit)
    return {"count": len(sessions), "sessions": sessions, "policy": await get_session_policy()}


@app.get("/api/sessions/{session_id}")
async def get_session_detail_api(session_id: str, user: dict = Depends(require_auth)):
    """Get recent messages and policy context for a session."""
    try:
        return await get_session_detail(session_id, limit=100)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/sessions/{session_id}/reset")
async def reset_session_api(session_id: str, user: dict = Depends(require_auth)):
    """Rotate a session route to a new session ID (best-effort, direct chats)."""
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


@app.post("/api/sessions/{session_id}/send-policy")
async def set_session_send_policy_api(session_id: str, body: SessionSendPolicyRequest, user: dict = Depends(require_auth)):
    """Set per-session send override (on|off|inherit)."""
    try:
        mode = await set_session_send_override(session_id, body.mode, source="admin_dashboard")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "success", "session_id": session_id, "mode": mode}

@app.post("/api/system/brain/provider")
async def set_provider(request: Request, user: dict = Depends(require_auth)):
    """Set the active LLM provider. Accepts both JSON and Form data."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        provider = body.get("provider", "")
    else:
        form = await request.form()
        provider = form.get("provider", "")

    provider = provider.lower()
    if provider not in BRAIN_PROVIDERS:
        raise HTTPException(400, "Invalid provider. Choose: auto, local, groq, claude, openrouter")

    brain.switch_provider(provider)
    from core.database import SystemKnowledge
    await SystemKnowledge.set_pref("brain.provider", provider, source="api")

    # HTMX: return updated control center HTML
    if "hx-request" in request.headers:
        return await get_system_state(request)

    # API: return JSON
    return {"status": "success", "provider": provider}


@app.get("/api/system/brain/config")
async def get_brain_config(user: dict = Depends(require_auth)):
    """Get editable brain configuration for admin dashboard."""
    return await _brain_config_snapshot()


@app.post("/api/system/brain/config")
async def update_brain_config(request: Request, user: dict = Depends(require_auth)):
    """Update brain provider/source/models/keys from admin dashboard."""
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Invalid request body")

    from core.database import SystemKnowledge

    provider = str(body.get("provider", "") or "").strip().lower()
    if provider:
        if provider not in BRAIN_PROVIDERS:
            raise HTTPException(400, "Invalid provider")
        brain.switch_provider(provider)
        await SystemKnowledge.set_pref("brain.provider", provider, source="admin_dashboard")

    claude_source = str(body.get("claude_source", "") or "").strip().lower()
    if claude_source:
        if claude_source not in CLAUDE_SOURCES:
            raise HTTPException(400, "Invalid claude_source")
        settings.brain_claude_source = claude_source
        await SystemKnowledge.set_pref("brain.claude_source", claude_source, source="admin_dashboard")

    auto_provider_order = body.get("auto_provider_order")
    if auto_provider_order is not None:
        if isinstance(auto_provider_order, list):
            auto_provider_order = ",".join(str(v).strip() for v in auto_provider_order if str(v).strip())
        auto_provider_order = _normalize_provider_csv(str(auto_provider_order))
        settings.brain_auto_provider_order = auto_provider_order
        await SystemKnowledge.set_pref("brain.auto_provider_order", auto_provider_order, source="admin_dashboard")

    keys = body.get("keys") or {}
    if isinstance(keys, dict):
        for raw_provider, value in keys.items():
            secret = str(value or "").strip()
            if not secret:
                continue  # blank means keep existing
            provider_key = raw_provider.lower().strip()
            if provider_key in {"claude", "anthropic"}:
                provider_key = "anthropic"
            if provider_key not in {"anthropic", "groq", "openrouter"}:
                continue
            _apply_runtime_secret(provider_key, secret)
            await SystemKnowledge.set_pref(f"brain.api_key.{provider_key}", secret, source="admin_dashboard")

    models = body.get("models") or {}
    model_pref_map = {
        "local": "brain.model.local",
        "groq": "brain.model.groq",
        "anthropic_fast": "brain.model.anthropic_fast",
        "anthropic_premium": "brain.model.anthropic_premium",
        "openrouter": "brain.model.openrouter",
    }
    if isinstance(models, dict):
        for model_key, pref_key in model_pref_map.items():
            if model_key not in models:
                continue
            model_value = str(models.get(model_key) or "").strip()
            if not model_value:
                continue
            _apply_runtime_brain_model(model_key, model_value)
            await SystemKnowledge.set_pref(pref_key, model_value, source="admin_dashboard")

    # Rebuild model chains after any runtime config mutation
    brain.registry.models = brain.registry._build_model_chain()

    return {"status": "success", "config": await _brain_config_snapshot()}


@app.post("/api/system/preference")
async def update_preference(request: Request, user: dict = Depends(require_auth)):
    """Update a system preference and persist it in system_knowledge."""
    body = await request.json()
    key = body.get("key")
    value = body.get("value")
    if not key:
        raise HTTPException(400, "Missing preference key")

    from core.database import SystemKnowledge
    await SystemKnowledge.set_pref(key, value, source="user_preference")
    return {"status": "success", "key": key, "value": value}


# ==================== SELLER PROVISIONING API ====================
# Server-to-server API for Soko to create/query linked seller accounts.
# Authenticated via SOKO_PROVISION_KEY Bearer token.

def verify_soko_provision_key(request: Request):
    """Verify Bearer token for Soko provisioning API."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = auth.split(" ", 1)[1]
    if not settings.soko_provision_key or token != settings.soko_provision_key:
        raise HTTPException(403, "Invalid provisioning key")
    return token


class SellerProvisionRequest(BaseModel):
    seller_uuid: str
    soko_user_id: Optional[int] = None
    name: str
    shop_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    whatsjet_vendor_uid: Optional[str] = None


@app.post("/api/sellers/provision")
async def provision_seller(
    payload: SellerProvisionRequest,
    token: str = Depends(verify_soko_provision_key),
):
    """Create a Sanaa Intelligence account for a Soko seller. Idempotent."""
    existing = await SellerAccount.get_by_uuid(payload.seller_uuid)
    if existing:
        return {
            "success": True,
            "already_existed": True,
            "seller_uuid": existing.seller_uuid,
            "api_key": existing.api_key,
            "dashboard_url": f"{settings.app_url}/seller/{existing.seller_uuid}",
        }

    import secrets
    api_key = "sa_" + secrets.token_urlsafe(32)

    account = await SellerAccount.create(
        seller_uuid=payload.seller_uuid,
        soko_user_id=payload.soko_user_id,
        name=payload.name,
        shop_name=payload.shop_name,
        phone=payload.phone,
        email=payload.email,
        whatsjet_vendor_uid=payload.whatsjet_vendor_uid,
        api_key=api_key,
        status="active",
    )

    await AuditLog.log(
        actor="soko_provisioning",
        action="seller_account_created",
        resource=f"seller:{payload.seller_uuid}",
        details={"soko_user_id": payload.soko_user_id, "name": payload.name},
    )

    return {
        "success": True,
        "already_existed": False,
        "seller_uuid": account.seller_uuid,
        "api_key": account.api_key,
        "dashboard_url": f"{settings.app_url}/seller/{account.seller_uuid}",
    }


@app.get("/api/sellers/{seller_uuid}")
async def get_seller(
    seller_uuid: str,
    token: str = Depends(verify_soko_provision_key),
):
    """Get a seller account by UUID."""
    account = await SellerAccount.get_by_uuid(seller_uuid)
    if not account:
        raise HTTPException(404, "Seller account not found")

    return {
        "success": True,
        "seller": {
            "seller_uuid": account.seller_uuid,
            "soko_user_id": account.soko_user_id,
            "name": account.name,
            "shop_name": account.shop_name,
            "phone": account.phone,
            "email": account.email,
            "whatsjet_vendor_uid": account.whatsjet_vendor_uid,
            "api_key": account.api_key,
            "status": account.status,
            "created_at": account.created_at.isoformat() if account.created_at else None,
        },
    }


@app.get("/api/sellers")
async def list_sellers(
    token: str = Depends(verify_soko_provision_key),
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List all seller accounts."""
    from sqlalchemy import select as sa_select
    from core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        query = sa_select(SellerAccount).order_by(SellerAccount.created_at.desc())
        if status:
            query = query.where(SellerAccount.status == status)
        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        accounts = result.scalars().all()

    return {
        "success": True,
        "count": len(accounts),
        "sellers": [
            {
                "seller_uuid": a.seller_uuid,
                "name": a.name,
                "shop_name": a.shop_name,
                "status": a.status,
                "whatsjet_vendor_uid": a.whatsjet_vendor_uid,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in accounts
        ],
    }
