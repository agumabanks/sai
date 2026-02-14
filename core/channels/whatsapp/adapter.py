"""
WhatsApp Channel Adapter — connects to the Node.js Baileys sidecar
over a local WebSocket to send/receive WhatsApp messages.
"""

import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from channels.base import ChannelAdapter
from router.internal_message import InternalMessage, MediaAttachment

logger = logging.getLogger(__name__)


class WhatsAppAdapter(ChannelAdapter):
    """
    WhatsApp channel via Baileys sidecar.

    Architecture:
        Python (this) ←WebSocket→ Node.js sidecar ←WhatsApp Web→ WhatsApp servers

    The sidecar runs as a separate process and handles the Baileys/WhatsApp
    connection. This adapter connects to it over localhost WebSocket.
    """

    channel_id = "whatsapp"

    def __init__(
        self,
        sidecar_url: str = "ws://127.0.0.1:3001",
        allowed_numbers: Optional[list[str]] = None,
        on_message=None,
    ):
        self.sidecar_url = sidecar_url
        self.allowed_numbers: set[str] = set(allowed_numbers or [])
        self._ws = None
        self._connected = False
        self._wa_connected = False
        self._phone = None
        self._current_qr: Optional[str] = None
        self._message_callback = on_message  # async callable(InternalMessage)
        self._listen_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Connect to the Baileys sidecar WebSocket."""
        try:
            import websockets
            self._ws = await websockets.connect(
                self.sidecar_url,
                ping_interval=30,
                ping_timeout=10,
            )
            self._connected = True
            self._listen_task = asyncio.create_task(self._listen())
            logger.info(f"Connected to WhatsApp sidecar at {self.sidecar_url}")

            # Request sidecar to connect to WhatsApp
            await self._send({"type": "connect"})

        except Exception as e:
            self._connected = False
            logger.error(f"Failed to connect to WhatsApp sidecar: {e}")

    async def disconnect(self) -> None:
        """Disconnect from the sidecar."""
        self._connected = False
        self._wa_connected = False
        if self._listen_task:
            self._listen_task.cancel()
        if self._ws:
            await self._ws.close()
        logger.info("WhatsApp adapter disconnected")

    def is_connected(self) -> bool:
        return self._connected and self._wa_connected

    # ==================== RECEIVE ====================

    async def _listen(self):
        """Listen for messages from the sidecar."""
        try:
            async for raw in self._ws:
                try:
                    data = json.loads(raw)
                    await self._handle_sidecar_event(data)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from sidecar: {raw[:100]}")
                except Exception as e:
                    logger.error(f"Error handling sidecar event: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"WhatsApp listener error: {e}")
            self._connected = False
            self._wa_connected = False
            # Try to reconnect after delay
            await asyncio.sleep(5)
            if not self._connected:
                asyncio.create_task(self.connect())

    async def _handle_sidecar_event(self, data: dict):
        """Handle events from the sidecar."""
        event_type = data.get("type")

        if event_type == "message":
            msg = await self.receive_message(data.get("data", {}))
            if msg and self._message_callback:
                asyncio.create_task(self._message_callback(msg))

        elif event_type == "qr":
            self._current_qr = data.get("data")
            logger.info("WhatsApp QR code received — scan to pair")

        elif event_type == "connected":
            self._wa_connected = True
            self._phone = data.get("phone")
            self._current_qr = None
            logger.info(f"WhatsApp connected as {self._phone}")

        elif event_type == "disconnected":
            self._wa_connected = False
            reason = data.get("reason", "unknown")
            logger.warning(f"WhatsApp disconnected: {reason}")

        elif event_type == "status":
            status = data.get("data", {})
            self._wa_connected = status.get("connected", False)
            self._phone = status.get("phone")

    async def receive_message(self, raw: dict) -> InternalMessage | None:
        """Convert raw WhatsApp message to InternalMessage."""
        sender_jid = raw.get("from", "")
        sender = sender_jid.replace("@s.whatsapp.net", "").replace("@g.us", "")

        # In groups, use participant as sender
        if raw.get("isGroup") and raw.get("participant"):
            sender = raw["participant"].replace("@s.whatsapp.net", "")

        # Auth: only process from allowed numbers
        if self.allowed_numbers and sender not in self.allowed_numbers:
            logger.debug(f"Ignoring message from non-allowed number: {sender}")
            return None

        text = raw.get("text", "")

        # Parse media if present
        media = []
        if raw.get("media"):
            m = raw["media"]
            media.append(MediaAttachment(
                type=m.get("type", "document"),
                url="",  # media download handled separately
                mime_type=m.get("mime", "application/octet-stream"),
                filename=m.get("filename"),
            ))

        is_group = raw.get("isGroup", False)
        timestamp_val = raw.get("timestamp")
        if isinstance(timestamp_val, (int, float)):
            ts = datetime.fromtimestamp(timestamp_val, tz=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        return InternalMessage(
            id=raw.get("id", ""),
            channel="whatsapp",
            sender_id=sender,
            sender_name=raw.get("pushName", sender),
            text=text,
            media=media,
            is_group=is_group,
            group_id=sender_jid if is_group else None,
            timestamp=ts,
            raw=raw,
        )

    # ==================== SEND ====================

    async def send_response(self, message: InternalMessage, response: str) -> None:
        """Send text message back to WhatsApp."""
        jid = message.raw.get("from") or f"{message.sender_id}@s.whatsapp.net"
        await self._send({
            "type": "send_message",
            "to": jid,
            "text": response,
        })

    async def send_media(self, to: str, media_url: str, caption: str = "") -> None:
        """Send media file to a WhatsApp number."""
        jid = f"{to}@s.whatsapp.net" if "@" not in to else to
        media_type = self._detect_media_type(media_url)
        await self._send({
            "type": "send_media",
            "to": jid,
            "url": media_url,
            "media_type": media_type,
            "caption": caption,
        })

    async def send_typing(self, chat_id: str, active: bool = True) -> None:
        """WhatsApp typing indicator is handled by Baileys automatically."""
        pass

    async def _send(self, data: dict):
        """Send JSON to sidecar WebSocket."""
        if self._ws:
            await self._ws.send(json.dumps(data))

    # ==================== STATUS ====================

    @property
    def current_qr(self) -> Optional[str]:
        """Get current QR code for web dashboard pairing display."""
        return self._current_qr

    @property
    def phone_number(self) -> Optional[str]:
        return self._phone

    def get_status(self) -> dict:
        """Full status for API/dashboard."""
        return {
            "sidecar_connected": self._connected,
            "whatsapp_connected": self._wa_connected,
            "phone": self._phone,
            "has_qr": self._current_qr is not None,
            "allowed_numbers": list(self.allowed_numbers),
        }

    @staticmethod
    def _detect_media_type(url: str) -> str:
        """Guess Baileys media type from URL extension."""
        url_lower = url.lower()
        if any(url_lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp")):
            return "image"
        if any(url_lower.endswith(ext) for ext in (".mp4", ".avi", ".mov")):
            return "video"
        if any(url_lower.endswith(ext) for ext in (".mp3", ".ogg", ".wav", ".opus")):
            return "audio"
        return "document"
