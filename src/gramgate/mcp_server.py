"""GramGate MCP server — exposes Telegram account capabilities as tools."""

import functools
import json
import logging
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from .telegram import GramGateTelegram

log = logging.getLogger("gramgate.mcp")

mcp = FastMCP("gramgate-telegram")


def _parse_id(value: str) -> int | str:
    """Parse ID — numeric string to int, otherwise keep as string."""
    if value.lstrip("-").isdigit():
        return int(value)
    return value

# Reference to the running GramGateTelegram instance (set at startup)
_tg: "GramGateTelegram | None" = None


def set_telegram(tg: "GramGateTelegram"):
    global _tg
    _tg = tg


def _require_tg() -> "GramGateTelegram":
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
    cid = _parse_id(chat_id)
    return json.dumps(await tg.get_chat_info(cid), ensure_ascii=False)


@mcp.tool()
async def telegram_get_chat_history(chat_id: str, limit: int = 30, offset_id: int = 0, reverse: bool = False) -> str:
    """Read messages from any chat, group, or channel.
    chat_id can be numeric ID or @username. Returns up to `limit` messages.
    offset_id: start from this message ID (0 = latest). reverse: True = oldest first."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.get_chat_history(cid, limit, offset_id=offset_id, reverse=reverse), ensure_ascii=False)


@mcp.tool()
async def telegram_get_chat_members(chat_id: str, limit: int = 50) -> str:
    """Get members of a group or channel. Returns user_id, username, first_name, status."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
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
    cid = _parse_id(chat_id)
    return json.dumps(await tg.leave_chat(cid), ensure_ascii=False)


# ==================== Messages ====================


@mcp.tool()
async def telegram_send_message(recipient: str, text: str) -> str:
    """Send a message to any user or chat.
    recipient can be @username, phone number, or numeric chat_id.
    Long messages are automatically split into 4096-char chunks."""
    tg = _require_tg()
    rcpt = _parse_id(recipient)
    return json.dumps(await tg.send_message_to(rcpt, text), ensure_ascii=False)


@mcp.tool()
async def telegram_send_document(recipient: str, file_path: str, caption: str = "") -> str:
    """Send a local file as a Telegram document (original bytes, not compressed).
    Use for .md, .pdf, .zip, code files, or any file you want delivered as-is.
    recipient: @username, phone number, or numeric chat_id.
    file_path: absolute path to a local file on the machine running GramGate.
    caption: optional text shown under the file (supports Markdown, max 1024 chars)."""
    import os
    tg = _require_tg()
    if not os.path.isfile(file_path):
        return json.dumps({"error": f"file not found: {file_path}"}, ensure_ascii=False)
    rcpt = _parse_id(recipient)
    return json.dumps(await tg.send_file(rcpt, file_path, caption), ensure_ascii=False)


@mcp.tool()
async def telegram_send_photo(recipient: str, photo_path: str, caption: str = "") -> str:
    """Send a local image as a Telegram photo (compressed, inline preview).
    Use for .jpg, .png, .webp shown as a regular photo. For original-quality image
    delivery use telegram_send_document instead.
    recipient: @username, phone number, or numeric chat_id.
    photo_path: absolute path to a local image file.
    caption: optional text shown under the photo (supports Markdown, max 1024 chars)."""
    import os
    tg = _require_tg()
    if not os.path.isfile(photo_path):
        return json.dumps({"error": f"file not found: {photo_path}"}, ensure_ascii=False)
    rcpt = _parse_id(recipient)
    return json.dumps(await tg.send_photo(rcpt, photo_path, caption), ensure_ascii=False)


@mcp.tool()
async def telegram_search_messages(chat_id: str, query: str, limit: int = 20) -> str:
    """Search messages in a specific chat by text query."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
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
    to_cid = _parse_id(to_chat_id)
    from_cid = _parse_id(from_chat_id)
    ids = [int(x.strip()) for x in message_ids.split(",")]
    return json.dumps(await tg.forward_messages(to_cid, from_cid, ids), ensure_ascii=False)


@mcp.tool()
async def telegram_send_reaction(chat_id: str, message_id: int, emoji: str = "\U0001f44d") -> str:
    """React to a message with an emoji (e.g. "👍", "❤️", "🔥")."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.send_reaction(cid, message_id, emoji), ensure_ascii=False)


@mcp.tool()
async def telegram_mark_read(chat_id: str) -> str:
    """Mark all messages in a chat as read."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
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
    Only contains messages received while GramGate is running."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
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
    """List all channels/groups that have received messages since GramGate started.
    Shows chat_id, title, message count, and last message preview."""
    tg = _require_tg()
    return json.dumps(tg.store.get_all_chats(), ensure_ascii=False, default=str)


# ==================== Edit / Delete ====================


@mcp.tool()
async def telegram_edit_message(chat_id: str, message_id: int, text: str) -> str:
    """Edit a previously sent message. Only your own messages can be edited.
    chat_id can be numeric ID or @username."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.edit_message(cid, message_id, text), ensure_ascii=False)


@mcp.tool()
async def telegram_delete_messages(chat_id: str, message_ids: str) -> str:
    """Delete messages from a chat.
    message_ids: comma-separated IDs (e.g. "123,456").
    In private chats, deletes for both sides. In groups, needs admin rights for others' messages."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    ids = [int(x.strip()) for x in message_ids.split(",")]
    return json.dumps(await tg.delete_messages(cid, ids), ensure_ascii=False)


# ==================== Pin / Unpin ====================


@mcp.tool()
async def telegram_pin_message(chat_id: str, message_id: int, disable_notification: bool = False) -> str:
    """Pin a message in a chat. Requires admin rights in groups/channels."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.pin_message(cid, message_id, disable_notification=disable_notification), ensure_ascii=False)


@mcp.tool()
async def telegram_unpin_message(chat_id: str, message_id: int = 0) -> str:
    """Unpin a specific message (by message_id) or the most recent pinned message (if message_id=0)."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.unpin_message(cid, message_id), ensure_ascii=False)


@mcp.tool()
async def telegram_unpin_all_messages(chat_id: str) -> str:
    """Unpin ALL pinned messages in a chat."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.unpin_all_messages(cid), ensure_ascii=False)


# ==================== Chat management ====================


@mcp.tool()
async def telegram_create_group(title: str, users: str) -> str:
    """Create a new private group chat.
    users: comma-separated user IDs or @usernames (e.g. "123456,@username")."""
    tg = _require_tg()
    user_list = []
    for u in users.split(","):
        u = u.strip()
        user_list.append(_parse_id(u))
    return json.dumps(await tg.create_group(title, user_list), ensure_ascii=False)


@mcp.tool()
async def telegram_create_channel(title: str, description: str = "") -> str:
    """Create a new broadcast channel."""
    tg = _require_tg()
    return json.dumps(await tg.create_channel(title, description), ensure_ascii=False)


@mcp.tool()
async def telegram_create_supergroup(title: str, description: str = "") -> str:
    """Create a new supergroup (megagroup with advanced features)."""
    tg = _require_tg()
    return json.dumps(await tg.create_supergroup(title, description), ensure_ascii=False)


@mcp.tool()
async def telegram_set_chat_title(chat_id: str, title: str) -> str:
    """Change the title of a group or channel. Requires admin rights."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.set_chat_title(cid, title), ensure_ascii=False)


@mcp.tool()
async def telegram_set_chat_description(chat_id: str, description: str) -> str:
    """Change the description of a group or channel. Requires admin rights."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.set_chat_description(cid, description), ensure_ascii=False)


@mcp.tool()
async def telegram_delete_chat_photo(chat_id: str) -> str:
    """Remove the photo of a group or channel. Requires admin rights."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.delete_chat_photo(cid), ensure_ascii=False)


@mcp.tool()
async def telegram_archive_chats(chat_ids: str) -> str:
    """Archive one or more chats. chat_ids: comma-separated IDs."""
    tg = _require_tg()
    ids = [int(x.strip()) for x in chat_ids.split(",")]
    return json.dumps(await tg.archive_chats(ids), ensure_ascii=False)


@mcp.tool()
async def telegram_unarchive_chats(chat_ids: str) -> str:
    """Unarchive one or more chats. chat_ids: comma-separated IDs."""
    tg = _require_tg()
    ids = [int(x.strip()) for x in chat_ids.split(",")]
    return json.dumps(await tg.unarchive_chats(ids), ensure_ascii=False)


@mcp.tool()
async def telegram_export_chat_invite_link(chat_id: str) -> str:
    """Export (regenerate) the primary invite link for a chat. Requires admin rights."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.export_chat_invite_link(cid), ensure_ascii=False)


@mcp.tool()
async def telegram_create_chat_invite_link(chat_id: str, name: str = "", expire_date: int = 0, member_limit: int = 0) -> str:
    """Create an additional invite link for a chat.
    expire_date: Unix timestamp when the link expires (0 = no expiry).
    member_limit: max joins via this link (0 = unlimited)."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.create_chat_invite_link(cid, name, expire_date or None, member_limit), ensure_ascii=False)


# ==================== User / Member management ====================


@mcp.tool()
async def telegram_ban_chat_member(chat_id: str, user_id: int) -> str:
    """Ban a user from a group or channel. Requires admin rights with ban permission."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.ban_chat_member(cid, user_id), ensure_ascii=False)


@mcp.tool()
async def telegram_unban_chat_member(chat_id: str, user_id: int) -> str:
    """Unban a previously banned user from a group or channel."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.unban_chat_member(cid, user_id), ensure_ascii=False)


@mcp.tool()
async def telegram_restrict_chat_member(chat_id: str, user_id: int, permissions: str) -> str:
    """Restrict a user in a group (mute, no media, no links, etc.).
    permissions: JSON object with ChatPermissions fields, e.g.
    '{"can_send_messages": false, "can_send_media_messages": false}'"""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    perms = json.loads(permissions)
    return json.dumps(await tg.restrict_chat_member(cid, user_id, perms), ensure_ascii=False)


@mcp.tool()
async def telegram_promote_chat_member(chat_id: str, user_id: int, privileges: str) -> str:
    """Promote a user to admin in a group/channel.
    privileges: JSON object with ChatPrivileges fields, e.g.
    '{"can_manage_chat": true, "can_delete_messages": true, "can_pin_messages": true}'"""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    privs = json.loads(privileges)
    return json.dumps(await tg.promote_chat_member(cid, user_id, privs), ensure_ascii=False)


@mcp.tool()
async def telegram_add_chat_members(chat_id: str, user_ids: str) -> str:
    """Add users to a group. user_ids: comma-separated IDs or @usernames."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    users = []
    for u in user_ids.split(","):
        u = u.strip()
        users.append(_parse_id(u))
    return json.dumps(await tg.add_chat_members(cid, users), ensure_ascii=False)


@mcp.tool()
async def telegram_block_user(user_id: int) -> str:
    """Block a user (they won't be able to message you)."""
    tg = _require_tg()
    return json.dumps(await tg.block_user(user_id), ensure_ascii=False)


@mcp.tool()
async def telegram_unblock_user(user_id: int) -> str:
    """Unblock a previously blocked user."""
    tg = _require_tg()
    return json.dumps(await tg.unblock_user(user_id), ensure_ascii=False)


@mcp.tool()
async def telegram_get_users(user_ids: str) -> str:
    """Get detailed info about users by ID or @username.
    user_ids: comma-separated (e.g. "123456,@username").
    Returns: id, username, first_name, last_name, phone, is_bot, is_premium, status, last_online."""
    tg = _require_tg()
    users = []
    for u in user_ids.split(","):
        u = u.strip()
        users.append(_parse_id(u))
    return json.dumps(await tg.get_users(users), ensure_ascii=False)


@mcp.tool()
async def telegram_get_profile_photos(chat_id: str, limit: int = 10) -> str:
    """Get profile photos of a user or chat. Returns file_id, date, file_size."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.get_profile_photos(cid, limit), ensure_ascii=False)


# ==================== Polls ====================


@mcp.tool()
async def telegram_send_poll(chat_id: str, question: str, options: str, is_anonymous: bool = True, poll_type: str = "regular", allows_multiple_answers: bool = False) -> str:
    """Send a poll to a chat.
    options: comma-separated poll options (e.g. "Yes,No,Maybe").
    poll_type: "regular" or "quiz". For quiz, first option is the correct answer."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    opts = [o.strip() for o in options.split(",")]
    return json.dumps(await tg.send_poll(cid, question, opts, is_anonymous, poll_type, allows_multiple_answers), ensure_ascii=False)


@mcp.tool()
async def telegram_stop_poll(chat_id: str, message_id: int) -> str:
    """Stop a running poll and get final results."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.stop_poll(cid, message_id), ensure_ascii=False)


@mcp.tool()
async def telegram_vote_poll(chat_id: str, message_id: int, option_ids: str) -> str:
    """Vote in a poll. option_ids: comma-separated 0-based indices (e.g. "0" or "0,2")."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    ids = [int(x.strip()) for x in option_ids.split(",")]
    return json.dumps(await tg.vote_poll(cid, message_id, ids), ensure_ascii=False)


# ==================== Copy / Scheduled / Get messages ====================


@mcp.tool()
async def telegram_copy_message(to_chat_id: str, from_chat_id: str, message_id: int) -> str:
    """Copy a message to another chat without the 'Forwarded from' header."""
    tg = _require_tg()
    to_cid = _parse_id(to_chat_id)
    from_cid = _parse_id(from_chat_id)
    return json.dumps(await tg.copy_message(to_cid, from_cid, message_id), ensure_ascii=False)


@mcp.tool()
async def telegram_send_scheduled_message(chat_id: str, text: str, schedule_date: int) -> str:
    """Send a message that will be delivered at a specified time.
    schedule_date: Unix timestamp of the delivery time (must be in the future)."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.send_scheduled_message(cid, text, schedule_date), ensure_ascii=False)


@mcp.tool()
async def telegram_get_messages(chat_id: str, message_ids: str) -> str:
    """Get specific messages by their IDs.
    message_ids: comma-separated (e.g. "123,456").
    Returns full message info including text, media, views, forwards."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    ids = [int(x.strip()) for x in message_ids.split(",")]
    return json.dumps(await tg.get_messages(cid, ids), ensure_ascii=False)


# ==================== Media ====================


@mcp.tool()
async def telegram_download_media(chat_id: str, message_id: int) -> str:
    """Download media from a specific message and return it as base64.
    Useful for processing images, audio, documents from any chat."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.download_media(cid, message_id), ensure_ascii=False)


# ==================== Location / Contact ====================


@mcp.tool()
async def telegram_send_location(chat_id: str, latitude: float, longitude: float) -> str:
    """Send a location pin to a chat."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.send_location(cid, latitude, longitude), ensure_ascii=False)


@mcp.tool()
async def telegram_send_contact(chat_id: str, phone_number: str, first_name: str, last_name: str = "") -> str:
    """Send a contact card to a chat."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.send_contact(cid, phone_number, first_name, last_name), ensure_ascii=False)


# ==================== Misc ====================


@mcp.tool()
async def telegram_set_typing(chat_id: str, action: str = "typing") -> str:
    """Send a chat action indicator (typing, uploading, recording, etc.).
    action: typing, upload_photo, upload_video, upload_document, record_video, record_audio, choose_sticker, cancel."""
    tg = _require_tg()
    cid = _parse_id(chat_id)
    return json.dumps(await tg.set_typing(cid, action), ensure_ascii=False)
