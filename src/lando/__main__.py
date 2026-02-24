"""Lando entry point — python -m lando

Runs both:
- Pyrogram MTProto client (Telegram transport + message bridge)
- HTTP REST API (exposes Telegram tools to OpenClaw on port 18791)
"""

import asyncio
import logging
import signal

import uvicorn
from pyrogram import idle

from .api import create_app, set_telegram as api_set_tg
from .config import Settings
from .openclaw import OpenClawClient
from .telegram import LandoTelegram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

log = logging.getLogger("lando")

API_PORT = 18791


async def run():
    config = Settings()
    log.info(
        "Lando starting — OpenClaw at %s, Telegram phone %s, API on port %d",
        config.openclaw_url,
        config.telegram_phone,
        API_PORT,
    )

    openclaw = OpenClawClient(config.openclaw_url, config.openclaw_token, config.openclaw_model)
    tg = LandoTelegram(config, openclaw)

    # Wire API to Telegram client
    api_set_tg(tg)

    # Start Pyrogram
    await tg.start()

    # Start HTTP API server
    app = create_app()
    uv_config = uvicorn.Config(app, host="127.0.0.1", port=API_PORT, log_level="warning")
    uv_server = uvicorn.Server(uv_config)
    asyncio.create_task(uv_server.serve())
    log.info("REST API started on http://127.0.0.1:%d", API_PORT)

    # Graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda: asyncio.create_task(shutdown(tg, openclaw, uv_server))
        )

    await idle()


async def shutdown(tg, openclaw, uv_server):
    log.info("Shutting down...")
    uv_server.should_exit = True
    await tg.stop()
    await openclaw.close()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
