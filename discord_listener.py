from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
SHELL_ROOT = PROJECT_ROOT / "studio_shell"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from studio_shell.discord_inbox import append_message, default_inbox_path


def _split_ids(value: str) -> set[int]:
    ids: set[int] = set()
    for item in value.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError:
            print(f"Ignoring invalid Discord channel id: {item}")
    return ids


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    channel_ids = _split_ids(os.getenv("DISCORD_CHANNEL_IDS", "") or os.getenv("DISCORD_CHANNEL_ID", ""))
    inbox_path = Path(os.getenv("DISCORD_INBOX_PATH", "") or default_inbox_path(SHELL_ROOT))

    if not token:
        raise SystemExit("Missing DISCORD_BOT_TOKEN in .env")
    if not channel_ids:
        raise SystemExit("Missing DISCORD_CHANNEL_ID or DISCORD_CHANNEL_IDS in .env")

    try:
        import discord
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: discord.py. Install with `uv sync` after pyproject.toml is updated."
        ) from exc

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:
        username = client.user.name if client.user else "Discord listener"
        watched = ", ".join(str(channel_id) for channel_id in sorted(channel_ids))
        print(f"{username} is listening to Discord channel(s): {watched}")
        print(f"Inbox file: {inbox_path}")

    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot or message.channel.id not in channel_ids:
            return

        content = (message.content or "").strip()
        if not content and message.attachments:
            content = " ".join(attachment.url for attachment in message.attachments)
        if not content:
            return

        channel_name = getattr(message.channel, "name", "")
        guild = getattr(message, "guild", None)
        saved = append_message(
            inbox_path,
            {
                "id": message.id,
                "channel_id": message.channel.id,
                "channel_name": channel_name,
                "guild_id": getattr(guild, "id", ""),
                "guild_name": getattr(guild, "name", ""),
                "author_id": message.author.id,
                "author_name": message.author.display_name,
                "content": content,
                "jump_url": message.jump_url,
                "created_at": message.created_at.isoformat(timespec="seconds"),
            },
        )
        if saved:
            print(f"Saved Discord message from {message.author.display_name}: {content[:80]}")

    client.run(token)


if __name__ == "__main__":
    main()
