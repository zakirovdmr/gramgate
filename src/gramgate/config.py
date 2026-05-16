"""GramGate configuration."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """GramGate configuration from environment variables."""

    # Telegram MTProto
    telegram_api_id: int = Field(..., alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(..., alias="TELEGRAM_API_HASH")
    telegram_phone: str = Field(..., alias="TELEGRAM_PHONE")
    telegram_session_dir: str = Field(default="./sessions", alias="TELEGRAM_SESSION_DIR")

    # API
    api_port: int = Field(default=18791, alias="GRAMGATE_API_PORT")
    api_token: str = Field(default="", alias="GRAMGATE_API_TOKEN")
    api_host: str = Field(default="127.0.0.1", alias="GRAMGATE_API_HOST")

    # MCP server (0 = disabled)
    mcp_port: int = Field(default=18793, alias="GRAMGATE_MCP_PORT")

    # Rate limits (0 = disabled, values are max requests per window)
    rate_send_per_chat: int = Field(default=20, alias="GRAMGATE_RATE_SEND_PER_CHAT")  # per 60s
    rate_send_global: int = Field(default=30, alias="GRAMGATE_RATE_SEND_GLOBAL")  # per 60s
    rate_join: int = Field(default=5, alias="GRAMGATE_RATE_JOIN")  # per 3600s
    rate_api_global: int = Field(default=25, alias="GRAMGATE_RATE_API_GLOBAL")  # per 1s

    # OpenClaw (optional — bridge disabled if token is empty)
    openclaw_url: str = Field(default="http://127.0.0.1:18789", alias="OPENCLAW_URL")
    openclaw_token: str = Field(default="", alias="OPENCLAW_TOKEN")
    openclaw_model: str = Field(default="openclaw", alias="OPENCLAW_MODEL")

    # Chat IDs the OpenClaw bridge must never forward (bots we drive via the
    # API/MCP — e.g. reframir_bot — would otherwise loop: bot replies →
    # bridge → OpenClaw → bot). Comma-separated. Seeds the persistent
    # skip-list on startup; runtime /api/chat/skip additions persist too.
    bridge_skip_chats: str = Field(default="", alias="GRAMGATE_BRIDGE_SKIP_CHATS")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
