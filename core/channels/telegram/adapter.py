"""
Telegram Channel Adapter — uses httpx to interact with the Telegram Bot API.
No external library needed — the Bot API is a simple HTTP JSON API.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from channels.base import ChannelAdapter
from router.internal_message import InternalMessage, MediaAttachment

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


class TelegramAdapter(ChannelAdapter):
    """
    Telegram bot channel using long-polling.

    Uses raw HTTP calls to the Bot API via httpx — no python-telegram-bot
    dependency needed. Keeps things lightweight.
    """

    channel_id = "telegram"

    def __init__(
        self,
        bot_token: str,
        allowed_chat_ids: Optional[list[int]] = None,
        on_message=None,
    ):
        self.bot_token = bot_token
        self.base_url = f"{TELEGRAM_API}/bot{bot_token}"
        self.allowed_chat_ids: set[int] = set(allowed_chat_ids or [])
        self._connected = False
        self._bot_info: dict = {}
        self._message_callback = on_message
        self._poll_task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._offset = 0

    async def connect(self) -> None:
        """Verify bot token and start long-polling."""
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

        try:
            resp = await self._client.get(f"{self.base_url}/getMe")
            data = resp.json()
            if not data.get("ok"):
                raise ValueError(f"Telegram getMe failed: {data}")

            self._bot_info = data["result"]
            self._connected = True
            logger.info(
                f"Telegram bot connected: @{self._bot_info.get('username')} "
                f"(ID: {self._bot_info.get('id')})"
            )

            # Start long-polling
            self._poll_task = asyncio.create_task(self._poll_updates())

        except Exception as e:
            self._connected = False
            logger.error(f"Telegram connection failed: {e}")

    async def disconnect(self) -> None:
        self._connected = False
        if self._poll_task:
            self._poll_task.cancel()
        if self._client:
            await self._client.aclose()
        logger.info("Telegram adapter disconnected")

    def is_connected(self) -> bool:
        return self._connected

    # ==================== POLLING ====================

    async def _poll_updates(self):
        """Long-poll for updates from Telegram."""
        while self._connected:
            try:
                resp = await self._client.get(
                    f"{self.base_url}/getUpdates",
                    params={
                        "offset": self._offset,
                        "timeout": 30,
                        "allowed_updates": '["message"]',
                    },
                )
                data = resp.json()

                if not data.get("ok"):
                    logger.warning(f"Telegram getUpdates error: {data}")
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    self._offset = update["update_id"] + 1

                    if "message" in update:
                        msg = await self.receive_message(update["message"])
                        if msg and self._message_callback:
                            asyncio.create_task(self._message_callback(msg))

            except asyncio.CancelledError:
                break
            except httpx.ReadTimeout:
                continue  # normal for long-polling
            except Exception as e:
                logger.error(f"Telegram polling error: {e}")
                await asyncio.sleep(5)

    # ==================== RECEIVE ====================

    async def receive_message(self, raw: dict) -> InternalMessage | None:
        """Convert raw Telegram message to InternalMessage."""
        chat = raw.get("chat", {})
        chat_id = chat.get("id")
        sender = raw.get("from", {})

        # Auth: only process from allowed chat IDs
        if self.allowed_chat_ids and chat_id not in self.allowed_chat_ids:
            logger.debug(f"Ignoring message from non-allowed chat: {chat_id}")
            return None

        text = raw.get("text", "")
        caption = raw.get("caption", "")

        # Parse media
        media = []
        if raw.get("photo"):
            # Telegram sends multiple sizes — take the largest
            largest = max(raw["photo"], key=lambda p: p.get("file_size", 0))
            media.append(MediaAttachment(
                type="image",
                url=await self._get_file_url(largest["file_id"]),
                mime_type="image/jpeg",
            ))
        if raw.get("document"):
            doc = raw["document"]
            media.append(MediaAttachment(
                type="document",
                url=await self._get_file_url(doc["file_id"]),
                mime_type=doc.get("mime_type", "application/octet-stream"),
                filename=doc.get("file_name"),
                size_bytes=doc.get("file_size"),
            ))
        if raw.get("voice"):
            voice = raw["voice"]
            media.append(MediaAttachment(
                type="voice",
                url=await self._get_file_url(voice["file_id"]),
                mime_type=voice.get("mime_type", "audio/ogg"),
            ))

        # Use caption as text for media messages
        if not text and caption:
            text = caption

        # Skip empty messages
        if not text and not media:
            return None

        is_group = chat.get("type") in ("group", "supergroup")
        ts = raw.get("date")
        timestamp = (
            datetime.fromtimestamp(ts, tz=timezone.utc) if ts
            else datetime.now(timezone.utc)
        )

        # Handle reply_to
        reply_to = None
        if raw.get("reply_to_message"):
            reply_to = str(raw["reply_to_message"].get("message_id", ""))

        return InternalMessage(
            id=str(raw.get("message_id", "")),
            channel="telegram",
            sender_id=str(sender.get("id", chat_id)),
            sender_name=self._format_name(sender),
            text=text,
            media=media,
            is_group=is_group,
            group_id=str(chat_id) if is_group else None,
            reply_to=reply_to,
            timestamp=timestamp,
            raw=raw,
        )

    # ==================== SEND ====================

    async def send_response(self, message: InternalMessage, response: str) -> None:
        """Send text message back to Telegram chat."""
        chat_id = message.raw.get("chat", {}).get("id") or message.chat_id

        # Telegram max message length is 4096
        if len(response) <= 4096:
            await self._api_call("sendMessage", {
                "chat_id": chat_id,
                "text": response,
                "parse_mode": "Markdown",
                "reply_to_message_id": message.raw.get("message_id"),
            })
        else:
            # Split long messages
            chunks = self._split_text(response, 4096)
            for i, chunk in enumerate(chunks):
                params = {"chat_id": chat_id, "text": chunk}
                if i == 0:
                    params["reply_to_message_id"] = message.raw.get("message_id")
                await self._api_call("sendMessage", params)

    async def send_media(self, to: str, media_url: str, caption: str = "") -> None:
        """Send a document/photo to a Telegram chat."""
        await self._api_call("sendDocument", {
            "chat_id": to,
            "document": media_url,
            "caption": caption,
        })

    async def send_typing(self, chat_id: str, active: bool = True) -> None:
        """Show typing indicator."""
        if active:
            await self._api_call("sendChatAction", {
                "chat_id": chat_id,
                "action": "typing",
            })

    # ==================== HELPERS ====================

    async def _api_call(self, method: str, params: dict) -> dict:
        """Make a Telegram Bot API call."""
        try:
            resp = await self._client.post(
                f"{self.base_url}/{method}",
                json=params,
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning(f"Telegram API {method} failed: {data}")
            return data
        except Exception as e:
            logger.error(f"Telegram API call {method} error: {e}")
            return {"ok": False, "error": str(e)}

    async def _get_file_url(self, file_id: str) -> str:
        """Get download URL for a Telegram file."""
        data = await self._api_call("getFile", {"file_id": file_id})
        if data.get("ok"):
            file_path = data["result"]["file_path"]
            return f"{TELEGRAM_API}/file/bot{self.bot_token}/{file_path}"
        return ""

    @staticmethod
    def _format_name(user: dict) -> str:
        """Format Telegram user name."""
        first = user.get("first_name", "")
        last = user.get("last_name", "")
        return f"{first} {last}".strip() or user.get("username", "Unknown")

    @staticmethod
    def _split_text(text: str, max_len: int) -> list[str]:
        """Split text at paragraph boundaries."""
        chunks = []
        while len(text) > max_len:
            split_at = text.rfind("\n\n", 0, max_len)
            if split_at == -1:
                split_at = text.rfind("\n", 0, max_len)
            if split_at == -1:
                split_at = max_len
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()
        if text:
            chunks.append(text)
        return chunks

    def get_status(self) -> dict:
        """Full status for API/dashboard."""
        return {
            "connected": self._connected,
            "bot_username": self._bot_info.get("username"),
            "bot_id": self._bot_info.get("id"),
            "allowed_chats": list(self.allowed_chat_ids),
        }
