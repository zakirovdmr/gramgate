"""Telegram MTProto transport — Pyrogram client that pipes messages to OpenClaw."""

import asyncio
import base64
import logging
import re
import tempfile
from pathlib import Path
from typing import Optional

from pyrogram import Client, filters
from pyrogram.enums import ChatAction, ParseMode
from pyrogram.types import Message

from .store import MessageStore, StoredMessage

log = logging.getLogger("lando.telegram")

MAX_MESSAGE_LENGTH = 4096


def _convert_markdown_for_telegram(text: str) -> str:
    """Convert GitHub-style Markdown headers to Telegram-compatible bold."""
    text = re.sub(r"^#{1,6}\s+(.+)$", r"**\1**", text, flags=re.MULTILINE)
    text = re.sub(r"^---+$", "\u2501" * 10, text, flags=re.MULTILINE)
    return text


def _split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split long text into chunks respecting Telegram's 4096-char limit."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        pos = text.rfind("\n", 0, max_length)
        if pos == -1 or pos < max_length // 2:
            pos = text.rfind(" ", 0, max_length)
        if pos == -1 or pos < max_length // 2:
            pos = max_length
        chunks.append(text[:pos])
        text = text[pos:].lstrip()
    return chunks


def _media_type(message: Message) -> Optional[str]:
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.video_note:
        return "video_note"
    if message.animation:
        return "animation"
    if message.voice:
        return "voice"
    if message.audio:
        return "audio"
    if message.document:
        return "document"
    if message.sticker:
        return "sticker"
    return None


class LandoTelegram:
    """Pyrogram MTProto client that forwards messages to OpenClaw
    and exposes full account capabilities via MCP tools."""

    def __init__(self, config, openclaw=None):
        self.config = config
        self.openclaw = openclaw
        self.client: Optional[Client] = None
        self.store = MessageStore()
        self._running = False

    async def start(self):
        if self._running:
            return

        session_dir = Path(self.config.telegram_session_dir)
        session_dir.mkdir(parents=True, exist_ok=True)

        self.client = Client(
            name="lando",
            api_id=self.config.telegram_api_id,
            api_hash=self.config.telegram_api_hash,
            phone_number=self.config.telegram_phone,
            workdir=str(session_dir),
        )

        # Chat IDs to skip (bots we test via API, not OpenClaw bridge)
        self._skip_chat_ids: set[int] = set()

        # Private messages (not from self)
        @self.client.on_message(filters.private & ~filters.me)
        async def on_private(client: Client, message: Message):
            self._store_message(message)
            if message.chat.id in self._skip_chat_ids:
                return  # skip — this chat is used for direct API testing
            if self.openclaw:
                await self._handle(message)

        # Group messages — respond when mentioned, always store
        @self.client.on_message(filters.group & ~filters.me)
        async def on_group(client: Client, message: Message):
            self._store_message(message)
            if message.mentioned and self.openclaw:
                await self._handle(message, is_group=True)

        # Channel messages — always store
        @self.client.on_message(filters.channel)
        async def on_channel(client: Client, message: Message):
            self._store_message(message)

        await self.client.start()
        self._running = True

        me = await self.client.get_me()
        log.info("Lando started as @%s (id=%s)", me.username, me.id)

    def _store_message(self, message: Message):
        """Store message in the feed."""
        try:
            self.store.add(StoredMessage(
                message_id=message.id,
                chat_id=message.chat.id,
                chat_title=getattr(message.chat, "title", None)
                    or getattr(message.chat, "first_name", str(message.chat.id)),
                user_id=message.from_user.id if message.from_user else None,
                username=message.from_user.username if message.from_user else None,
                first_name=message.from_user.first_name if message.from_user else None,
                text=message.text or message.caption or "",
                date=message.date.isoformat() if message.date else "",
                has_media=bool(_media_type(message)),
                media_type=_media_type(message),
                reply_to=message.reply_to_message_id,
                views=message.views,
            ))
        except Exception as e:
            log.debug("Failed to store message: %s", e)

    # ==================== Message bridge (private/mentioned → OpenClaw) ====================

    async def _handle(self, message: Message, is_group: bool = False):
        """Handle incoming message: download media, forward to OpenClaw, reply."""
        text = message.text or message.caption or ""
        images: list[dict] = []
        files: list[dict] = []

        try:
            await self._extract_media(message, text, images, files)
        except Exception as e:
            log.error("Failed to download media: %s", e)

        if not text and (images or files):
            text = "[User sent a photo]" if images else "[User sent a file]"

        if not text and not images and not files:
            return

        chat_id = message.chat.id
        session_key = f"lando:{chat_id}"
        typing_task: Optional[asyncio.Task] = None

        try:
            try:
                await self.client.send_reaction(chat_id, message_id=message.id, emoji="\U0001f440")
            except Exception:
                pass

            typing_task = asyncio.create_task(self._typing_loop(chat_id))

            response = await self.openclaw.send(
                text, session_key, images=images or None, files=files or None,
            )

            if response:
                await self._send_reply(chat_id, response, reply_to=message.id)
                try:
                    await self.client.send_reaction(chat_id, message_id=message.id, emoji=None)
                except Exception:
                    pass

        except Exception as e:
            log.error("Error handling message from %s: %s", chat_id, e)
            try:
                await self.client.send_reaction(chat_id, message_id=message.id, emoji="\U0001f622")
            except Exception:
                pass
            # Don't send error messages to bots — prevents reply loops
            is_bot = getattr(message.chat, "is_bot", False) or (
                message.from_user and getattr(message.from_user, "is_bot", False)
            )
            if not is_bot:
                await self._send_reply(chat_id, f"Error: {str(e)[:200]}", reply_to=message.id)
        finally:
            if typing_task:
                typing_task.cancel()
            try:
                await self.client.read_chat_history(chat_id, max_id=message.id)
            except Exception:
                pass

    async def _extract_media(
        self, message: Message, text: str, images: list[dict], files: list[dict]
    ):
        """Download media from message and populate images/files lists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            if message.photo:
                path = Path(tmp_dir) / f"photo_{message.id}.jpg"
                await message.download(str(path))
                data = base64.b64encode(path.read_bytes()).decode()
                images.append({"data": data, "media_type": "image/jpeg"})

            elif message.sticker and not message.sticker.is_animated:
                path = Path(tmp_dir) / f"sticker_{message.id}.webp"
                await message.download(str(path))
                data = base64.b64encode(path.read_bytes()).decode()
                images.append({"data": data, "media_type": "image/webp"})

            elif message.voice or message.audio:
                voice = message.voice or message.audio
                ext = ".ogg" if message.voice else ".mp3"
                path = Path(tmp_dir) / f"audio_{message.id}{ext}"
                await message.download(str(path))
                data = base64.b64encode(path.read_bytes()).decode()
                mime = voice.mime_type or ("audio/ogg" if message.voice else "audio/mpeg")
                files.append({"data": data, "media_type": mime, "filename": path.name})

            elif message.document:
                doc = message.document
                fname = doc.file_name or f"doc_{message.id}"
                path = Path(tmp_dir) / fname
                await message.download(str(path))
                data = base64.b64encode(path.read_bytes()).decode()
                mime = doc.mime_type or "application/octet-stream"
                ext = Path(fname).suffix.lower()
                if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
                    images.append({"data": data, "media_type": mime})
                else:
                    files.append({"data": data, "media_type": mime, "filename": fname})

    async def _typing_loop(self, chat_id: int):
        try:
            while True:
                try:
                    await self.client.send_chat_action(chat_id, ChatAction.TYPING)
                except Exception:
                    return
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            return

    async def _send_reply(self, chat_id: int, text: str, reply_to: int = None):
        text = _convert_markdown_for_telegram(text)
        chunks = _split_message(text)
        for i, chunk in enumerate(chunks):
            rid = reply_to if i == 0 else None
            try:
                await self.client.send_message(
                    chat_id, chunk, reply_to_message_id=rid, parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                await self.client.send_message(chat_id, chunk, reply_to_message_id=rid)

    # ==================== Account actions (called from MCP tools) ====================

    async def get_me(self) -> dict:
        me = await self.client.get_me()
        return {"id": me.id, "username": me.username, "first_name": me.first_name, "phone": me.phone_number}

    async def get_dialogs(self, limit: int = 30) -> list[dict]:
        result = []
        async for d in self.client.get_dialogs(limit=limit):
            result.append({
                "chat_id": d.chat.id,
                "title": getattr(d.chat, "title", None) or getattr(d.chat, "first_name", "?"),
                "username": d.chat.username,
                "type": str(d.chat.type),
                "unread": d.unread_messages_count,
                "last_message": (d.top_message.text or "")[:100] if d.top_message else None,
            })
        return result

    async def get_chat_history(self, chat_id, limit: int = 30) -> list[dict]:
        result = []
        async for msg in self.client.get_chat_history(chat_id, limit=limit):
            result.append({
                "id": msg.id,
                "from": msg.from_user.username if msg.from_user else None,
                "text": msg.text or msg.caption or "",
                "date": msg.date.isoformat() if msg.date else None,
                "has_media": bool(_media_type(msg)),
                "media_type": _media_type(msg),
            })
        return result

    async def get_chat_info(self, chat_id) -> dict:
        if isinstance(chat_id, str) and chat_id.startswith("@"):
            chat_id = chat_id[1:]
        chat = await self.client.get_chat(chat_id)
        return {
            "id": chat.id,
            "title": getattr(chat, "title", None) or getattr(chat, "first_name", "?"),
            "username": chat.username,
            "type": str(chat.type),
            "members_count": getattr(chat, "members_count", None),
            "description": getattr(chat, "description", None),
        }

    async def get_chat_history_rich(self, chat_id, limit: int = 30) -> list[dict]:
        """Chat history with inline button data included."""
        result = []
        async for msg in self.client.get_chat_history(chat_id, limit=limit):
            entry = {
                "id": msg.id,
                "from": msg.from_user.username if msg.from_user else None,
                "text": msg.text or msg.caption or "",
                "date": msg.date.isoformat() if msg.date else None,
                "has_media": bool(_media_type(msg)),
                "media_type": _media_type(msg),
            }
            # Extract inline keyboard buttons
            if msg.reply_markup and hasattr(msg.reply_markup, "inline_keyboard"):
                buttons = []
                for row in msg.reply_markup.inline_keyboard:
                    for btn in row:
                        buttons.append({
                            "text": btn.text,
                            "callback_data": btn.callback_data,
                            "url": btn.url,
                        })
                entry["buttons"] = buttons
            result.append(entry)
        return result

    async def click_inline_button(self, chat_id, message_id: int, callback_data: str) -> dict:
        """Click an inline button by its callback_data."""
        try:
            await self.client.request_callback_answer(chat_id, message_id, callback_data)
            return {"ok": True, "chat_id": chat_id, "message_id": message_id, "callback_data": callback_data}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def send_message_to(self, recipient, text: str) -> dict:
        if isinstance(recipient, str) and recipient.startswith("@"):
            recipient = recipient[1:]
        text = _convert_markdown_for_telegram(text)
        chunks = _split_message(text)
        last = None
        for chunk in chunks:
            last = await self.client.send_message(recipient, chunk, parse_mode=ParseMode.MARKDOWN)
        return {"message_id": last.id, "chat_id": last.chat.id}

    async def join_chat(self, link: str) -> dict:
        if link.startswith("@"):
            link = link[1:]
        elif link.startswith("https://t.me/"):
            link = link.replace("https://t.me/", "")
        elif link.startswith("t.me/"):
            link = link.replace("t.me/", "")
        chat = await self.client.join_chat(link)
        return {"chat_id": chat.id, "title": chat.title, "type": str(chat.type)}

    async def leave_chat(self, chat_id) -> dict:
        await self.client.leave_chat(chat_id)
        return {"left": True}

    async def search_messages(self, chat_id, query: str, limit: int = 20) -> list[dict]:
        result = []
        async for msg in self.client.search_messages(chat_id, query, limit=limit):
            result.append({
                "id": msg.id,
                "text": msg.text or msg.caption or "",
                "date": msg.date.isoformat() if msg.date else None,
                "from": msg.from_user.username if msg.from_user else None,
            })
        return result

    async def search_global(self, query: str, limit: int = 10) -> list[dict]:
        result = []
        seen_chats: set[int] = set()
        async for msg in self.client.search_global(query, limit=limit):
            chat = msg.chat
            if chat.id in seen_chats:
                continue
            seen_chats.add(chat.id)
            result.append({
                "chat_id": chat.id,
                "title": getattr(chat, "title", None) or getattr(chat, "first_name", "?"),
                "username": chat.username,
                "type": str(chat.type),
                "message_id": msg.id,
                "text": (msg.text or msg.caption or "")[:200],
                "date": msg.date.isoformat() if msg.date else None,
            })
        return result

    async def forward_messages(self, to_chat_id, from_chat_id, message_ids: list[int]) -> dict:
        msgs = await self.client.forward_messages(to_chat_id, from_chat_id, message_ids)
        count = len(msgs) if isinstance(msgs, list) else 1
        return {"forwarded": count}

    async def send_reaction(self, chat_id, message_id: int, emoji: str) -> dict:
        await self.client.send_reaction(chat_id, message_id=message_id, emoji=emoji)
        return {"ok": True}

    async def get_chat_members(self, chat_id, limit: int = 50) -> list[dict]:
        result = []
        async for m in self.client.get_chat_members(chat_id, limit=limit):
            result.append({
                "user_id": m.user.id,
                "username": m.user.username,
                "first_name": m.user.first_name,
                "status": str(m.status),
            })
        return result

    async def get_contacts(self) -> list[dict]:
        contacts = await self.client.get_contacts()
        return [{"id": c.id, "username": c.username, "first_name": c.first_name, "phone": c.phone_number} for c in contacts]

    async def read_chat(self, chat_id) -> dict:
        await self.client.read_chat_history(chat_id)
        return {"ok": True}

    async def send_photo(self, chat_id, photo_path: str, caption: str = "") -> dict:
        msg = await self.client.send_photo(chat_id, photo_path, caption=caption)
        return {"message_id": msg.id}

    async def send_file(self, chat_id, file_path: str, caption: str = "") -> dict:
        msg = await self.client.send_document(chat_id, file_path, caption=caption)
        return {"message_id": msg.id}

    # ==================== Edit / Delete messages ====================

    async def edit_message(self, chat_id, message_id: int, text: str) -> dict:
        text = _convert_markdown_for_telegram(text)
        msg = await self.client.edit_message_text(chat_id, message_id, text, parse_mode=ParseMode.MARKDOWN)
        return {"message_id": msg.id, "chat_id": msg.chat.id}

    async def delete_messages(self, chat_id, message_ids: list[int]) -> dict:
        await self.client.delete_messages(chat_id, message_ids)
        return {"deleted": len(message_ids)}

    # ==================== Pin / Unpin ====================

    async def pin_message(self, chat_id, message_id: int, both_sides: bool = True, disable_notification: bool = False) -> dict:
        await self.client.pin_chat_message(chat_id, message_id, both_sides=both_sides, disable_notification=disable_notification)
        return {"pinned": True, "message_id": message_id}

    async def unpin_message(self, chat_id, message_id: int = 0) -> dict:
        await self.client.unpin_chat_message(chat_id, message_id or None)
        return {"unpinned": True}

    async def unpin_all_messages(self, chat_id) -> dict:
        await self.client.unpin_all_chat_messages(chat_id)
        return {"unpinned_all": True}

    # ==================== Chat management ====================

    async def create_group(self, title: str, users: list) -> dict:
        chat = await self.client.create_group(title, users)
        return {"chat_id": chat.id, "title": chat.title, "type": str(chat.type)}

    async def create_channel(self, title: str, description: str = "") -> dict:
        chat = await self.client.create_channel(title, description=description)
        return {"chat_id": chat.id, "title": chat.title, "type": str(chat.type)}

    async def create_supergroup(self, title: str, description: str = "") -> dict:
        chat = await self.client.create_supergroup(title, description=description)
        return {"chat_id": chat.id, "title": chat.title, "type": str(chat.type)}

    async def set_chat_title(self, chat_id, title: str) -> dict:
        await self.client.set_chat_title(chat_id, title)
        return {"ok": True, "title": title}

    async def set_chat_description(self, chat_id, description: str) -> dict:
        await self.client.set_chat_description(chat_id, description)
        return {"ok": True}

    async def set_chat_photo(self, chat_id, photo_path: str) -> dict:
        await self.client.set_chat_photo(chat_id, photo=photo_path)
        return {"ok": True}

    async def delete_chat_photo(self, chat_id) -> dict:
        await self.client.delete_chat_photo(chat_id)
        return {"ok": True}

    async def archive_chats(self, chat_ids: list) -> dict:
        await self.client.archive_chats(chat_ids)
        return {"archived": len(chat_ids)}

    async def unarchive_chats(self, chat_ids: list) -> dict:
        await self.client.unarchive_chats(chat_ids)
        return {"unarchived": len(chat_ids)}

    # ==================== User / Member management ====================

    async def ban_chat_member(self, chat_id, user_id: int) -> dict:
        await self.client.ban_chat_member(chat_id, user_id)
        return {"banned": True, "user_id": user_id}

    async def unban_chat_member(self, chat_id, user_id: int) -> dict:
        await self.client.unban_chat_member(chat_id, user_id)
        return {"unbanned": True, "user_id": user_id}

    async def restrict_chat_member(self, chat_id, user_id: int, permissions: dict) -> dict:
        from pyrogram.types import ChatPermissions
        perms = ChatPermissions(**permissions)
        await self.client.restrict_chat_member(chat_id, user_id, perms)
        return {"restricted": True, "user_id": user_id}

    async def promote_chat_member(self, chat_id, user_id: int, privileges: dict) -> dict:
        from pyrogram.types import ChatPrivileges
        privs = ChatPrivileges(**privileges)
        await self.client.promote_chat_member(chat_id, user_id, privs)
        return {"promoted": True, "user_id": user_id}

    async def add_chat_members(self, chat_id, user_ids: list) -> dict:
        await self.client.add_chat_members(chat_id, user_ids)
        return {"added": len(user_ids)}

    # ==================== User actions ====================

    async def block_user(self, user_id: int) -> dict:
        await self.client.block_user(user_id)
        return {"blocked": True, "user_id": user_id}

    async def unblock_user(self, user_id: int) -> dict:
        await self.client.unblock_user(user_id)
        return {"unblocked": True, "user_id": user_id}

    async def get_users(self, user_ids: list) -> list[dict]:
        users = await self.client.get_users(user_ids)
        if not isinstance(users, list):
            users = [users]
        return [
            {
                "id": u.id,
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "phone": u.phone_number,
                "is_bot": u.is_bot,
                "is_premium": getattr(u, "is_premium", None),
                "status": str(u.status) if u.status else None,
                "last_online": u.last_online_date.isoformat() if getattr(u, "last_online_date", None) else None,
            }
            for u in users
        ]

    async def get_profile_photos(self, chat_id, limit: int = 10) -> list[dict]:
        photos = []
        async for photo in self.client.get_chat_photos(chat_id, limit=limit):
            photos.append({
                "file_id": photo.file_id,
                "date": photo.date.isoformat() if photo.date else None,
                "file_size": photo.file_size,
            })
        return photos

    # ==================== Polls ====================

    async def send_poll(self, chat_id, question: str, options: list[str], is_anonymous: bool = True, poll_type: str = "regular", allows_multiple_answers: bool = False) -> dict:
        msg = await self.client.send_poll(
            chat_id, question=question, options=options,
            is_anonymous=is_anonymous, type=poll_type,
            allows_multiple_answers=allows_multiple_answers,
        )
        return {"message_id": msg.id, "chat_id": msg.chat.id}

    async def stop_poll(self, chat_id, message_id: int) -> dict:
        poll = await self.client.stop_poll(chat_id, message_id)
        results = []
        for opt in poll.options:
            results.append({"text": opt.text, "voter_count": opt.voter_count})
        return {"results": results, "total_voters": poll.total_voter_count}

    async def vote_poll(self, chat_id, message_id: int, option_ids: list[int]) -> dict:
        await self.client.vote_poll(chat_id, message_id, option_ids)
        return {"voted": True}

    # ==================== Copy messages ====================

    async def copy_message(self, to_chat_id, from_chat_id, message_id: int) -> dict:
        msg = await self.client.copy_message(to_chat_id, from_chat_id, message_id)
        return {"message_id": msg.id}

    # ==================== Scheduled messages ====================

    async def send_scheduled_message(self, chat_id, text: str, schedule_date) -> dict:
        from datetime import datetime
        if isinstance(schedule_date, (int, float)):
            schedule_date = datetime.fromtimestamp(schedule_date)
        text = _convert_markdown_for_telegram(text)
        chunks = _split_message(text)
        last = None
        for chunk in chunks:
            last = await self.client.send_message(
                chat_id, chunk, parse_mode=ParseMode.MARKDOWN,
                schedule_date=schedule_date,
            )
        return {"message_id": last.id, "chat_id": last.chat.id, "scheduled": True}

    # ==================== Media download ====================

    async def download_media(self, chat_id, message_id: int) -> dict:
        """Download media from a specific message, return base64."""
        msgs = [m async for m in self.client.get_chat_history(chat_id, limit=1, offset_id=message_id + 1)]
        if not msgs:
            return {"error": "message not found"}
        message = msgs[0]
        if message.id != message_id:
            return {"error": "message not found"}
        mtype = _media_type(message)
        if not mtype:
            return {"error": "no media in message"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / f"media_{message_id}"
            await self.client.download_media(message, str(path))
            actual = list(Path(tmp_dir).glob("media_*"))
            if not actual:
                return {"error": "download failed"}
            data = base64.b64encode(actual[0].read_bytes()).decode()
            return {
                "data": data,
                "media_type": mtype,
                "filename": actual[0].name,
                "size": actual[0].stat().st_size,
            }

    # ==================== Location / Contact ====================

    async def send_location(self, chat_id, latitude: float, longitude: float) -> dict:
        msg = await self.client.send_location(chat_id, latitude=latitude, longitude=longitude)
        return {"message_id": msg.id}

    async def send_contact(self, chat_id, phone_number: str, first_name: str, last_name: str = "") -> dict:
        msg = await self.client.send_contact(chat_id, phone_number=phone_number, first_name=first_name, last_name=last_name)
        return {"message_id": msg.id}

    # ==================== Invite links ====================

    async def export_chat_invite_link(self, chat_id) -> dict:
        link = await self.client.export_chat_invite_link(chat_id)
        return {"invite_link": link}

    async def create_chat_invite_link(self, chat_id, name: str = "", expire_date=None, member_limit: int = 0) -> dict:
        from datetime import datetime
        ed = None
        if expire_date:
            ed = datetime.fromtimestamp(expire_date) if isinstance(expire_date, (int, float)) else expire_date
        link = await self.client.create_chat_invite_link(
            chat_id, name=name or None,
            expire_date=ed, member_limit=member_limit or None,
        )
        return {"invite_link": link.invite_link, "name": link.name, "is_primary": link.is_primary}

    # ==================== Get single message ====================

    async def get_messages(self, chat_id, message_ids: list[int]) -> list[dict]:
        msgs = await self.client.get_messages(chat_id, message_ids)
        if not isinstance(msgs, list):
            msgs = [msgs]
        return [
            {
                "id": m.id,
                "from": m.from_user.username if m.from_user else None,
                "text": m.text or m.caption or "",
                "date": m.date.isoformat() if m.date else None,
                "has_media": bool(_media_type(m)),
                "media_type": _media_type(m),
                "views": m.views,
                "forwards": m.forwards,
                "reply_to": m.reply_to_message_id,
            }
            for m in msgs
            if m and not m.empty
        ]

    # ==================== Misc ====================

    async def set_typing(self, chat_id, action: str = "typing") -> dict:
        actions_map = {
            "typing": ChatAction.TYPING,
            "upload_photo": ChatAction.UPLOAD_PHOTO,
            "upload_video": ChatAction.UPLOAD_VIDEO,
            "upload_document": ChatAction.UPLOAD_DOCUMENT,
            "record_video": ChatAction.RECORD_VIDEO,
            "record_audio": ChatAction.RECORD_AUDIO,
            "choose_sticker": ChatAction.CHOOSE_STICKER,
            "cancel": ChatAction.CANCEL,
        }
        act = actions_map.get(action, ChatAction.TYPING)
        await self.client.send_chat_action(chat_id, act)
        return {"ok": True, "action": action}

    async def stop(self):
        if self.client and self._running:
            await self.client.stop()
            self._running = False
            log.info("Lando stopped")
