"""
Sanaa AI — Validated Configuration
All env vars loaded and validated through Pydantic Settings.
"""

from pydantic_settings import BaseSettings
from pydantic import AliasChoices, Field, field_validator
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

    # CORS
    # `str | list[str]` keeps pydantic_settings from JSON-decoding the env value,
    # so a comma-separated string can be split into a list by the validator below.
    cors_origins: list[str] | str = ["https://ai.sanaa.co"]

    # Database
    database_url: str = "postgresql+asyncpg://antigravity:password@localhost:5432/antigravity_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"

    # LLM — Local (Ollama / self-hosted)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # LLM — Soldier (self-hosted OpenAI-compatible endpoint, e.g. Salad.cloud)
    soldier_url: str = ""           # OpenAI-compatible base URL (includes /v1)
    soldier_model: str = ""         # Model name served by that endpoint
    soldier_api_key: str = "none"   # API key — "none" for unauthenticated endpoints

    # LLM — Cloud (optional)
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    llm_strategy: str = "auto"  # local | cloud | auto
    brain_claude_source: str = "anthropic"  # anthropic | groq | openrouter
    brain_auto_provider_order: str = "groq,soldier,anthropic,openrouter,local"
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
    root_admin_email: str = "banks@sanaa.co"
    admin_password: str = "CHANGE_THIS"
    admin_password_hash: str = ""  # auto-migrated to bcrypt on first run

    # Channels — WhatsApp
    whatsapp_enabled: bool = False
    whatsapp_sidecar_url: str = "ws://127.0.0.1:3001"
    whatsapp_allowed_numbers: str = ""  # comma-separated
    whatsapp_webhook_secret: str = ""  # fail-closed when unset

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

    # Soko 24 marketplace DB (local MySQL on ai.sanaa.co)
    soko_db_host: str = "127.0.0.1"
    soko_db_port: int = 3306
    soko_db_user: str = "soko24"
    soko_db_password: str = "SUPER_STRONG_PASSWORDX"
    soko_db_name: str = "soko"
    soko_site_url: str = "https://soko24.co"
    soko_admin_path: str = "/admin"
    soko_bridge_key: str = Field(
        default="",
        validation_alias=AliasChoices("SANAA_BRIDGE_KEY", "SOKO_BRIDGE_KEY", "soko_bridge_key"),
    )
    soko_sso_fallback_email: str = "banks@soko.ug"

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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, v):
        if isinstance(v, str):
            return [u.strip() for u in v.split(",") if u.strip()]
        return v

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Weak/default secret literals that are never acceptable in production.
_PRODUCTION_SECRET_DENYLIST = ("CHANGE-THIS", "CHANGE_THIS")
_PRODUCTION_SECRET_WEAK_LITERALS = frozenset({"password", "admin", "secret", "123456", "qwerty"})


def _is_default_secret(value: str) -> bool:
    """Return True if a secret still contains a default/placeholder pattern or a trivial literal."""
    if not value:
        return True
    lowered = value.lower()
    if lowered in _PRODUCTION_SECRET_WEAK_LITERALS:
        return True
    return any(pattern.lower() in lowered for pattern in _PRODUCTION_SECRET_DENYLIST)


def validate_production_secrets() -> None:
    """Fatal startup check: reject default/placeholder secrets in production."""
    cfg = get_settings()
    if cfg.app_env != "production":
        return

    failures: list[str] = []
    if _is_default_secret(cfg.app_secret):
        failures.append("app_secret")
    if _is_default_secret(cfg.mac_client_api_key):
        failures.append("mac_client_api_key")
    if _is_default_secret(cfg.admin_password):
        failures.append("admin_password")

    if failures:
        raise RuntimeError(
            f"Production startup blocked: the following secrets are still set to "
            f"default/placeholder values and must be changed before Sanaa AI can start: "
            f"{', '.join(failures)}"
        )


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton — call this everywhere."""
    return Settings()
