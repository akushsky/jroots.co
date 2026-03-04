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
    media_path: str = "/app/media"
    access_token_expire_minutes: int = 60 * 24
    telegram_webhook_secret: str = ""

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
