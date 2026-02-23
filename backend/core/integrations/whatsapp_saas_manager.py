"""
WhatsApp SaaS (WhatsJet) integration manager.

Provides:
- Health checking for the nginx-hosted WhatsJet instance
- Full async API client for WhatsJet's vendor API (send messages, contacts, templates)
- Status introspection for the Sanaa AI dashboard
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Default timeout for API calls
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)


class WhatsAppSaaSManager:
    """
    Client for the WhatsJet Laravel app running behind nginx at wa.sanaa.co.
    All messaging goes through WhatsJet's vendor API which talks to Meta Cloud API.
    """

    def __init__(
        self,
        source_path: str,
        base_url: str,
        vendor_uid: str = "",
        api_token: str = "",
        **_kwargs,  # absorb legacy params (host, port, php_bin)
    ):
        self.source_path = Path(source_path)
        self.base_url = base_url.rstrip("/")
        self.vendor_uid = vendor_uid
        self.api_token = api_token
        self._api_base = f"{self.base_url}/api/{vendor_uid}"

    def is_installed(self) -> bool:
        return (self.source_path / "artisan").exists()

    # ==================== HEALTH ====================

    async def health_check(self) -> dict[str, Any]:
        """Check if WhatsJet is reachable via HTTP."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(self.base_url, follow_redirects=True)
                return {
                    "healthy": resp.status_code < 500,
                    "status_code": resp.status_code,
                    "base_url": self.base_url,
                }
        except httpx.RequestError as e:
            return {"healthy": False, "error": str(e), "base_url": self.base_url}

    async def status(self) -> dict[str, Any]:
        """Full status for dashboard display."""
        health = await self.health_check()
        return {
            "installed": self.is_installed(),
            "running": health.get("healthy", False),
            "base_url": self.base_url,
            "vendor_uid": self.vendor_uid,
            "has_api_token": bool(self.api_token),
            "source_path": str(self.source_path),
            **health,
        }

    # ==================== INTERNAL HTTP ====================

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to WhatsJet's vendor API."""
        url = f"{self._api_base}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.request(
                    method=method,
                    url=url,
                    headers=self._headers(),
                    json=json_data,
                    params=params,
                    follow_redirects=True,
                )
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text}
                return {
                    "success": resp.status_code < 400,
                    "status_code": resp.status_code,
                    "data": data,
                }
        except httpx.RequestError as e:
            logger.error(f"WhatsJet API error: {method} {url} → {e}")
            return {"success": False, "error": str(e)}

    # ==================== MESSAGING ====================

    async def send_message(
        self, phone: str, message: str, **extra
    ) -> dict[str, Any]:
        """Send a text message to a phone number."""
        payload = {"phone_number": phone, "message": message, **extra}
        return await self._request("POST", "/contact/send-message", json_data=payload)

    async def send_media_message(
        self, phone: str, media_url: str, media_type: str = "image",
        caption: str = "", **extra
    ) -> dict[str, Any]:
        """Send a media message (image, video, document, audio)."""
        payload = {
            "phone_number": phone,
            "media_link": media_url,
            "type": media_type,
            "caption": caption,
            **extra,
        }
        return await self._request("POST", "/contact/send-media-message", json_data=payload)

    async def send_template_message(
        self, phone: str, template_name: str, language: str = "en",
        components: Optional[list] = None, **extra
    ) -> dict[str, Any]:
        """Send a pre-approved WhatsApp template message."""
        payload = {
            "phone_number": phone,
            "template_name": template_name,
            "language": language,
            **extra,
        }
        if components:
            payload["components"] = components
        return await self._request("POST", "/contact/send-template-message", json_data=payload)

    async def send_interactive_message(
        self, phone: str, interactive_data: dict, **extra
    ) -> dict[str, Any]:
        """Send an interactive message (buttons, lists)."""
        payload = {"phone_number": phone, **interactive_data, **extra}
        return await self._request("POST", "/contact/send-interactive-message", json_data=payload)

    async def send_carousel_template(
        self, phone: str, template_name: str, language: str = "en",
        components: Optional[list] = None, **extra
    ) -> dict[str, Any]:
        """Send a carousel template message."""
        payload = {
            "phone_number": phone,
            "template_name": template_name,
            "language": language,
            **extra,
        }
        if components:
            payload["components"] = components
        return await self._request("POST", "/contact/send-carousel-template-message", json_data=payload)

    # ==================== CONTACTS ====================

    async def create_contact(
        self, phone: str, first_name: str = "", last_name: str = "",
        email: str = "", groups: str = "", **extra
    ) -> dict[str, Any]:
        """Create a new WhatsApp contact."""
        payload = {
            "phone_number": phone,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "groups": groups,
            **extra,
        }
        return await self._request("POST", "/contact/create", json_data=payload)

    async def update_contact(
        self, phone: str, **fields
    ) -> dict[str, Any]:
        """Update an existing contact by phone number."""
        return await self._request("POST", f"/contact/update/{phone}", json_data=fields)

    async def get_contacts(
        self, page: int = 1, per_page: int = 50
    ) -> dict[str, Any]:
        """Get paginated contact list."""
        return await self._request("GET", "/contacts", params={"page": page, "per_page": per_page})

    async def get_contact(
        self, phone_or_email: str
    ) -> dict[str, Any]:
        """Get a single contact by phone number or email."""
        return await self._request("GET", "/contact", params={"phone_number": phone_or_email})

    async def assign_team_member(
        self, phone: str, user_id: int
    ) -> dict[str, Any]:
        """Assign a team member to a contact."""
        return await self._request(
            "POST", "/contact/assign-team-member",
            json_data={"phone_number": phone, "user_id": user_id},
        )

    # ==================== ROUTE DISCOVERY ====================

    def discover_api_routes(self) -> list[dict[str, str]]:
        routes_file = self.source_path / "routes" / "api.php"
        if not routes_file.exists():
            return []
        text = routes_file.read_text(encoding="utf-8", errors="ignore")
        pattern = re.compile(
            r"Route::(get|post|put|patch|delete|any)\s*\(\s*['\"]([^'\"]+)['\"]",
            flags=re.IGNORECASE,
        )
        return [
            {"method": m.upper(), "path": p.strip()}
            for m, p in pattern.findall(text)
        ]
