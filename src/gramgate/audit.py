"""Action audit log — one JSON line per action, never message text.

Answers "what did the agent do on my behalf": which client, which action,
which chat, how big, did it succeed. Message content is deliberately NOT
recorded — Telegram already keeps it. Enabled by GRAMGATE_AUDIT_LOG=<path>.
"""

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_log = logging.getLogger("gramgate.audit")
_log.propagate = False  # never duplicate into the service log
_enabled = False

# Request/tool argument names that identify the target of an action.
TARGET_KEYS = ("chat_id", "recipient", "to_chat_id", "chat_ids", "link", "user_id", "user_ids")
# Argument names whose length is worth recording (content itself is not).
SIZE_KEYS = ("text", "caption", "question")


def setup(path: str) -> bool:
    """Open the audit file. Returns False (and stays disabled) if it cannot be opened."""
    global _enabled
    if not path:
        return False
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # WatchedFileHandler reopens the file after logrotate moves it.
        handler = logging.handlers.WatchedFileHandler(str(p), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        _log.handlers.clear()
        _log.addHandler(handler)
        _log.setLevel(logging.INFO)
        _enabled = True
        return True
    except OSError as e:
        logging.getLogger("gramgate").warning("Audit log disabled — cannot open %s: %s", path, e)
        _enabled = False
        return False


def enabled() -> bool:
    return _enabled


def target_of(args: dict) -> Optional[Any]:
    for key in TARGET_KEYS:
        value = args.get(key)
        if value not in (None, "", []):
            return value
    return None


def size_of(args: dict) -> Optional[int]:
    for key in SIZE_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value:
            return len(value)
    return None


def record(
    source: str,
    action: str,
    *,
    caller: Optional[str] = None,
    target: Any = None,
    size: Optional[int] = None,
    status: Any = "ok",
    error: Optional[str] = None,
    ms: Optional[float] = None,
) -> None:
    """Append one entry. source: rest | mcp | bridge. Never raises."""
    if not _enabled:
        return
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "src": source,
        "action": action,
    }
    if caller:
        entry["caller"] = str(caller)[:80]
    if target is not None:
        entry["target"] = str(target)[:120]
    if size is not None:
        entry["size"] = int(size)
    entry["status"] = status if isinstance(status, int) else str(status)
    if error:
        entry["error"] = str(error)[:200]
    if ms is not None:
        entry["ms"] = int(ms)
    try:
        _log.info(json.dumps(entry, ensure_ascii=False))
    except Exception:  # noqa: BLE001 — auditing must never break the action itself
        pass
