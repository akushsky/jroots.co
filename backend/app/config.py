from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str
    algorithm: str = "HS256"
    admin_password: str
    database_url: str
    cors_origins: str = "http://localhost:5173"
    frontend_url: str = "http://localhost:5173"
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

    moonshot_api_key: str = ""
    moonshot_base_url: str = "https://api.moonshot.ai/v1"
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

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
