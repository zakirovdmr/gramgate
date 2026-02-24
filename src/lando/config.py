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

    # OpenClaw
    openclaw_url: str = Field(default="http://127.0.0.1:18789", alias="OPENCLAW_URL")
    openclaw_token: str = Field(..., alias="OPENCLAW_TOKEN")
    openclaw_model: str = Field(default="openclaw", alias="OPENCLAW_MODEL")

    model_config = {
        "env_file": ["/root/lando/.env", ".env"],
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
