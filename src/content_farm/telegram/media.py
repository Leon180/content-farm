"""Telegram file download helpers."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from content_farm.telegram.bot import TelegramBot

logger = logging.getLogger(__name__)

# Allow alphanumeric, dots, hyphens, colons (for timestamps), underscores.
_SAFE_CHARS = re.compile(r"[^\w.\-:]")


def _safe_filename(raw: str) -> str:
    """Sanitise a Telegram-supplied filename to prevent path traversal."""
    name = Path(raw).name  # strip any directory components
    safe = _SAFE_CHARS.sub("_", name)
    return safe or "upload.bin"


async def download_telegram_document(
    bot: TelegramBot,
    update: dict[str, Any],
    destination_dir: Path,
) -> tuple[Path, str] | None:
    """Download a document from a Telegram update.

    Returns ``(local_path, original_filename)`` or ``None`` if
    the update doesn't contain a document.
    """
    message = update.get("message", {})
    document = message.get("document")
    if not document:
        return None

    file_id = document["file_id"]
    raw_filename = document.get("file_name", f"{file_id}.bin")
    filename = _safe_filename(raw_filename)

    destination = destination_dir / filename
    await bot.download_file(file_id, destination)

    logger.info("Downloaded document: %s → %s", filename, destination)
    return destination, filename
