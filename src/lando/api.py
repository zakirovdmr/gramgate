"""Lando HTTP REST API — simple JSON endpoints for Telegram account actions."""

import logging
import traceback
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from .telegram import LandoTelegram

log = logging.getLogger("lando.api")

_tg: "LandoTelegram | None" = None
_api_token: str = ""


def set_telegram(tg: "LandoTelegram"):
    global _tg
    _tg = tg


def _require_tg() -> "LandoTelegram":
    if _tg is None:
        raise RuntimeError("Telegram not initialized")
    return _tg


def _parse_chat_id(value) -> int | str:
    """Parse chat_id from request — numeric string to int, otherwise keep as string."""
    s = str(value)
    if s.lstrip("-").isdigit():
        return int(s)
    return s


async def _json_body(request: Request) -> dict:
    body = await request.body()
    if not body:
        return {}
    try:
        return await request.json()
    except Exception:
        raise ValueError("Invalid JSON body")


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=503)
        except Exception as e:
            log.error("Unhandled error: %s\n%s", e, traceback.format_exc())
            return JSONResponse({"error": str(e)}, status_code=500)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not _api_token:
            return await call_next(request)
        if request.url.path == "/health":
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {_api_token}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


_rate_limiter = None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not _rate_limiter:
            return await call_next(request)

        path = request.url.path
        if path == "/health":
            return await call_next(request)

        from .ratelimit import SEND_ACTIONS, JOIN_ACTIONS

        # Check action-specific limits
        if path in SEND_ACTIONS:
            # Try to extract chat_id for per-chat limiting
            chat_key = ""
            try:
                body = await request.body()
                if body:
                    import json
                    data = json.loads(body)
                    chat_key = str(data.get("chat_id", data.get("recipient", "")))
            except Exception:
                pass
            ok, retry = _rate_limiter.check_send(chat_key)
            if not ok:
                return JSONResponse(
                    {"error": "rate limit exceeded", "retry_after": round(retry, 1)},
                    status_code=429,
                    headers={"Retry-After": str(int(retry) + 1)},
                )
        elif path in JOIN_ACTIONS:
            ok, retry = _rate_limiter.check_join()
            if not ok:
                return JSONResponse(
                    {"error": "rate limit exceeded", "retry_after": round(retry, 1)},
                    status_code=429,
                    headers={"Retry-After": str(int(retry) + 1)},
                )

        # Global API rate
        ok, retry = _rate_limiter.check_api()
        if not ok:
            return JSONResponse(
                {"error": "rate limit exceeded", "retry_after": round(retry, 1)},
                status_code=429,
                headers={"Retry-After": str(int(retry) + 1)},
            )

        return await call_next(request)


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
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.get_chat_info(cid))


async def get_chat_history(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    limit = int(body.get("limit", 30))
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.get_chat_history(cid, limit))


async def get_chat_members(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    limit = int(body.get("limit", 50))
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.get_chat_members(cid, limit))


async def get_chat_history_rich(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    limit = int(body.get("limit", 30))
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.get_chat_history_rich(cid, limit))


async def click_inline_button(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    message_id = int(body.get("message_id", 0))
    callback_data = body.get("callback_data", "")
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.click_inline_button(cid, message_id, callback_data))


async def send_message(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    recipient = body.get("recipient", "")
    text = body.get("text", "")
    rcpt = _parse_chat_id(recipient)
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
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.leave_chat(cid))


async def search_messages(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    query = body.get("query", "")
    limit = int(body.get("limit", 20))
    cid = _parse_chat_id(chat_id)
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
    to_cid = _parse_chat_id(to_id)
    from_cid = _parse_chat_id(from_id)
    return JSONResponse(await tg.forward_messages(to_cid, from_cid, msg_ids))


async def send_reaction(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    message_id = int(body.get("message_id", 0))
    emoji = body.get("emoji", "\U0001f44d")
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.send_reaction(cid, message_id, emoji))


async def mark_read(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    cid = _parse_chat_id(chat_id)
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
    cid = _parse_chat_id(chat_id)
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


# ==================== Edit / Delete ====================


async def edit_message(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    message_id = int(body.get("message_id", 0))
    text = body.get("text", "")
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.edit_message(cid, message_id, text))


async def delete_messages(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    message_ids = body.get("message_ids", [])
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.delete_messages(cid, message_ids))


# ==================== Pin / Unpin ====================


async def pin_message(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    message_id = int(body.get("message_id", 0))
    disable_notification = body.get("disable_notification", False)
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.pin_message(cid, message_id, disable_notification=disable_notification))


async def unpin_message(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    message_id = int(body.get("message_id", 0))
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.unpin_message(cid, message_id))


async def unpin_all_messages(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.unpin_all_messages(cid))


# ==================== Chat management ====================


async def create_group(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    title = body.get("title", "")
    users = body.get("users", [])
    return JSONResponse(await tg.create_group(title, users))


async def create_channel(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    title = body.get("title", "")
    description = body.get("description", "")
    return JSONResponse(await tg.create_channel(title, description))


async def create_supergroup(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    title = body.get("title", "")
    description = body.get("description", "")
    return JSONResponse(await tg.create_supergroup(title, description))


async def set_chat_title(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    title = body.get("title", "")
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.set_chat_title(cid, title))


async def set_chat_description(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    description = body.get("description", "")
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.set_chat_description(cid, description))


async def delete_chat_photo(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.delete_chat_photo(cid))


async def archive_chats(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_ids = body.get("chat_ids", [])
    return JSONResponse(await tg.archive_chats(chat_ids))


async def unarchive_chats(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_ids = body.get("chat_ids", [])
    return JSONResponse(await tg.unarchive_chats(chat_ids))


async def export_chat_invite_link(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.export_chat_invite_link(cid))


async def create_chat_invite_link(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    name = body.get("name", "")
    expire_date = body.get("expire_date")
    member_limit = int(body.get("member_limit", 0))
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.create_chat_invite_link(cid, name, expire_date, member_limit))


# ==================== User / Member management ====================


async def ban_chat_member(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    user_id = int(body.get("user_id", 0))
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.ban_chat_member(cid, user_id))


async def unban_chat_member(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    user_id = int(body.get("user_id", 0))
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.unban_chat_member(cid, user_id))


async def restrict_chat_member(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    user_id = int(body.get("user_id", 0))
    permissions = body.get("permissions", {})
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.restrict_chat_member(cid, user_id, permissions))


async def promote_chat_member(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    user_id = int(body.get("user_id", 0))
    privileges = body.get("privileges", {})
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.promote_chat_member(cid, user_id, privileges))


async def add_chat_members(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    user_ids = body.get("user_ids", [])
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.add_chat_members(cid, user_ids))


async def block_user(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    user_id = int(body.get("user_id", 0))
    return JSONResponse(await tg.block_user(user_id))


async def unblock_user(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    user_id = int(body.get("user_id", 0))
    return JSONResponse(await tg.unblock_user(user_id))


async def get_users(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    user_ids = body.get("user_ids", [])
    return JSONResponse(await tg.get_users(user_ids))


async def get_profile_photos(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    limit = int(body.get("limit", 10))
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.get_profile_photos(cid, limit))


# ==================== Polls ====================


async def send_poll(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    question = body.get("question", "")
    options = body.get("options", [])
    is_anonymous = body.get("is_anonymous", True)
    poll_type = body.get("poll_type", "regular")
    allows_multiple = body.get("allows_multiple_answers", False)
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.send_poll(cid, question, options, is_anonymous, poll_type, allows_multiple))


async def stop_poll(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    message_id = int(body.get("message_id", 0))
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.stop_poll(cid, message_id))


async def vote_poll(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    message_id = int(body.get("message_id", 0))
    option_ids = body.get("option_ids", [])
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.vote_poll(cid, message_id, option_ids))


# ==================== Copy / Scheduled / Get messages ====================


async def copy_message(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    to_id = body.get("to_chat_id", "")
    from_id = body.get("from_chat_id", "")
    message_id = int(body.get("message_id", 0))
    to_cid = _parse_chat_id(to_id)
    from_cid = _parse_chat_id(from_id)
    return JSONResponse(await tg.copy_message(to_cid, from_cid, message_id))


async def send_scheduled_message(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    text = body.get("text", "")
    schedule_date = body.get("schedule_date", 0)
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.send_scheduled_message(cid, text, schedule_date))


async def get_messages(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    message_ids = body.get("message_ids", [])
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.get_messages(cid, message_ids))


async def download_media(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    message_id = int(body.get("message_id", 0))
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.download_media(cid, message_id))


# ==================== Location / Contact ====================


async def send_location(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    latitude = float(body.get("latitude", 0))
    longitude = float(body.get("longitude", 0))
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.send_location(cid, latitude, longitude))


async def send_contact(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    phone = body.get("phone_number", "")
    first_name = body.get("first_name", "")
    last_name = body.get("last_name", "")
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.send_contact(cid, phone, first_name, last_name))


# ==================== Misc ====================


async def set_typing(request: Request) -> JSONResponse:
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = body.get("chat_id", "")
    action = body.get("action", "typing")
    cid = _parse_chat_id(chat_id)
    return JSONResponse(await tg.set_typing(cid, action))


# ==================== Health ====================


async def skip_chat(request: Request) -> JSONResponse:
    """Add/remove chat_id from the OpenClaw bridge skip list."""
    tg = _require_tg()
    body = await _json_body(request)
    chat_id = int(body.get("chat_id", 0))
    action = body.get("action", "add")  # "add" or "remove"
    if action == "remove":
        tg._skip_chat_ids.discard(chat_id)
    else:
        tg._skip_chat_ids.add(chat_id)
    return JSONResponse({"ok": True, "skip_chat_ids": list(tg._skip_chat_ids)})


async def health(request: Request) -> JSONResponse:
    tg = _require_tg()
    return JSONResponse({"status": "ok", "running": tg._running})


# ==================== App ====================


def create_app(api_token: str = "", rate_limiter=None) -> Starlette:
    global _api_token, _rate_limiter
    _api_token = api_token
    _rate_limiter = rate_limiter

    return Starlette(
        middleware=[
            Middleware(ErrorHandlerMiddleware),
            Middleware(AuthMiddleware),
            Middleware(RateLimitMiddleware),
        ],
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/api/chat/skip", skip_chat, methods=["POST"]),
            # Account
            Route("/api/me", get_me, methods=["GET"]),
            Route("/api/contacts", get_contacts, methods=["GET"]),
            Route("/api/users", get_users, methods=["POST"]),
            Route("/api/users/photos", get_profile_photos, methods=["POST"]),
            # Chats
            Route("/api/dialogs", get_dialogs, methods=["GET"]),
            Route("/api/chat/info", get_chat_info, methods=["POST"]),
            Route("/api/chat/history", get_chat_history, methods=["POST"]),
            Route("/api/chat/history/rich", get_chat_history_rich, methods=["POST"]),
            Route("/api/button/click", click_inline_button, methods=["POST"]),
            Route("/api/chat/members", get_chat_members, methods=["POST"]),
            Route("/api/chat/join", join_chat, methods=["POST"]),
            Route("/api/chat/leave", leave_chat, methods=["POST"]),
            Route("/api/chat/read", mark_read, methods=["POST"]),
            Route("/api/chat/create/group", create_group, methods=["POST"]),
            Route("/api/chat/create/channel", create_channel, methods=["POST"]),
            Route("/api/chat/create/supergroup", create_supergroup, methods=["POST"]),
            Route("/api/chat/title", set_chat_title, methods=["POST"]),
            Route("/api/chat/description", set_chat_description, methods=["POST"]),
            Route("/api/chat/photo/delete", delete_chat_photo, methods=["POST"]),
            Route("/api/chat/archive", archive_chats, methods=["POST"]),
            Route("/api/chat/unarchive", unarchive_chats, methods=["POST"]),
            Route("/api/chat/invite/export", export_chat_invite_link, methods=["POST"]),
            Route("/api/chat/invite/create", create_chat_invite_link, methods=["POST"]),
            # Messages
            Route("/api/message/send", send_message, methods=["POST"]),
            Route("/api/message/edit", edit_message, methods=["POST"]),
            Route("/api/message/delete", delete_messages, methods=["POST"]),
            Route("/api/message/pin", pin_message, methods=["POST"]),
            Route("/api/message/unpin", unpin_message, methods=["POST"]),
            Route("/api/message/unpin/all", unpin_all_messages, methods=["POST"]),
            Route("/api/message/search", search_messages, methods=["POST"]),
            Route("/api/message/forward", forward_messages, methods=["POST"]),
            Route("/api/message/copy", copy_message, methods=["POST"]),
            Route("/api/message/react", send_reaction, methods=["POST"]),
            Route("/api/message/get", get_messages, methods=["POST"]),
            Route("/api/message/scheduled", send_scheduled_message, methods=["POST"]),
            Route("/api/message/media/download", download_media, methods=["POST"]),
            Route("/api/search/global", search_global, methods=["POST"]),
            # Members
            Route("/api/member/ban", ban_chat_member, methods=["POST"]),
            Route("/api/member/unban", unban_chat_member, methods=["POST"]),
            Route("/api/member/restrict", restrict_chat_member, methods=["POST"]),
            Route("/api/member/promote", promote_chat_member, methods=["POST"]),
            Route("/api/member/add", add_chat_members, methods=["POST"]),
            # User actions
            Route("/api/user/block", block_user, methods=["POST"]),
            Route("/api/user/unblock", unblock_user, methods=["POST"]),
            # Polls
            Route("/api/poll/send", send_poll, methods=["POST"]),
            Route("/api/poll/stop", stop_poll, methods=["POST"]),
            Route("/api/poll/vote", vote_poll, methods=["POST"]),
            # Location / Contact
            Route("/api/send/location", send_location, methods=["POST"]),
            Route("/api/send/contact", send_contact, methods=["POST"]),
            # Misc
            Route("/api/typing", set_typing, methods=["POST"]),
            # Live Feed
            Route("/api/feed/new", get_new_feed, methods=["GET"]),
            Route("/api/feed/chat", get_chat_feed, methods=["POST"]),
            Route("/api/feed/chats", get_monitored_chats, methods=["GET"]),
        ],
    )
