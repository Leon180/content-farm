"""Telegram Bot API client — raw httpx, no extra dependency."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LENGTH = 4096


class TelegramBot:
    """Lightweight async Telegram bot using httpx."""

    def __init__(self, token: str, chat_id: str) -> None:
        self._chat_id = chat_id
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{token}",
            timeout=60.0,
        )

    async def send_message(self, text: str) -> int:
        """Send a text message. Auto-splits if >4096 chars.

        Returns the message_id of the last sent message.
        """
        chunks = _split_text(text, _MAX_MESSAGE_LENGTH)
        message_id = 0
        for chunk in chunks:
            response = await self._client.post(
                "/sendMessage",
                json={"chat_id": self._chat_id, "text": chunk},
            )
            response.raise_for_status()
            message_id = response.json()["result"]["message_id"]
        logger.info("Telegram message sent (%d chars, %d chunks)", len(text), len(chunks))
        return message_id

    async def send_photo(
        self,
        photo: str | Path,
        caption: str = "",
    ) -> int:
        """Send a single photo. Accepts file path or URL.

        Returns the message_id.
        """
        data: dict[str, object] = {"chat_id": self._chat_id}
        if caption:
            data["caption"] = caption

        if isinstance(photo, Path) or (isinstance(photo, str) and not photo.startswith("http")):
            photo_path = Path(photo)
            with open(photo_path, "rb") as f:
                response = await self._client.post(
                    "/sendPhoto",
                    data=data,  # type: ignore[arg-type]
                    files={"photo": (photo_path.name, f, "image/jpeg")},
                )
        else:
            data["photo"] = photo
            response = await self._client.post("/sendPhoto", json=data)

        response.raise_for_status()
        message_id: int = response.json()["result"]["message_id"]
        logger.info("Telegram photo sent: %s", photo)
        return message_id

    async def send_photos(
        self,
        items: list[tuple[str, str]],
    ) -> None:
        """Send multiple photos as a media group.

        Each item is (url, caption). Max 10 per group.
        """
        for batch_start in range(0, len(items), 10):
            batch = items[batch_start : batch_start + 10]
            media = []
            for idx, (url, caption) in enumerate(batch):
                entry: dict[str, str] = {"type": "photo", "media": url}
                if caption:
                    entry["caption"] = caption
                media.append(entry)

            response = await self._client.post(
                "/sendMediaGroup",
                json={
                    "chat_id": self._chat_id,
                    "media": media,
                },
            )
            response.raise_for_status()
        logger.info("Telegram media group sent: %d photos", len(items))

    async def wait_for_reply(self, timeout_seconds: int = 1800) -> str:
        """Poll getUpdates until user replies. Returns reply text.

        Raises TimeoutError if no reply within timeout.
        """
        offset = await self._flush_updates()
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            remaining = max(1, int(deadline - time.monotonic()))
            poll_timeout = min(30, remaining)

            response = await self._client.get(
                "/getUpdates",
                params={"offset": offset, "timeout": poll_timeout},
                timeout=poll_timeout + 10,
            )
            response.raise_for_status()
            updates = response.json().get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", ""))
                text = message.get("text", "")

                if chat_id == self._chat_id and text.strip():
                    logger.info("Telegram reply received: %r", text.strip())
                    return text.strip()

        raise TimeoutError(
            f"No Telegram reply within {timeout_seconds}s"
        )

    async def _flush_updates(self) -> int:
        """Flush old updates and return offset for next poll."""
        response = await self._client.get(
            "/getUpdates",
            params={"offset": -1, "timeout": 0},
        )
        response.raise_for_status()
        updates = response.json().get("result", [])
        if updates:
            return updates[-1]["update_id"] + 1
        return 0


def _split_text(text: str, max_length: int) -> list[str]:
    """Split text into chunks of max_length, breaking at newlines."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break
        # Find last newline within limit
        cut = remaining.rfind("\n", 0, max_length)
        if cut <= 0:
            cut = max_length
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    return chunks
