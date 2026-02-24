"""Lando HTTP REST API — simple JSON endpoints for Telegram account actions."""

import json
import logging
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from .telegram import LandoTelegram

log = logging.getLogger("lando.api")

_tg: "LandoTelegram | None" = None


def set_telegram(tg: "LandoTelegram"):
    global _tg
    _tg = tg


def _require_tg() -> "LandoTelegram":
    if _tg is None:
        raise RuntimeError("Telegram not initialized")
    return _tg


async def _json_body(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


# ==================== Endpoints ====================


async def get_me(request: Request) -> JSONResponse:
    tg = _require_tg()
    return JSONResponse(await tg.get_me())


async def get_dialogs(request: Request) -> JSONResponse:
    tg = _require_tg()
    limit = int(request.query_params.get("limit", "30"))
    return JSONResponse(await tg.get_dialogs(limit))


async def get_chat_info(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    cid = int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id
    return JSONResponse(await tg.get_chat_info(cid))


async def get_chat_history(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    limit = int(body.get("limit", 30))
    cid = int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id
    return JSONResponse(await tg.get_chat_history(cid, limit))


async def get_chat_members(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    limit = int(body.get("limit", 50))
    cid = int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id
    return JSONResponse(await tg.get_chat_members(cid, limit))


async def send_message(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    recipient = body.get("recipient", "")
    text = body.get("text", "")
    rcpt = int(recipient) if str(recipient).lstrip("-").isdigit() else recipient
    return JSONResponse(await tg.send_message_to(rcpt, text))


async def join_chat(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    link = body.get("link", "")
    return JSONResponse(await tg.join_chat(link))


async def leave_chat(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    cid = int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id
    return JSONResponse(await tg.leave_chat(cid))


async def search_messages(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    query = body.get("query", "")
    limit = int(body.get("limit", 20))
    cid = int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id
    return JSONResponse(await tg.search_messages(cid, query, limit))


async def search_global(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    query = body.get("query", "")
    limit = int(body.get("limit", 10))
    return JSONResponse(await tg.search_global(query, limit))


async def forward_messages(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    to_id = body.get("to_chat_id", "")
    from_id = body.get("from_chat_id", "")
    msg_ids = body.get("message_ids", [])
    to_cid = int(to_id) if str(to_id).lstrip("-").isdigit() else to_id
    from_cid = int(from_id) if str(from_id).lstrip("-").isdigit() else from_id
    return JSONResponse(await tg.forward_messages(to_cid, from_cid, msg_ids))


async def send_reaction(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    message_id = int(body.get("message_id", 0))
    emoji = body.get("emoji", "\U0001f44d")
    cid = int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id
    return JSONResponse(await tg.send_reaction(cid, message_id, emoji))


async def mark_read(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    cid = int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id
    return JSONResponse(await tg.read_chat(cid))


async def get_contacts(request: Request) -> JSONResponse:
    tg = _require_tg()
    return JSONResponse(await tg.get_contacts())


# ==================== Live Feed ====================


async def get_new_feed(request: Request) -> JSONResponse:
    tg = _require_tg()
    limit = int(request.query_params.get("limit", "100"))
    messages = tg.store.get_new_messages("openclaw", limit)
    return JSONResponse([
        {
            "message_id": m.message_id,
            "chat_id": m.chat_id,
            "chat_title": m.chat_title,
            "username": m.username,
            "text": m.text[:500] if m.text else "",
            "date": m.date,
            "has_media": m.has_media,
            "media_type": m.media_type,
        }
        for m in messages
    ])


async def get_chat_feed(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    limit = int(body.get("limit", 50))
    cid = int(chat_id) if str(chat_id).lstrip("-").isdigit() else int(chat_id)
    messages = tg.store.get_chat_feed(cid, limit)
    return JSONResponse([
        {
            "message_id": m.message_id,
            "username": m.username,
            "text": m.text[:500] if m.text else "",
            "date": m.date,
            "has_media": m.has_media,
            "media_type": m.media_type,
        }
        for m in messages
    ])


async def get_monitored_chats(request: Request) -> JSONResponse:
    tg = _require_tg()
    return JSONResponse(tg.store.get_all_chats())


# ==================== Health ====================


async def health(request: Request) -> JSONResponse:
    tg = _require_tg()
    return JSONResponse({"status": "ok", "running": tg._running})


# ==================== App ====================


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            # Account
            Route("/api/me", get_me, methods=["GET"]),
            Route("/api/contacts", get_contacts, methods=["GET"]),
            # Chats
            Route("/api/dialogs", get_dialogs, methods=["GET"]),
            Route("/api/chat/info", get_chat_info, methods=["POST"]),
            Route("/api/chat/history", get_chat_history, methods=["POST"]),
            Route("/api/chat/members", get_chat_members, methods=["POST"]),
            Route("/api/chat/join", join_chat, methods=["POST"]),
            Route("/api/chat/leave", leave_chat, methods=["POST"]),
            Route("/api/chat/read", mark_read, methods=["POST"]),
            # Messages
            Route("/api/message/send", send_message, methods=["POST"]),
            Route("/api/message/search", search_messages, methods=["POST"]),
            Route("/api/message/forward", forward_messages, methods=["POST"]),
            Route("/api/message/react", send_reaction, methods=["POST"]),
            Route("/api/search/global", search_global, methods=["POST"]),
            # Live Feed
            Route("/api/feed/new", get_new_feed, methods=["GET"]),
            Route("/api/feed/chat", get_chat_feed, methods=["POST"]),
            Route("/api/feed/chats", get_monitored_chats, methods=["GET"]),
        ],
    )
