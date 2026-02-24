"""Lando MCP server — exposes Telegram account capabilities as tools."""

import json
import logging
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from .telegram import LandoTelegram

log = logging.getLogger("lando.mcp")

mcp = FastMCP("lando-telegram")

# Reference to the running LandoTelegram instance (set at startup)
_tg: "LandoTelegram | None" = None


def set_telegram(tg: "LandoTelegram"):
    global _tg
    _tg = tg


def _require_tg() -> "LandoTelegram":
    if _tg is None:
        raise RuntimeError("Telegram client not initialized")
    return _tg


# ==================== Account ====================


@mcp.tool()
async def telegram_get_me() -> str:
    """Get current Telegram account info (id, username, phone)."""
    tg = _require_tg()
    return json.dumps(await tg.get_me(), ensure_ascii=False)


# ==================== Chats & Channels ====================


@mcp.tool()
async def telegram_get_dialogs(limit: int = 30) -> str:
    """List all Telegram chats, groups, and channels (most recent first).
    Each entry has: chat_id, title, username, type, unread count, last message preview."""
    tg = _require_tg()
    return json.dumps(await tg.get_dialogs(limit), ensure_ascii=False)


@mcp.tool()
async def telegram_get_chat_info(chat_id: str) -> str:
    """Get detailed info about a chat/channel/user.
    chat_id can be numeric ID or @username."""
    tg = _require_tg()
    cid = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
    return json.dumps(await tg.get_chat_info(cid), ensure_ascii=False)


@mcp.tool()
async def telegram_get_chat_history(chat_id: str, limit: int = 30) -> str:
    """Read recent messages from any chat, group, or channel.
    chat_id can be numeric ID or @username. Returns up to `limit` messages."""
    tg = _require_tg()
    cid = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
    return json.dumps(await tg.get_chat_history(cid, limit), ensure_ascii=False)


@mcp.tool()
async def telegram_get_chat_members(chat_id: str, limit: int = 50) -> str:
    """Get members of a group or channel. Returns user_id, username, first_name, status."""
    tg = _require_tg()
    cid = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
    return json.dumps(await tg.get_chat_members(cid, limit), ensure_ascii=False)


@mcp.tool()
async def telegram_join_chat(link: str) -> str:
    """Join a channel or group by link or @username.
    Supports: @channel, t.me/channel, https://t.me/+invite"""
    tg = _require_tg()
    return json.dumps(await tg.join_chat(link), ensure_ascii=False)


@mcp.tool()
async def telegram_leave_chat(chat_id: str) -> str:
    """Leave a channel or group."""
    tg = _require_tg()
    cid = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
    return json.dumps(await tg.leave_chat(cid), ensure_ascii=False)


# ==================== Messages ====================


@mcp.tool()
async def telegram_send_message(recipient: str, text: str) -> str:
    """Send a message to any user or chat.
    recipient can be @username, phone number, or numeric chat_id.
    Long messages are automatically split into 4096-char chunks."""
    tg = _require_tg()
    rcpt = int(recipient) if recipient.lstrip("-").isdigit() else recipient
    return json.dumps(await tg.send_message_to(rcpt, text), ensure_ascii=False)


@mcp.tool()
async def telegram_search_messages(chat_id: str, query: str, limit: int = 20) -> str:
    """Search messages in a specific chat by text query."""
    tg = _require_tg()
    cid = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
    return json.dumps(await tg.search_messages(cid, query, limit), ensure_ascii=False)


@mcp.tool()
async def telegram_search_global(query: str, limit: int = 10) -> str:
    """Search globally for public chats, channels, and users by name/keyword."""
    tg = _require_tg()
    return json.dumps(await tg.search_global(query, limit), ensure_ascii=False)


@mcp.tool()
async def telegram_forward_messages(
    to_chat_id: str, from_chat_id: str, message_ids: str
) -> str:
    """Forward messages from one chat to another.
    message_ids: comma-separated list of message IDs (e.g. "123,456,789")."""
    tg = _require_tg()
    to_cid = int(to_chat_id) if to_chat_id.lstrip("-").isdigit() else to_chat_id
    from_cid = int(from_chat_id) if from_chat_id.lstrip("-").isdigit() else from_chat_id
    ids = [int(x.strip()) for x in message_ids.split(",")]
    return json.dumps(await tg.forward_messages(to_cid, from_cid, ids), ensure_ascii=False)


@mcp.tool()
async def telegram_send_reaction(chat_id: str, message_id: int, emoji: str = "\U0001f44d") -> str:
    """React to a message with an emoji (e.g. "👍", "❤️", "🔥")."""
    tg = _require_tg()
    cid = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
    return json.dumps(await tg.send_reaction(cid, message_id, emoji), ensure_ascii=False)


@mcp.tool()
async def telegram_mark_read(chat_id: str) -> str:
    """Mark all messages in a chat as read."""
    tg = _require_tg()
    cid = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
    return json.dumps(await tg.read_chat(cid), ensure_ascii=False)


# ==================== Contacts ====================


@mcp.tool()
async def telegram_get_contacts() -> str:
    """Get the full contact list of this Telegram account."""
    tg = _require_tg()
    return json.dumps(await tg.get_contacts(), ensure_ascii=False)


# ==================== Live Feed ====================


@mcp.tool()
async def telegram_get_new_feed(limit: int = 100) -> str:
    """Get new messages from ALL monitored channels and groups since last check.
    Messages are collected in real-time as they arrive.
    Each call returns only NEW messages (not seen before by this consumer).
    Returns: list of {message_id, chat_id, chat_title, username, text, date, media_type}."""
    tg = _require_tg()
    messages = tg.store.get_new_messages("openclaw", limit)
    return json.dumps(
        [
            {
                "message_id": m.message_id,
                "chat_id": m.chat_id,
                "chat_title": m.chat_title,
                "username": m.username,
                "first_name": m.first_name,
                "text": m.text[:500] if m.text else "",
                "date": m.date,
                "has_media": m.has_media,
                "media_type": m.media_type,
            }
            for m in messages
        ],
        ensure_ascii=False,
    )


@mcp.tool()
async def telegram_get_chat_feed(chat_id: str, limit: int = 50) -> str:
    """Get stored messages from a specific channel/group (from live monitoring buffer).
    Only contains messages received while Lando is running."""
    tg = _require_tg()
    cid = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
    messages = tg.store.get_chat_feed(cid, limit)
    return json.dumps(
        [
            {
                "message_id": m.message_id,
                "username": m.username,
                "text": m.text[:500] if m.text else "",
                "date": m.date,
                "has_media": m.has_media,
                "media_type": m.media_type,
            }
            for m in messages
        ],
        ensure_ascii=False,
    )


@mcp.tool()
async def telegram_get_monitored_chats() -> str:
    """List all channels/groups that have received messages since Lando started.
    Shows chat_id, title, message count, and last message preview."""
    tg = _require_tg()
    return json.dumps(tg.store.get_all_chats(), ensure_ascii=False, default=str)
