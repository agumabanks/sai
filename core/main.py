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

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks, Form, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from typing import Optional

from config import get_settings
from database import init_db, get_db, Log, Command, DeviceReport, Alert

from agents.server_health import ServerHealthAgent
from agents.app_monitor import AppMonitorAgent
from agents.email_agent import EmailInboxAgent
from agents.news_agent import NewsAgent
from agents.web_test_agent import WebTestAgent
from agents.report_agent import ReportAgent
from agents.device_agent import DeviceAgent
from agents.llm_brain import LLMBrain

from router.message_router import MessageRouter
from router.internal_message import InternalMessage
from channels.web.adapter import WebChannelAdapter
from agents.watchdog import ServerWatchdog
from agents.healer import SelfHealer

logger = logging.getLogger(__name__)
settings = get_settings()
security = HTTPBearer(auto_error=False)

# Resolve template directory relative to this file
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "web" / "templates"
STATIC_DIR = BASE_DIR / "web" / "static"


# ==================== AGENTS & CHANNELS ====================

brain = LLMBrain()
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

# In-memory event store for dashboard live feed (bounded, last 50 events)
_recent_events: list[dict] = []
MAX_EVENTS = 50

# Optional channels (connected during lifespan)
whatsapp_adapter = None
telegram_adapter = None


# ==================== LIFESPAN ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global whatsapp_adapter, telegram_adapter

    await init_db()
    await web_channel.connect()

    # WhatsApp (optional — only if enabled in config)
    if settings.whatsapp_enabled:
        try:
            from channels.whatsapp.adapter import WhatsAppAdapter
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
            from channels.telegram.adapter import TelegramAdapter
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

    print(f"Sanaa AI is online ({settings.app_env}) — channels: {list(router.channels.keys())}")
    yield

    # Shutdown channels
    if whatsapp_adapter:
        await whatsapp_adapter.disconnect()
    if telegram_adapter:
        await telegram_adapter.disconnect()
    await web_channel.disconnect()
    print("Sanaa AI shutting down")


# ==================== APP INIT ====================

app = FastAPI(
    title=settings.app_name,
    description="Sanaa AI Operations Agent",
    version="2.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_debug else None,
    redoc_url=None,
)

# Signed session cookies — survive restarts, cryptographically secure
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


def require_user(request: Request) -> dict:
    """Dependency: require authenticated user or raise 401."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


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

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "health": health,
        "alerts": recent_alerts,
        "commands": recent_commands,
        "devices": devices,
        "channels": channels_status,
        "now": datetime.now(timezone.utc),
        "user": user,
    })


# ==================== COMMAND API (routed through channels) ====================

class CommandRequest(BaseModel):
    command: str
    context: Optional[str] = None
    approval_required: bool = True


@app.post("/api/command")
async def execute_command(request: Request, background_tasks: BackgroundTasks):
    """Handle commands from both JSON API and htmx form submissions.
    Now routes through the message router for memory + context integration."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

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

    # Build an InternalMessage and route through the channel system
    msg = await web_channel.receive_message({
        "command": command_text,
        "email": user["email"],
        "name": user["email"],
        "session_id": f"web:{user['email']}",
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
async def approve_command(cmd_id: str, request: Request, background_tasks: BackgroundTasks):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

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
async def api_status(request: Request):
    """Full system status — requires auth."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    health = await server_health.get_snapshot()
    alerts = await Alert.get_recent(limit=50)
    devices = await DeviceReport.get_latest_all()

    return {
        "server": health,
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
        "version": "2.1.0",
        "channels": list(router.channels.keys()),
    }


# ==================== CHANNEL API ====================

@app.get("/api/channels")
async def list_channels(request: Request):
    """Get status of all registered channels."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    status = router.get_channel_status()

    # Add extra detail for WhatsApp
    if whatsapp_adapter:
        status["whatsapp"]["detail"] = whatsapp_adapter.get_status()

    # Add extra detail for Telegram
    if telegram_adapter:
        status["telegram"]["detail"] = telegram_adapter.get_status()

    return status


@app.post("/api/channels/whatsapp/pair")
async def whatsapp_pair(request: Request):
    """Initiate WhatsApp QR pairing."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

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
async def whatsapp_qr(request: Request):
    """Get current WhatsApp QR code for dashboard display."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not whatsapp_adapter:
        raise HTTPException(400, "WhatsApp channel not enabled")

    return {
        "qr": whatsapp_adapter.current_qr,
        "connected": whatsapp_adapter.is_connected(),
        "phone": whatsapp_adapter.phone_number,
    }


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
async def list_devices(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

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
async def list_alerts(request: Request, limit: int = 50):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

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
async def get_watchdog_events(request: Request):
    """Get recent watchdog events for the live feed."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _recent_events


@app.post("/api/watchdog/run")
async def run_watchdog_now(request: Request):
    """Manually trigger a watchdog check + heal cycle."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    events = await watchdog.run_full_check()
    event_dicts = [e.to_dict() for e in events]

    # Store in recent events
    global _recent_events
    _recent_events = (event_dicts + _recent_events)[:MAX_EVENTS]

    # Auto-heal
    actions = await healer.process_events(events)

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
async def watchdog_events_htmx(request: Request):
    """htmx-friendly live event feed fragment."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

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
