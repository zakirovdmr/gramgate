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
from .telegram import LandoTelegram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

log = logging.getLogger("lando")

async def run():
    config = Settings()

    # OpenClaw bridge is optional
    openclaw = None
    if config.openclaw_token:
        from .openclaw import OpenClawClient
        openclaw = OpenClawClient(config.openclaw_url, config.openclaw_token, config.openclaw_model)
        log.info("OpenClaw bridge enabled at %s", config.openclaw_url)
    else:
        log.info("OpenClaw bridge disabled (OPENCLAW_TOKEN not set)")

    tg = LandoTelegram(config, openclaw)

    # Wire API to Telegram client
    api_set_tg(tg)

    # Start Pyrogram
    await tg.start()

    # Rate limiter
    from .ratelimit import RateLimiter, RateLimit
    rate_limiter = RateLimiter(
        send_per_chat=RateLimit(config.rate_send_per_chat, 60),
        send_global=RateLimit(config.rate_send_global, 60),
        join_leave=RateLimit(config.rate_join, 3600),
        api_global=RateLimit(config.rate_api_global, 1),
    )
    log.info(
        "Rate limits: send=%d/chat/min, %d/global/min, join=%d/hr, api=%d/sec",
        config.rate_send_per_chat, config.rate_send_global,
        config.rate_join, config.rate_api_global,
    )

    # Start HTTP API server
    app = create_app(api_token=config.api_token, rate_limiter=rate_limiter)
    uv_config = uvicorn.Config(app, host=config.api_host, port=config.api_port, log_level="warning")
    uv_server = uvicorn.Server(uv_config)
    asyncio.create_task(uv_server.serve())
    log.info(
        "Lando started — phone %s, REST API on http://%s:%d",
        config.telegram_phone, config.api_host, config.api_port,
    )

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
    if openclaw:
        await openclaw.close()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
