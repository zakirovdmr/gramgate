"""Rate limiter — safety net to protect the Telegram account from flood bans.

Uses a sliding window counter per bucket (action type + optional chat_id).
All limits are configurable and can be disabled by setting to 0.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class RateLimit:
    max_requests: int
    window_seconds: float


@dataclass
class _Bucket:
    timestamps: list[float] = field(default_factory=list)

    def count_in_window(self, window: float) -> int:
        now = time.monotonic()
        cutoff = now - window
        self.timestamps = [t for t in self.timestamps if t > cutoff]
        return len(self.timestamps)

    def record(self):
        self.timestamps.append(time.monotonic())


class RateLimiter:
    """Sliding window rate limiter with per-action and per-chat tracking."""

    def __init__(
        self,
        send_per_chat: RateLimit | None = None,
        send_global: RateLimit | None = None,
        join_leave: RateLimit | None = None,
        api_global: RateLimit | None = None,
    ):
        self.limits = {
            "send_per_chat": send_per_chat or RateLimit(20, 60),
            "send_global": send_global or RateLimit(30, 60),
            "join_leave": join_leave or RateLimit(5, 3600),
            "api_global": api_global or RateLimit(25, 1),
        }
        self._buckets: dict[str, _Bucket] = defaultdict(_Bucket)

    def check(self, action: str, key: str = "") -> tuple[bool, float]:
        """Check if action is allowed.

        Returns (allowed, retry_after_seconds).
        """
        limit = self.limits.get(action)
        if not limit or limit.max_requests <= 0:
            return True, 0

        bucket_key = f"{action}:{key}" if key else action
        bucket = self._buckets[bucket_key]
        count = bucket.count_in_window(limit.window_seconds)

        if count >= limit.max_requests:
            if bucket.timestamps:
                oldest_in_window = bucket.timestamps[0]
                retry_after = (oldest_in_window + limit.window_seconds) - time.monotonic()
                return False, max(retry_after, 0.1)
            return False, 1.0

        bucket.record()
        return True, 0

    def check_api(self) -> tuple[bool, float]:
        """Check global API rate limit."""
        return self.check("api_global")

    def check_send(self, chat_id: str = "") -> tuple[bool, float]:
        """Check send rate limits (per-chat + global)."""
        ok, retry = self.check("send_per_chat", str(chat_id))
        if not ok:
            return False, retry
        return self.check("send_global")

    def check_join(self) -> tuple[bool, float]:
        """Check join/leave rate limit."""
        return self.check("join_leave")


# Action categories for URL-based routing
SEND_ACTIONS = {
    "/api/message/send",
    "/api/message/edit",
    "/api/message/forward",
    "/api/message/copy",
    "/api/message/scheduled",
    "/api/poll/send",
    "/api/send/location",
    "/api/send/contact",
}

JOIN_ACTIONS = {
    "/api/chat/join",
    "/api/chat/leave",
    "/api/chat/create/group",
    "/api/chat/create/channel",
    "/api/chat/create/supergroup",
}
