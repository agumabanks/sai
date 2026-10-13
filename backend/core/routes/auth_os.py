"""
Sanaa OS — Production Auth System
OTP-based email login, session management, and secure logout.
"""

import base64
import hashlib
import hmac
import json
import random
import logging
import smtplib
import asyncio
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.config import get_settings
from core.database import Account
from core.routes import deps

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

# Redis key prefix for OTP storage
OTP_PREFIX = "sanaa:otp:"
OTP_TTL_SECONDS = 600  # 10 minutes
SESSION_MAX_AGE = 86400 * 7  # 7 days

# Authorized emails (admin + extras from env)
AUTHORIZED_EMAILS = {settings.admin_email.lower(), settings.root_admin_email.lower()}
if hasattr(settings, "authorized_emails") and settings.authorized_emails:
    AUTHORIZED_EMAILS.update(e.strip().lower() for e in settings.authorized_emails.split(",") if e.strip())


class OTPSendRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)


class OTPVerifyRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    otp: str = Field(..., min_length=6, max_length=6)


def _get_redis():
    """Get Redis connection from existing config."""
    import redis
    try:
        r = redis.from_url(settings.redis_url or "redis://localhost:6379/0", decode_responses=True)
        r.ping()
        return r
    except Exception as e:
        logger.warning(f"Redis unavailable for OTP: {e}")
        return None


def _generate_otp() -> str:
    return f"{random.randint(100000, 999999)}"


def _send_otp_email(to_email: str, otp: str) -> bool:
    """Send OTP via SMTP using existing Sanaa config."""
    try:
        msg = MIMEText(
            f"""Your Sanaa OS Login Code

Code: {otp}
Valid for 10 minutes.

If you didn't request this, ignore this email.

— Sanaa AI Security
"""
        )
        msg["Subject"] = "Sanaa OS Login OTP"
        msg["From"] = settings.smtp_from
        msg["To"] = to_email

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_pass)
            server.send_message(msg)

        logger.info(f"OTP email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email: {e}")
        return False


@router.post("/api/auth/otp/send")
async def send_otp(body: OTPSendRequest, request: Request):
    """Send OTP to authorized email address."""
    email = body.email.strip().lower()

    # Strict: only allow configured admin/authorized emails
    if email not in AUTHORIZED_EMAILS:
        logger.warning(f"OTP request for unauthorized email: {email}")
        # Return same message to prevent enumeration
        return {"status": "queued", "message": "If your email is authorized, you will receive an OTP shortly."}

    # Rate limit: max 3 OTP requests per 10 min per email
    redis = _get_redis()
    if redis:
        rate_key = f"sanaa:otp_rate:{email}"
        count = redis.get(rate_key)
        if count and int(count) >= 3:
            raise HTTPException(429, "Too many OTP requests. Try again in 10 minutes.")
        pipe = redis.pipeline()
        pipe.incr(rate_key)
        pipe.expire(rate_key, 600)
        pipe.execute()

    otp = _generate_otp()

    # Store OTP in Redis with TTL
    if redis:
        redis.setex(f"{OTP_PREFIX}{email}", OTP_TTL_SECONDS, otp)
    else:
        # Fallback: in-memory store (not for production multi-worker)
        import time
        _memory_otps = getattr(send_otp, "_memory_otps", {})
        _memory_otps[email] = {"otp": otp, "expires": time.time() + OTP_TTL_SECONDS}
        send_otp._memory_otps = _memory_otps

    # Send email in background
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, _send_otp_email, email, otp)

    if not success:
        raise HTTPException(500, "Failed to send OTP email. Check SMTP configuration.")

    return {"status": "sent", "message": "OTP sent to your email.", "email_masked": email[:2] + "***@" + email.split("@")[-1]}


@router.post("/api/auth/otp/verify")
async def verify_otp(body: OTPVerifyRequest, request: Request):
    """Verify OTP and create session."""
    email = body.email.strip().lower()
    otp_input = body.otp.strip()

    if email not in AUTHORIZED_EMAILS:
        raise HTTPException(401, "Unauthorized email address")

    # Retrieve OTP
    redis = _get_redis()
    stored_otp = None
    if redis:
        stored_otp = redis.get(f"{OTP_PREFIX}{email}")
    else:
        _memory_otps = getattr(send_otp, "_memory_otps", {})
        entry = _memory_otps.get(email)
        if entry:
            import time
            if time.time() < entry["expires"]:
                stored_otp = entry["otp"]

    if not stored_otp or stored_otp != otp_input:
        raise HTTPException(401, "Invalid or expired OTP")

    # Clear OTP after use
    if redis:
        redis.delete(f"{OTP_PREFIX}{email}")
    else:
        _memory_otps = getattr(send_otp, "_memory_otps", {})
        _memory_otps.pop(email, None)

    # Create session
    request.session["email"] = email
    request.session["role"] = "admin"
    request.session["name"] = email
    request.session["logged_in_at"] = datetime.now(timezone.utc).isoformat()
    request.session["auth_method"] = "otp"

    # Upsert account record for device/app linking and profile storage
    try:
        await Account.upsert_from_session(email, name=email, role="admin")
    except Exception as e:
        logger.warning(f"Failed to upsert account for {email}: {e}")

    logger.info(f"User {email} authenticated via OTP from {request.client.host if request.client else 'unknown'}")

    return {"status": "authenticated", "email": email, "role": "admin", "session_created": True}


@router.get("/api/auth/me")
async def get_me(request: Request):
    """Get current authenticated user."""
    user = deps.get_current_user(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return {
        "authenticated": True,
        "email": user["email"],
        "role": user.get("role", "admin"),
        "logged_in_at": user.get("logged_in_at"),
    }


@router.post("/api/auth/logout")
async def logout(request: Request):
    """Clear session."""
    request.session.clear()
    return {"status": "logged_out"}


@router.get("/api/auth/check")
async def auth_check(request: Request):
    """Lightweight auth check for frontend polling."""
    user = deps.get_current_user(request)
    if user:
        return {
            "authenticated": True,
            "email": user["email"],
            "role": user.get("role", "admin"),
            "name": user.get("name", user["email"]),
        }
    return {"authenticated": False}


class FilamentBridgeTokenRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=4096)


def _bridge_signing_key() -> str:
    return getattr(settings, "os_bridge_key", None) or settings.mac_client_api_key or settings.app_secret


@router.post("/api/auth/establish-token")
async def establish_token(body: FilamentBridgeTokenRequest, request: Request):
    """Exchange a short-lived Laravel-signed token for a FastAPI session cookie."""
    try:
        payload_b64, signature = body.token.rsplit(".", 1)
    except ValueError:
        raise HTTPException(400, "Malformed bridge token")

    key = _bridge_signing_key().encode("utf-8")
    expected = hmac.new(key, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(403, "Invalid bridge token signature")

    try:
        data = json.loads(base64.b64decode(payload_b64.encode("utf-8")).decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Invalid bridge token payload")

    if int(data.get("exp", 0)) < int(time.time()):
        raise HTTPException(403, "Bridge token expired")

    email = str(data.get("email", "")).strip().lower()
    if not email:
        raise HTTPException(400, "Bridge token missing email")

    role = str(data.get("role", "operator")).lower()
    if role not in {"admin", "operator", "viewer", "seller"}:
        role = "operator"

    request.session["email"] = email
    request.session["role"] = role
    request.session["name"] = str(data.get("name") or email).strip()
    request.session["logged_in_at"] = datetime.now(timezone.utc).isoformat()
    request.session["auth_method"] = "filament_bridge"

    # Upsert account record for device/app linking and profile storage
    try:
        await Account.upsert_from_session(email, name=request.session["name"], role=role)
    except Exception as e:
        logger.warning(f"Failed to upsert account for {email}: {e}")

    logger.info("Bridge session established for %s (%s)", email, role)
    return {
        "authenticated": True,
        "email": email,
        "role": role,
        "name": request.session["name"],
    }
