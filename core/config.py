"""
Sanaa AI — Validated Configuration
All env vars loaded and validated through Pydantic Settings.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """All configuration loaded from .env with validation and defaults."""

    # Application
    app_name: str = "Sanaa AI"
    app_url: str = "https://ai.sanaa.co"
    app_secret: str = Field(default="CHANGE-THIS-IN-PRODUCTION-64-CHARS-MINIMUM-SECRET-KEY-HERE!!!")
    app_env: str = "production"
    app_debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://antigravity:password@localhost:5432/antigravity_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"

    # LLM — Local (Ollama)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # LLM — Cloud (optional)
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    llm_strategy: str = "auto"  # local | cloud | auto

    # Email (SMTP)
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    smtp_from: str = "Sanaa AI <alert@ai.sanaa.co>"
    alert_recipients: str = ""

    # Email (IMAP)
    imap_host: Optional[str] = None
    imap_port: int = 993
    imap_user: Optional[str] = None
    imap_pass: Optional[str] = None

    # Monitoring
    monitor_urls: str = "https://cards.sanaa.ug,https://fx.sanaa.co,https://soko.sanaa.ug,https://sanaa.co,https://ai.sanaa.co"

    # Thresholds
    cpu_alert_threshold: int = 85
    ram_alert_threshold: int = 85
    disk_alert_threshold: int = 90
    load_alert_threshold: float = 4.0

    # Device API
    mac_client_api_key: str = "CHANGE_THIS"

    # Admin Auth
    admin_email: str = "admin@ai.sanaa.co"
    admin_password: str = "CHANGE_THIS"

    # Channels — WhatsApp
    whatsapp_enabled: bool = False
    whatsapp_sidecar_url: str = "ws://127.0.0.1:3001"
    whatsapp_allowed_numbers: str = ""  # comma-separated

    # Channels — Telegram
    telegram_enabled: bool = False
    telegram_bot_token: Optional[str] = None
    telegram_allowed_chats: str = ""  # comma-separated chat IDs

    # Timezone
    tz: str = "Africa/Kampala"

    @property
    def database_url_async(self) -> str:
        """Ensure the URL uses asyncpg driver."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def monitor_url_list(self) -> list[str]:
        return [u.strip() for u in self.monitor_urls.split(",") if u.strip()]

    @property
    def alert_recipient_list(self) -> list[str]:
        return [r.strip() for r in self.alert_recipients.split(",") if r.strip()]

    @property
    def whatsapp_allowed_list(self) -> list[str]:
        return [n.strip() for n in self.whatsapp_allowed_numbers.split(",") if n.strip()]

    @property
    def telegram_allowed_chat_list(self) -> list[int]:
        return [int(c.strip()) for c in self.telegram_allowed_chats.split(",") if c.strip()]

    model_config = {
        "env_file": "/opt/antigravity/.env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton — call this everywhere."""
    return Settings()
