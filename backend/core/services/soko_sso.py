"""Sanaa OS ↔ Soko 24 signed SSO token helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any
from urllib.parse import quote

from core.config import get_settings


def _signing_key() -> str:
    s = get_settings()
    return (s.soko_bridge_key or s.soko_provision_key or "").strip()


def build_sso_token(email: str, surface: str = "admin", ttl: int = 120) -> str | None:
    key = _signing_key()
    if not key:
        return None
    payload = {
        "email": (email or "").strip().lower(),
        "surface": surface,
        "exp": int(time.time()) + max(30, min(ttl, 300)),
        "nonce": secrets.token_hex(8),
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(key.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def sso_urls(email: str, surface: str = "admin", seller_id: int | None = None) -> dict[str, Any]:
    s = get_settings()
    site = s.soko_site_url.rstrip("/")
    token = build_sso_token(email, surface=surface)
    if not token:
        return {"available": False, "reason": "bridge_key_not_configured"}

    redirects = {
        "admin": f"{s.soko_admin_path.rstrip('/')}",
        "seller": "/seller/os",
        "store": "/",
    }
    redirect = redirects.get(surface, s.soko_admin_path)
    if surface == "seller" and seller_id:
        redirect = f"{s.soko_admin_path.rstrip('/')}/sellers/login/{seller_id}"

    auth_path = f"/sanaa-os/auth?token={quote(token)}&redirect={quote(redirect)}"
    return {
        "available": True,
        "surface": surface,
        "embed_url": f"{site}{auth_path}",
        "proxy_embed_url": f"/soko-platform{auth_path}",
        "open_url": f"{site}{auth_path}",
        "expires_in": 120,
    }