"""
Web Channel Adapter — wraps the FastAPI/htmx dashboard chat into the
unified channel system. Unlike WhatsApp/Telegram, web messages arrive via
HTTP requests, not a persistent connection. The adapter converts request
data into InternalMessage and holds responses in memory for the HTTP
handler to return synchronously.
"""

import asyncio
import logging
from typing import Optional

from channels.base import ChannelAdapter
from router.internal_message import InternalMessage

logger = logging.getLogger(__name__)


class WebChannelAdapter(ChannelAdapter):
    """
    Web dashboard channel.

    Unlike messaging channels, web is request-response:
    - receive_message() is called from the HTTP handler with form/JSON data
    - send_response() stores the response for the HTTP handler to return
    - No persistent connection needed
    """

    channel_id = "web"

    def __init__(self):
        self._connected = True
        # Temporary storage for responses (keyed by message ID)
        self._pending_responses: dict[str, str] = {}
        self._response_events: dict[str, asyncio.Event] = {}

    async def receive_message(self, raw: dict) -> InternalMessage | None:
        """Convert web request data to InternalMessage."""
        text = raw.get("command", "").strip() or raw.get("text", "").strip()
        if not text:
            return None

        sender_email = raw.get("email", "web_user")
        session_id = raw.get("session_id")

        return InternalMessage(
            channel="web",
            sender_id=sender_email,
            sender_name=raw.get("name", sender_email),
            text=text,
            session_id=session_id,
            raw=raw,
        )

    async def send_response(self, message: InternalMessage, response: str) -> None:
        """
        Store response for the HTTP handler to pick up.
        In web context, we don't push — the handler awaits this.
        """
        msg_id = message.id
        if msg_id in self._pending_responses:
            # Append to existing (chunked responses)
            self._pending_responses[msg_id] += response
        else:
            self._pending_responses[msg_id] = response

        # Signal that response is ready
        event = self._response_events.get(msg_id)
        if event:
            event.set()

    async def get_response(self, message_id: str, timeout: float = 60.0) -> Optional[str]:
        """
        Wait for the response to a specific message.
        Called by the HTTP handler after routing.
        """
        event = asyncio.Event()
        self._response_events[message_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._pending_responses.pop(message_id, None)
        except asyncio.TimeoutError:
            logger.warning(f"Web response timeout for message {message_id}")
            return None
        finally:
            self._response_events.pop(message_id, None)

    async def connect(self) -> None:
        """Web channel is always connected (it's HTTP-based)."""
        self._connected = True
        logger.info("Web channel adapter initialized")

    async def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected
