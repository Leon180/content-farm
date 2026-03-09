"""Telegram Bot API client — raw httpx, no extra dependency."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LENGTH = 4096
_MAX_CAPTION_LENGTH = 1024


class TelegramBot:
    """Lightweight async Telegram bot using httpx.

    Supports: text, photos, videos, documents, inline keyboards,
    callback queries, and long-polling for replies.
    """

    def __init__(self, token: str, chat_id: str) -> None:
        self._chat_id = chat_id
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{token}",
            timeout=60.0,
        )

    async def close(self) -> None:
        """Close the underlying httpx client (I-7: prevent connection leak)."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Sending messages
    # ------------------------------------------------------------------

    async def send_message(
        self,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = None,
    ) -> int:
        """Send a text message. Auto-splits if >4096 chars.

        Returns the message_id of the last sent message.
        """
        chunks = _split_text(text, _MAX_MESSAGE_LENGTH)
        message_id = 0
        for i, chunk in enumerate(chunks):
            payload: dict[str, Any] = {
                "chat_id": self._chat_id,
                "text": chunk,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            # Only attach reply_markup to the last chunk
            if reply_markup and i == len(chunks) - 1:
                payload["reply_markup"] = reply_markup
            response = await self._client.post("/sendMessage", json=payload)
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
            data["caption"] = caption[:_MAX_CAPTION_LENGTH]

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

    async def send_video(
        self,
        video: str | Path,
        caption: str = "",
    ) -> int:
        """Send a video file (up to 50MB via upload, 20MB via URL).

        Returns the message_id.
        """
        data: dict[str, object] = {"chat_id": self._chat_id}
        if caption:
            data["caption"] = caption[:_MAX_CAPTION_LENGTH]

        if isinstance(video, Path) or (isinstance(video, str) and not video.startswith("http")):
            video_path = Path(video)
            with open(video_path, "rb") as f:
                response = await self._client.post(
                    "/sendVideo",
                    data=data,  # type: ignore[arg-type]
                    files={"video": (video_path.name, f, "video/mp4")},
                    timeout=300.0,  # Videos can be large
                )
        else:
            data["video"] = video
            response = await self._client.post("/sendVideo", json=data)

        response.raise_for_status()
        message_id: int = response.json()["result"]["message_id"]
        logger.info("Telegram video sent: %s", video)
        return message_id

    async def send_document(
        self,
        document: Path,
        caption: str = "",
    ) -> int:
        """Send a document/file.

        Returns the message_id.
        """
        data: dict[str, object] = {"chat_id": self._chat_id}
        if caption:
            data["caption"] = caption[:_MAX_CAPTION_LENGTH]

        with open(document, "rb") as f:
            response = await self._client.post(
                "/sendDocument",
                data=data,  # type: ignore[arg-type]
                files={"document": (document.name, f)},
                timeout=300.0,
            )

        response.raise_for_status()
        message_id: int = response.json()["result"]["message_id"]
        logger.info("Telegram document sent: %s", document.name)
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

    # ------------------------------------------------------------------
    # Inline keyboards
    # ------------------------------------------------------------------

    async def send_inline_keyboard(
        self,
        text: str,
        buttons: list[list[tuple[str, str]]],
        *,
        parse_mode: str | None = None,
    ) -> int:
        """Send a message with inline keyboard buttons.

        buttons: list of rows, each row is list of (label, callback_data) tuples.
        Returns the message_id.
        """
        keyboard = [
            [{"text": label, "callback_data": data} for label, data in row]
            for row in buttons
        ]
        return await self.send_message(
            text,
            reply_markup={"inline_keyboard": keyboard},
            parse_mode=parse_mode,
        )

    async def edit_message_reply_markup(
        self,
        message_id: int,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        """Edit (or remove) the inline keyboard on a sent message."""
        payload: dict[str, Any] = {
            "chat_id": self._chat_id,
            "message_id": message_id,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        else:
            payload["reply_markup"] = {"inline_keyboard": []}

        response = await self._client.post("/editMessageReplyMarkup", json=payload)
        response.raise_for_status()

    # ------------------------------------------------------------------
    # Receiving replies and callbacks
    # ------------------------------------------------------------------

    async def wait_for_reply(self, timeout_seconds: int = 1800) -> str:
        """Poll getUpdates until user replies with text. Returns reply text.

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

    async def wait_for_callback(self, timeout_seconds: int = 1800) -> str:
        """Poll getUpdates until user taps an inline button.

        Returns the callback_data string.
        Raises TimeoutError if no callback within timeout.
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

                # Handle callback queries (inline button taps)
                callback = update.get("callback_query")
                if callback:
                    sender_chat = str(callback.get("message", {}).get("chat", {}).get("id", ""))
                    if sender_chat == self._chat_id:
                        data = callback.get("data", "")
                        # Answer the callback to dismiss the loading spinner
                        await self._answer_callback_query(callback["id"])
                        logger.info("Telegram callback received: %r", data)
                        return data

                # Also accept text replies as fallback
                message = update.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", ""))
                text = message.get("text", "")
                if chat_id == self._chat_id and text.strip():
                    logger.info("Telegram text reply (as callback fallback): %r", text.strip())
                    return text.strip()

        raise TimeoutError(
            f"No Telegram callback within {timeout_seconds}s"
        )

    async def _answer_callback_query(self, callback_query_id: str) -> None:
        """Acknowledge a callback query to dismiss the loading spinner."""
        response = await self._client.post(
            "/answerCallbackQuery",
            json={"callback_query_id": callback_query_id},
        )
        response.raise_for_status()

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
