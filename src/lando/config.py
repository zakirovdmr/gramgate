"""Lando configuration."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Lando configuration from environment variables."""

    # Telegram MTProto
    telegram_api_id: int = Field(..., alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(..., alias="TELEGRAM_API_HASH")
    telegram_phone: str = Field(..., alias="TELEGRAM_PHONE")
    telegram_session_dir: str = Field(default="./sessions", alias="TELEGRAM_SESSION_DIR")

    # API
    api_port: int = Field(default=18791, alias="LANDO_API_PORT")
    api_token: str = Field(default="", alias="LANDO_API_TOKEN")
    api_host: str = Field(default="127.0.0.1", alias="LANDO_API_HOST")

    # OpenClaw (optional — bridge disabled if token is empty)
    openclaw_url: str = Field(default="http://127.0.0.1:18789", alias="OPENCLAW_URL")
    openclaw_token: str = Field(default="", alias="OPENCLAW_TOKEN")
    openclaw_model: str = Field(default="openclaw", alias="OPENCLAW_MODEL")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
