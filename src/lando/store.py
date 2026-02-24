"""In-memory message store for channel/group feed."""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StoredMessage:
    message_id: int
    chat_id: int
    chat_title: str
    user_id: Optional[int]
    username: Optional[str]
    first_name: Optional[str]
    text: str
    date: str
    has_media: bool
    media_type: Optional[str]  # "photo", "video", "document", "voice", etc.
    reply_to: Optional[int]
    views: Optional[int]
    timestamp: float = field(default_factory=time.time)


class MessageStore:
    """Stores recent messages from channels and groups."""

    def __init__(self, max_per_chat: int = 200, max_total: int = 5000):
        self.max_per_chat = max_per_chat
        self.max_total = max_total
        self._by_chat: dict[int, deque[StoredMessage]] = {}
        self._global: deque[StoredMessage] = deque(maxlen=max_total)
        self._last_read: dict[str, float] = {}  # consumer_id -> timestamp

    def add(self, msg: StoredMessage):
        """Add a message to the store."""
        if msg.chat_id not in self._by_chat:
            self._by_chat[msg.chat_id] = deque(maxlen=self.max_per_chat)
        self._by_chat[msg.chat_id].append(msg)
        self._global.append(msg)

    def get_chat_feed(self, chat_id: int, limit: int = 50) -> list[StoredMessage]:
        """Get recent messages from a specific chat."""
        msgs = self._by_chat.get(chat_id, deque())
        return list(msgs)[-limit:]

    def get_new_messages(self, consumer_id: str = "default", limit: int = 100) -> list[StoredMessage]:
        """Get messages since last read for this consumer."""
        last = self._last_read.get(consumer_id, 0)
        new = [m for m in self._global if m.timestamp > last][-limit:]
        if new:
            self._last_read[consumer_id] = new[-1].timestamp
        return new

    def get_all_chats(self) -> dict[int, dict]:
        """Get summary of all stored chats."""
        result = {}
        for chat_id, msgs in self._by_chat.items():
            if msgs:
                last = msgs[-1]
                result[chat_id] = {
                    "chat_id": chat_id,
                    "chat_title": last.chat_title,
                    "message_count": len(msgs),
                    "last_text": last.text[:100] if last.text else "",
                    "last_date": last.date,
                }
        return result

    def clear(self, chat_id: int = None):
        if chat_id:
            self._by_chat.pop(chat_id, None)
        else:
            self._by_chat.clear()
            self._global.clear()
