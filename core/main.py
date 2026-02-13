"""
Sanaa AI — Operations Agent
Main FastAPI application
"""

import os
import secrets
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks, Form, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv("/opt/antigravity/.env")

from agents.server_health import ServerHealthAgent
from agents.app_monitor import AppMonitorAgent
from agents.email_agent import EmailInboxAgent
from agents.news_agent import NewsAgent
from agents.web_test_agent import WebTestAgent
from agents.report_agent import ReportAgent
from agents.device_agent import DeviceAgent
from agents.llm_brain import LLMBrain
from database import init_db, get_db, Log, Command, DeviceReport, Alert

security = HTTPBearer(auto_error=False)

# Session store (in-memory; survives within process lifetime)
active_sessions: dict[str, dict] = {}

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@ai.sanaa.co")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin@ai.sanaa.coPython")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown"""
    await init_db()
    print("Sanaa AI is online")
    yield
    print("Sanaa AI shutting down")

app = FastAPI(
    title="Sanaa AI",
    description="Sanaa AI Operations Agent",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ai.sanaa.co", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("/opt/antigravity/web/templates", exist_ok=True)
templates = Jinja2Templates(directory="/opt/antigravity/web/templates")

# Initialize agents
brain = LLMBrain()
server_health = ServerHealthAgent()
app_monitor = AppMonitorAgent()
email_agent = EmailInboxAgent()
news_agent = NewsAgent()
web_test = WebTestAgent()
report_agent = ReportAgent()
device_agent = DeviceAgent()


# ==================== AUTH ====================

def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing API key")
    if credentials.credentials != os.getenv("MAC_CLIENT_API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return credentials.credentials

def verify_session(request: Request):
    """Verify the user has a valid session cookie"""
    session_token = request.cookies.get("sanaa_session")
    if not session_token or session_token not in active_sessions:
        return None
    return active_sessions[session_token]


# ==================== LOGIN ====================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    if verify_session(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    """Handle login form submission"""
    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        session_token = secrets.token_hex(32)
        active_sessions[session_token] = {"email": email, "logged_in_at": datetime.now(timezone.utc).isoformat()}
        redirect = RedirectResponse(url="/", status_code=302)
        redirect.set_cookie(
            key="sanaa_session",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=86400 * 7,  # 7 days
        )
        return redirect
    else:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid email or password"})

@app.get("/logout")
async def logout(request: Request):
    """Logout and clear session"""
    session_token = request.cookies.get("sanaa_session")
    if session_token and session_token in active_sessions:
        del active_sessions[session_token]
    redirect = RedirectResponse(url="/login", status_code=302)
    redirect.delete_cookie("sanaa_session")
    return redirect


# ==================== WEB DASHBOARD ====================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard — system overview"""
    user = verify_session(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    health = await server_health.get_snapshot()
    recent_alerts = await Alert.get_recent(limit=20)
    recent_commands = await Command.get_recent(limit=10)
    devices = await DeviceReport.get_latest_all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "health": health,
        "alerts": recent_alerts,
        "commands": recent_commands,
        "devices": devices,
        "now": datetime.now(timezone.utc),
        "user": user,
    })

# ==================== COMMAND API ====================

class CommandRequest(BaseModel):
    command: str
    context: str | None = None
    approval_required: bool = True

class CommandResponse(BaseModel):
    id: str
    status: str
    analysis: str
    proposed_actions: list[str]
    requires_approval: bool
    result: str | None = None

@app.post("/api/command", response_model=CommandResponse)
async def execute_command(req: CommandRequest, request: Request, background_tasks: BackgroundTasks):
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    cmd = await Command.create(
        text=req.command,
        context=req.context,
        status="analyzing"
    )

    server_snap = await server_health.get_snapshot()
    recent_errs = await app_monitor.get_recent_errors(limit=20)

    analysis = await brain.analyze_command(
        command=req.command,
        server_context=server_snap,
        recent_logs=recent_errs,
    )

    if analysis.get("auto_execute") and not req.approval_required:
        background_tasks.add_task(brain.execute_plan, cmd.id, analysis["plan"])
        return CommandResponse(
            id=cmd.id,
            status="executing",
            analysis=analysis["summary"],
            proposed_actions=analysis["plan"],
            requires_approval=False,
        )
    else:
        await Command.update_by_id(
            cmd.id,
            status="awaiting_approval",
            proposed_plan=analysis["plan"]
        )
        return CommandResponse(
            id=cmd.id,
            status="awaiting_approval",
            analysis=analysis["summary"],
            proposed_actions=analysis["plan"],
            requires_approval=True,
        )

@app.post("/api/command/{cmd_id}/approve")
async def approve_command(cmd_id: str, request: Request, background_tasks: BackgroundTasks):
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    cmd = await Command.get(cmd_id)
    if not cmd:
        raise HTTPException(404, "Command not found")
    if cmd.status != "awaiting_approval":
        raise HTTPException(400, "Command not awaiting approval")

    background_tasks.add_task(brain.execute_plan, cmd.id, cmd.proposed_plan)
    await Command.update_by_id(cmd.id, status="executing")
    return {"status": "approved", "message": "Executing now"}


# ==================== HEALTH & MONITORING API ====================

@app.get("/api/health")
async def api_health():
    return await server_health.get_snapshot()

@app.post("/api/device/report")
async def receive_device_report(
    request: Request,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
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

        alerts = []

        return {"status": "received", "alerts_triggered": len(alerts)}
    except Exception as e:
        raise HTTPException(500, str(e))
