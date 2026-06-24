from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

INBOX_VERSION = 1
MAX_MESSAGES = 300


def default_inbox_path(shell_root: Path) -> Path:
    return shell_root / "data" / "discord_inbox.json"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def empty_inbox() -> dict[str, Any]:
    return {
        "version": INBOX_VERSION,
        "updated_at": utc_now_iso(),
        "messages": [],
    }


def load_inbox(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_inbox()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return empty_inbox()
    if not isinstance(data, dict):
        return empty_inbox()
    messages = data.get("messages")
    if not isinstance(messages, list):
        messages = []
    data["messages"] = [message for message in messages if isinstance(message, dict)]
    data.setdefault("version", INBOX_VERSION)
    data.setdefault("updated_at", utc_now_iso())
    return data


def save_inbox(path: Path, inbox: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    inbox["version"] = INBOX_VERSION
    inbox["updated_at"] = utc_now_iso()
    path.write_text(json.dumps(inbox, ensure_ascii=False, indent=2), encoding="utf-8")


def append_message(path: Path, message: dict[str, Any]) -> bool:
    inbox = load_inbox(path)
    messages = inbox["messages"]
    message_id = str(message.get("id", "")).strip()
    if not message_id:
        return False
    if any(str(existing.get("id", "")) == message_id for existing in messages):
        return False

    stored = {
        "id": message_id,
        "channel_id": str(message.get("channel_id", "")),
        "channel_name": str(message.get("channel_name", "")),
        "guild_id": str(message.get("guild_id", "")),
        "guild_name": str(message.get("guild_name", "")),
        "author_id": str(message.get("author_id", "")),
        "author_name": str(message.get("author_name", "")),
        "content": str(message.get("content", ""))[:1800],
        "jump_url": str(message.get("jump_url", "")),
        "created_at": str(message.get("created_at", "")) or utc_now_iso(),
        "received_at": utc_now_iso(),
        "handled": bool(message.get("handled", False)),
    }
    messages.append(stored)
    inbox["messages"] = messages[-MAX_MESSAGES:]
    save_inbox(path, inbox)
    return True


def list_recent_messages(path: Path, limit: int = 20, include_handled: bool = True) -> list[dict[str, Any]]:
    inbox = load_inbox(path)
    messages = inbox["messages"]
    if not include_handled:
        messages = [message for message in messages if not message.get("handled")]
    return list(reversed(messages[-limit:]))


def mark_handled(path: Path, message_id: str, handled: bool = True) -> bool:
    inbox = load_inbox(path)
    changed = False
    for message in inbox["messages"]:
        if str(message.get("id", "")) == str(message_id):
            message["handled"] = handled
            changed = True
            break
    if changed:
        save_inbox(path, inbox)
    return changed


def format_context(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in reversed(messages):
        author = str(message.get("author_name") or "Unknown").strip()
        content = " ".join(str(message.get("content") or "").split())
        created_at = str(message.get("created_at") or "").strip()
        if content:
            lines.append(f"{created_at} {author}: {content}")
    return "\n".join(lines)
