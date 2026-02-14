"""
Message Router — central dispatch between channels and the agent core.

Flow:
    Channel receives raw input → ChannelAdapter.receive_message() → InternalMessage
    → MessageRouter.route() → LLMBrain.think() → response text
    → ChannelAdapter.send_response() → user sees reply
"""

import logging
import time
import hashlib
from typing import Optional

from router.internal_message import InternalMessage
from channels.base import ChannelAdapter
from database import AuditLog, Conversation

logger = logging.getLogger(__name__)


class MessageRouter:
    """Routes normalized messages to the agent core and back to channels."""

    def __init__(self, brain, channels: Optional[dict[str, ChannelAdapter]] = None):
        self.brain = brain
        self.channels: dict[str, ChannelAdapter] = channels or {}
        # Per-channel auth: set of allowed sender IDs. Empty set = allow all.
        self._allowed_senders: dict[str, set[str]] = {}

    def register_channel(self, channel: ChannelAdapter):
        """Register a channel adapter."""
        self.channels[channel.channel_id] = channel
        logger.info(f"Channel registered: {channel.channel_id}")

    def set_allowed_senders(self, channel_id: str, sender_ids: set[str]):
        """Set which sender IDs are allowed for a channel. Empty = allow all."""
        self._allowed_senders[channel_id] = sender_ids

    def _is_authorized(self, message: InternalMessage) -> bool:
        """Check if sender is allowed for this channel."""
        allowed = self._allowed_senders.get(message.channel)
        if not allowed:
            return True  # no restrictions configured
        return message.sender_id in allowed

    # ==================== ROUTING ====================

    async def route(self, message: InternalMessage) -> str:
        """
        Process an incoming message end-to-end:
        1. Auth check
        2. Generate session ID
        3. Save user turn
        4. Send to LLM brain
        5. Save assistant turn
        6. Send response back through channel
        7. Audit log
        """
        start = time.monotonic()

        # Auth check
        if not self._is_authorized(message):
            logger.warning(
                f"Unauthorized message from {message.sender_id} on {message.channel}"
            )
            return ""

        # Ensure session ID
        if not message.session_id:
            message.session_id = self._derive_session_id(message)

        # Save user turn
        from memory.context import ContextAssembler
        ctx = self.brain.context_assembler
        await ctx.save_turn(
            session_id=message.session_id,
            channel=message.channel,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            role="user",
            content=message.text,
        )

        # Get response from brain
        response = await self.brain.think(
            prompt=message.text,
            complexity="auto",
            session_id=message.session_id,
            channel=message.channel,
        )

        latency_ms = int((time.monotonic() - start) * 1000)

        # Send response back through the originating channel
        channel = self.channels.get(message.channel)
        if channel and channel.is_connected():
            await self._send_chunked(channel, message, response)

        # Audit
        await AuditLog.log(
            actor=f"{message.channel}:{message.sender_id}",
            action="message.routed",
            resource=message.text[:200],
            detail=f"latency={latency_ms}ms session={message.session_id}",
            success=True,
        )

        logger.info(
            f"Routed [{message.channel}] {message.sender_id}: "
            f"{message.text[:60]}... → {len(response)} chars ({latency_ms}ms)"
        )
        return response

    async def route_and_respond(self, message: InternalMessage) -> str:
        """Alias for route() — processes message and sends response back."""
        return await self.route(message)

    # ==================== HELPERS ====================

    def _derive_session_id(self, message: InternalMessage) -> str:
        """
        Generate a deterministic session ID from channel + sender.
        Same user on same channel always gets the same session.
        """
        raw = f"{message.channel}:{message.chat_id}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    async def _send_chunked(
        self, channel: ChannelAdapter, message: InternalMessage, response: str
    ):
        """Split long responses into channel-appropriate chunks."""
        max_length = {
            "whatsapp": 4000,
            "telegram": 4000,
            "web": 100_000,
        }.get(message.channel, 4000)

        if len(response) <= max_length:
            await channel.send_response(message, response)
        else:
            chunks = self._split_at_boundaries(response, max_length)
            for chunk in chunks:
                await channel.send_response(message, chunk)

    @staticmethod
    def _split_at_boundaries(text: str, max_length: int) -> list[str]:
        """Split text at paragraph/sentence boundaries to avoid mid-word cuts."""
        chunks = []
        while len(text) > max_length:
            # Try to split at double newline (paragraph)
            split_at = text.rfind("\n\n", 0, max_length)
            if split_at == -1:
                # Try single newline
                split_at = text.rfind("\n", 0, max_length)
            if split_at == -1:
                # Try period + space (sentence)
                split_at = text.rfind(". ", 0, max_length)
                if split_at != -1:
                    split_at += 1  # include the period
            if split_at == -1:
                # Hard cut at space
                split_at = text.rfind(" ", 0, max_length)
            if split_at == -1:
                split_at = max_length

            chunks.append(text[:split_at].rstrip())
            text = text[split_at:].lstrip()

        if text:
            chunks.append(text)
        return chunks

    # ==================== STATUS ====================

    def get_channel_status(self) -> dict:
        """Return connectivity status for all registered channels."""
        return {
            cid: {
                "connected": ch.is_connected(),
                "channel_id": ch.channel_id,
            }
            for cid, ch in self.channels.items()
        }
