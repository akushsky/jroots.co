from functools import lru_cache
from typing import Any, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings

# Per-provider defaults for model ids and USD prices. Applied only when the
# corresponding field was not set explicitly via env (see apply_provider_profile).
_PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    "moonshot": {
        "llm_model_main": "kimi-k2.6",
        "llm_model_escalation": "kimi-k3",
        "llm_price_in_per_1m": 0.95,
        "llm_price_out_per_1m": 4.0,
    },
    "gemini": {
        "llm_model_main": "gemini-3.1-pro-preview",
        "llm_model_escalation": "gemini-3.1-pro-preview",
        "llm_price_in_per_1m": 2.0,
        "llm_price_out_per_1m": 12.0,
    },
}


class Settings(BaseSettings):
    secret_key: str
    algorithm: str = "HS256"
    admin_password: str
    database_url: str
    cors_origins: str = "http://localhost:5173"
    frontend_url: str = "http://localhost:5173"
    # Invite-only beta: set REGISTRATION_ENABLED=false to reject POST /api/register.
    registration_enabled: bool = True
    # Optional seed on startup (entrypoint): create/promote a verified admin.
    bootstrap_admin_email: str = ""
    bootstrap_admin_username: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    hcaptcha_secret_key: str = ""
    resend_api_key: str = ""
    environment: str = "development"
    loki_hostname: str = "loki"
    sentry_dsn: str = ""
    media_path: str = "/app/media"
    access_token_expire_minutes: int = 60 * 24
    telegram_webhook_secret: str = ""
    max_upload_size_mb: int = 50
    cdn_base: str = ""

    # LLM provider toggle: "gemini" | "moonshot". One env var switches the
    # whole stack; model ids and prices fall back to the provider profile
    # unless overridden explicitly.
    llm_provider: str = "gemini"
    moonshot_api_key: str = ""
    moonshot_base_url: str = "https://api.moonshot.ai/v1"
    google_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    # Empty = provider default. Gemini accepts "low"/"high"; cuts thinking tokens.
    llm_reasoning_effort: str = ""
    # Field defaults match the moonshot profile; apply_provider_profile
    # rewrites unset ones when llm_provider is gemini (the default).
    llm_model_main: str = "kimi-k2.6"
    llm_model_escalation: str = "kimi-k3"
    llm_token_cap_per_session: int = 200_000
    llm_price_in_per_1m: float = 0.95
    llm_price_out_per_1m: float = 4.0
    free_daily_budget_usd: float = 20.0
    free_sessions_per_day: int = 2

    # JRoots MCP archive-search gateway (streamable HTTP).
    jroots_mcp_enabled: bool = True
    jroots_mcp_url: str = "http://localhost:8100"
    jroots_mcp_token: str = ""
    jroots_mcp_timeout_seconds: float = 30.0
    mcp_tool_call_cap: int = 15
    mcp_rate_limit_per_db_seconds: float = 1.0
    # Token diet: hard cap on tool-result text shown to the model (chars).
    mcp_tool_result_max_chars: int = 8000
    # In-cycle history collapse: after this many rounds, tool results older
    # than the last N rounds are replaced with one-line digests.
    agent_collapse_after_rounds: int = 4
    agent_collapse_keep_rounds: int = 2

    # Payments (M4): Polar / NOWPayments / YuKassa.
    public_base_url: str = "http://localhost:8000"
    polar_api_key: str = ""
    polar_webhook_secret: str = ""
    polar_sandbox: bool = True
    polar_product_id_delo: str = ""
    polar_product_id_researcher: str = ""
    polar_product_id_scans_pack: str = ""
    polar_product_id_ppr: str = ""
    nowpayments_api_key: str = ""
    nowpayments_ipn_secret: str = ""
    yukassa_shop_id: str = ""
    yukassa_secret_key: str = ""
    yukassa_currency: str = "RUB"
    yukassa_usd_rate: float = 90.0

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def apply_provider_profile(self) -> Self:
        """Fill model/price fields from the active provider when unset in env."""
        profile = _PROVIDER_PROFILES.get(self.llm_provider, _PROVIDER_PROFILES["gemini"])
        for field, value in profile.items():
            if field not in self.model_fields_set:
                object.__setattr__(self, field, value)
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
