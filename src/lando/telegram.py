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

from .openclaw import OpenClawClient
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

    def __init__(self, config, openclaw: OpenClawClient):
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

        # Private messages (not from self)
        @self.client.on_message(filters.private & ~filters.me)
        async def on_private(client: Client, message: Message):
            await self._handle(message)

        # Group messages — respond when mentioned, always store
        @self.client.on_message(filters.group & ~filters.me)
        async def on_group(client: Client, message: Message):
            self._store_message(message)
            if message.mentioned:
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
        async for chat in self.client.search_global(query, limit=limit):
            result.append({
                "id": chat.id,
                "title": getattr(chat, "title", None) or getattr(chat, "first_name", "?"),
                "username": chat.username,
                "type": str(chat.type),
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

    async def stop(self):
        if self.client and self._running:
            await self.client.stop()
            self._running = False
            log.info("Lando stopped")
