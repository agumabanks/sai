"""
ChannelAdapter — abstract base class for all channel integrations.
Each channel (web, WhatsApp, Telegram) implements this interface.
"""

from abc import ABC, abstractmethod

from router.internal_message import InternalMessage


class ChannelAdapter(ABC):
    """Abstract base for all channel integrations."""

    channel_id: str  # "web", "whatsapp", "telegram"

    @abstractmethod
    async def receive_message(self, raw: dict) -> InternalMessage | None:
        """Convert raw channel input to InternalMessage. Return None to skip."""
        ...

    @abstractmethod
    async def send_response(self, message: InternalMessage, response: str) -> None:
        """Send text response back through the channel."""
        ...

    async def send_media(self, to: str, media_url: str, caption: str = "") -> None:
        """Send media (image, file, voice) through the channel. Optional."""
        raise NotImplementedError(f"{self.channel_id} does not support send_media")

    async def send_typing(self, chat_id: str, active: bool = True) -> None:
        """Show typing indicator. Optional — not all channels support this."""
        pass

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection to channel service."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean shutdown."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Check connection status."""
        ...
