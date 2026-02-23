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
    groq_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    llm_strategy: str = "auto"  # local | cloud | auto
    brain_claude_source: str = "anthropic"  # anthropic | groq | openrouter
    brain_auto_provider_order: str = "groq,anthropic,openrouter,local"
    anthropic_model_fast: str = "claude-3-haiku-20240307"
    anthropic_model_premium: str = "claude-3-5-sonnet-20240620"
    groq_model: str = "llama-3.3-70b-versatile"
    openrouter_model: str = "liquid/lfm-40b"
    sanaa_clade_enabled: bool = True
    sanaa_clade_path: str = "/var/www/ai.sanaa.co/sanaa-clade"
    sanaa_clade_timeout: int = 180
    sanaa_clade_no_admin_sync: bool = False

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
    monitor_urls: str = "https://cards.sanaa.ug,https://fx.sanaa.co,https://soko.sanaa.ug,https://sanaa.co,https://ai.sanaa.co,https://wa.sanaa.co"

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

    # Integrations — WhatsApp SaaS (WhatsJet at wa.sanaa.co)
    whatsapp_saas_enabled: bool = True
    whatsapp_saas_source_path: str = "/var/www/ai.sanaa.co/integrations/whatsapp-saas/Source"
    whatsapp_saas_base_url: str = "https://wa.sanaa.co"
    whatsapp_saas_vendor_uid: str = ""  # WhatsJet vendor UID (set after first login)
    whatsapp_saas_api_token: str = ""  # WhatsJet vendor API token
    whatsapp_saas_auto_start: bool = False  # legacy — WhatsJet now runs via nginx/PHP-FPM

    # External WhatsApp API key (for Soko, FX, Cards to call our bridge)
    whatsapp_api_key: str = ""

    # Soko provisioning key (shared secret for Soko ↔ Sanaa ↔ WhatsJet)
    soko_provision_key: str = ""

    # Watchdog Alerting
    watchdog_cooldown_tiers: str = "0,1800,7200,21600,86400"  # seconds: immediate, 30min, 2hr, 6hr, 24hr
    watchdog_stale_threshold: int = 600  # 10 min without seeing alert = resolved
    watchdog_resolution_notify: bool = True  # send "issue cleared" emails

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

    @property
    def watchdog_cooldown_tier_list(self) -> list[int]:
        return [int(t.strip()) for t in self.watchdog_cooldown_tiers.split(",") if t.strip()]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton — call this everywhere."""
    return Settings()
