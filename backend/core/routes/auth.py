"""
Sanaa AI — Auth routes: login, logout, dashboard.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

GRAPH_BRIDGE_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Sanaa Brain Graph</title>
<style>body{background:#0b0c15;color:#94a3b8;font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}</style>
</head><body><div>Connecting your session…</div><script>
(async()=>{
  try{
    const b=await fetch('/auth/os-bridge',{method:'POST',credentials:'include',headers:{Accept:'application/json','Content-Type':'application/json'}});
    if(!b.ok){location.href='/';return;}
    const d=await b.json();
    if(!d.token){location.href='/';return;}
    const s=await fetch('/api/auth/establish-token',{method:'POST',credentials:'include',headers:{Accept:'application/json','Content-Type':'application/json'},body:JSON.stringify({token:d.token})});
    if(!s.ok){location.href='/';return;}
    location.reload();
  }catch(e){location.href='/';}
})();
</script></body></html>"""
from fastapi.templating import Jinja2Templates
from pathlib import Path

from core.config import get_settings
from core.utils.password import verify_password, is_bcrypt_hash
from core.routes import deps
from core.routes.deps import get_current_user, require_auth

from core.database import Command, Alert, DeviceReport, IntelligenceBriefing

settings = get_settings()

router = APIRouter()

# Resolve template directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = BASE_DIR / "web" / "templates"
if TEMPLATE_DIR.exists():
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
else:
    templates = Jinja2Templates(directory="/opt/antigravity/web/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    # Rate limit: 5 attempts per minute per IP
    client_ip = request.client.host if request.client else "unknown"
    if not await deps.rate_limiter.check(f"login:{client_ip}", limit=5):
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Too many login attempts. Try again in 60 seconds."},
            status_code=429,
        )

    if email != settings.admin_email:
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Invalid email or password"},
            status_code=401,
        )

    password_valid = False
    if settings.admin_password_hash and is_bcrypt_hash(settings.admin_password_hash):
        password_valid = verify_password(password, settings.admin_password_hash)
    else:
        password_valid = (password == settings.admin_password)

    if password_valid:
        request.session["email"] = email
        request.session["logged_in_at"] = datetime.now(timezone.utc).isoformat()
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        request, "login.html",
        {"error": "Invalid email or password"},
        status_code=401,
    )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    health = await deps.server_health.get_snapshot()
    recent_alerts = await Alert.get_recent(limit=20)
    recent_commands = await Command.get_recent(limit=10)
    devices = await DeviceReport.get_latest_all()
    channels_status = deps.router_instance.get_channel_status()
    briefings = await IntelligenceBriefing.get_recent(limit=5)

    return templates.TemplateResponse(
        request, "dashboard.html", {
            "health": health,
            "alerts": recent_alerts,
            "commands": recent_commands,
            "devices": devices,
            "channels": channels_status,
            "briefings": briefings,
            "now": datetime.now(timezone.utc),
            "user": user,
        }
    )


@router.get("/api/brain/graph/ui", response_class=HTMLResponse)
async def brain_graph_page(request: Request):
    # Accept both session auth and Bearer token
    user = get_current_user(request)
    if not user:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth.split(" ")[1] == settings.mac_client_api_key:
            user = {"email": "api", "is_bridge": True}
    if not user:
        return HTMLResponse(content=GRAPH_BRIDGE_HTML, status_code=200)
    return templates.TemplateResponse(request, "graph.html", {"user": user})
