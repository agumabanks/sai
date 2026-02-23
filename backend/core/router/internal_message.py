"""
InternalMessage — the normalized message format that all channels produce.
Every incoming message from web, WhatsApp, or Telegram is converted into this
before reaching the agent core.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class MediaAttachment:
    """A file/image/voice attached to a message."""
    type: str                           # image, video, audio, document, voice
    url: str                            # local path or remote URL
    mime_type: str
    filename: Optional[str] = None
    size_bytes: Optional[int] = None
    caption: Optional[str] = None


@dataclass
class InternalMessage:
    """
    Normalized message format used across all channels.

    Flow:
        ChannelAdapter.receive_message(raw) → InternalMessage
        MessageRouter.route(msg) → response text
        ChannelAdapter.send_response(msg, response)
    """
    channel: str                        # "web", "whatsapp", "telegram"
    sender_id: str                      # channel-specific user ID
    text: str                           # message text content
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    sender_name: str = ""               # display name
    media: list[MediaAttachment] = field(default_factory=list)
    is_group: bool = False
    group_id: Optional[str] = None
    reply_to: Optional[str] = None      # message ID being replied to
    session_id: Optional[str] = None    # conversation session
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    @property
    def has_media(self) -> bool:
        return len(self.media) > 0

    @property
    def chat_id(self) -> str:
        """Return group_id if group message, else sender_id."""
        return self.group_id if self.is_group else self.sender_id
