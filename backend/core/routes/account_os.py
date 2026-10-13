"""
Sanaa OS — Account & Profile Management

Backend endpoints for the current authenticated user's account,
preferences, and linked devices.
"""

import os
import re
import json
import mimetypes
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.database import Account, Device, AsyncSessionLocal, utcnow
from sqlalchemy import select
from core.routes import deps
from core.routes.deps import RateLimit

logger = logging.getLogger(__name__)
router = APIRouter()

# Where user-generated OS data lives on disk
OS_DATA_DIR = Path(os.environ.get("SANAA_OS_DATA_DIR", "/data/os"))
AVATAR_DIR = OS_DATA_DIR / "users"

ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB
DEFAULT_STORAGE_QUOTA = 1073741824  # 1 GB


# ─── Pydantic models ────────────────────────────────────────────────────

class AccountUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    avatar_url: Optional[str] = Field(default=None, max_length=500)


class PreferencesPayload(BaseModel):
    preferences: dict = Field(default_factory=dict)


# ─── Helpers ────────────────────────────────────────────────────────────

def _email_slug(email: str) -> str:
    """Create a filesystem-safe slug from an email address."""
    return re.sub(r"[^a-z0-9_-]+", "_", email.lower().strip()).strip("_")[:128] or "unknown"


def _actor_email(request: Request) -> str:
    user = deps.get_current_user(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user["email"].lower().strip()


def _avatar_path(email: str, ext: str) -> Path:
    slug = _email_slug(email)
    user_dir = AVATAR_DIR / slug
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / f"avatar.{ext.lstrip('.')}"


# ─── Account endpoints ──────────────────────────────────────────────────

@router.get("/api/account/me")
async def get_account_me(request: Request, _rate: None = Depends(RateLimit(limit=120))):
    """Return the current authenticated user's account profile."""
    email = _actor_email(request)

    async with AsyncSessionLocal() as session:
        account = await Account.get_by_email(email)

        # Storage used is a rough placeholder: size of OS data dir for this user
        storage_used = 0
        try:
            user_dir = AVATAR_DIR / _email_slug(email)
            if user_dir.exists():
                storage_used = sum(f.stat().st_size for f in user_dir.rglob("*") if f.is_file())
        except Exception:
            pass

        devices_count = 0
        try:
            devices_count = len(await Device.get_by_owner(email))
        except Exception:
            pass

    if not account:
        # Return a derived profile from session if account row is missing
        user = deps.get_current_user(request)
        return {
            "email": email,
            "name": user.get("name") or email,
            "role": user.get("role") or "operator",
            "avatar_url": None,
            "storage_used": storage_used,
            "storage_quota": DEFAULT_STORAGE_QUOTA,
            "devices_count": devices_count,
            "created_at": None,
            "updated_at": None,
        }

    return {
        "email": account.email,
        "name": account.name or email,
        "role": account.role or "operator",
        "avatar_url": account.avatar_url,
        "storage_used": storage_used,
        "storage_quota": DEFAULT_STORAGE_QUOTA,
        "devices_count": devices_count,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }


@router.put("/api/account/me")
async def update_account_me(
    body: AccountUpdate,
    request: Request,
    _rate: None = Depends(RateLimit(limit=60)),
):
    """Update current user's name and/or avatar URL."""
    email = _actor_email(request)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.email == email))
        account = result.scalars().first()
        if not account:
            raise HTTPException(404, "Account not found")

        if body.name is not None:
            account.name = body.name.strip() or email
        if body.avatar_url is not None:
            account.avatar_url = body.avatar_url.strip() or None
        account.updated_at = utcnow()
        await session.commit()

    return {
        "status": "updated",
        "email": account.email,
        "name": account.name,
        "role": account.role,
        "avatar_url": account.avatar_url,
    }


@router.post("/api/account/avatar")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    _rate: None = Depends(RateLimit(limit=30)),
):
    """Upload an avatar image for the current user."""
    email = _actor_email(request)

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_AVATAR_TYPES:
        raise HTTPException(400, f"Invalid file type. Allowed: {', '.join(ALLOWED_AVATAR_TYPES)}")

    ext = mimetypes.guess_extension(content_type) or ".png"
    if ext == ".jpe":
        ext = ".jpg"

    target_path = _avatar_path(email, ext)

    # Read limited bytes to avoid memory blow-out
    contents = await file.read(MAX_AVATAR_BYTES + 1)
    if len(contents) > MAX_AVATAR_BYTES:
        raise HTTPException(413, f"Avatar must be under {MAX_AVATAR_BYTES // (1024 * 1024)} MB")

    target_path.write_bytes(contents)

    # Persist relative URL in DB
    avatar_url = f"/api/account/avatar/{_email_slug(email)}"
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.email == email))
        account = result.scalars().first()
        if account:
            account.avatar_url = avatar_url
            account.updated_at = utcnow()
            await session.commit()

    return {"status": "uploaded", "avatar_url": avatar_url}


@router.get("/api/account/avatar/{email_slug}")
async def get_avatar(email_slug: str, _rate: None = Depends(RateLimit(limit=120))):
    """Serve a user's avatar image by slug."""
    user_dir = AVATAR_DIR / email_slug
    if not user_dir.exists():
        raise HTTPException(404, "Avatar not found")

    for ext in ("png", "jpg", "jpeg", "gif", "webp"):
        candidate = user_dir / f"avatar.{ext}"
        if candidate.exists():
            return FileResponse(candidate)

    raise HTTPException(404, "Avatar not found")


@router.get("/api/account/preferences")
async def get_preferences(request: Request, _rate: None = Depends(RateLimit(limit=120))):
    """Return stored OS preferences for the current user."""
    email = _actor_email(request)

    account = await Account.get_by_email(email)
    if not account or not account.os_preferences_json:
        return {"preferences": {}}

    try:
        prefs = json.loads(account.os_preferences_json)
    except json.JSONDecodeError:
        prefs = {}

    return {"preferences": prefs}


@router.post("/api/account/preferences")
async def save_preferences(
    body: PreferencesPayload,
    request: Request,
    _rate: None = Depends(RateLimit(limit=60)),
):
    """Store OS preferences for the current user."""
    email = _actor_email(request)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.email == email))
        account = result.scalars().first()
        if not account:
            raise HTTPException(404, "Account not found")

        account.os_preferences_json = json.dumps(body.preferences, default=str)
        account.updated_at = utcnow()
        await session.commit()

    return {"status": "saved", "preferences": body.preferences}


@router.get("/api/account/devices")
async def list_account_devices(
    request: Request,
    _rate: None = Depends(RateLimit(limit=120)),
):
    """List devices owned by the current user's email."""
    email = _actor_email(request)
    devices = await Device.get_by_owner(email)

    return {
        "total": len(devices),
        "devices": [
            {
                "device_id": d.device_id,
                "display_name": d.display_name,
                "codename": d.codename,
                "worker_role": d.worker_role,
                "status": d.status,
                "device_model": d.device_model,
                "android_version": d.android_version,
                "last_heartbeat": d.last_heartbeat.isoformat() if d.last_heartbeat else None,
                "total_tasks_completed": d.total_tasks_completed,
                "is_revoked": d.is_revoked,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in devices
        ],
    }


@router.get("/api/account/sessions")
async def list_account_sessions(request: Request, _rate: None = Depends(RateLimit(limit=120))):
    """Return active session metadata for the current user.

    FastAPI/Starlette sessions are client-side signed cookies; this endpoint
    returns the current session as a stub. A future implementation may track
    server-side sessions in Redis or the database.
    """
    email = _actor_email(request)
    user = deps.get_current_user(request)

    return {
        "sessions": [
            {
                "email": email,
                "role": user.get("role") or "operator",
                "auth_method": user.get("auth_method") or "session",
                "logged_in_at": user.get("logged_in_at"),
                "current": True,
            }
        ]
    }
