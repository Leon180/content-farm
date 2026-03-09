"""Approval gate — human-in-the-loop checkpoints via Telegram."""

from __future__ import annotations

import logging
import re

from content_farm.script_gen.schemas import Script
from content_farm.telegram.bot import TelegramBot
from content_farm.telegram.schemas import ApprovalResult
from content_farm.visual.schemas import VisualAsset

logger = logging.getLogger(__name__)

_APPROVED_PATTERN = re.compile(
    r"^(ok|OK|Ok|好|通過|可以|沒問題|没问题|確認|确认)",
)

_REJECTION_REPLY = "收到！請修改完成後回覆 ok 繼續 Pipeline。"


class ApprovalGate:
    """Telegram-based approval checkpoints for the pipeline.

    If bot is None, all checks auto-approve (for running without Telegram).
    """

    def __init__(self, bot: TelegramBot | None) -> None:
        self._bot = bot

    async def check_script(self, script: Script) -> ApprovalResult:
        """Send script for review, wait for approval."""
        if self._bot is None:
            return ApprovalResult(approved=True, reply_text="auto-approved")

        messages = _format_script(script)
        for msg in messages:
            await self._bot.send_message(msg)

        return await self._wait_for_approval()

    async def check_visuals(
        self,
        assets: tuple[VisualAsset, ...],
    ) -> ApprovalResult:
        """Send visual preview summary, wait for approval."""
        if self._bot is None:
            return ApprovalResult(approved=True, reply_text="auto-approved")

        lines = [f"【片段預覽】共 {len(assets)} 個場景", ""]
        for asset in assets:
            lines.append(
                f"場景 {asset.scene_number}：{asset.query_used} "
                f"({asset.duration_seconds:.1f}s) [{asset.source}]"
            )
        lines.append("")
        lines.append("確認請回覆 ok，需要修改請回覆任意文字。")
        await self._bot.send_message("\n".join(lines))

        return await self._wait_for_approval()

    async def _wait_for_approval(self) -> ApprovalResult:
        """Poll until user sends an approval keyword."""
        while True:
            reply = await self._bot.wait_for_reply()  # type: ignore[union-attr]
            if _is_approved(reply):
                logger.info("Approval granted: %r", reply)
                return ApprovalResult(approved=True, reply_text=reply)
            logger.info("Approval rejected: %r, waiting for ok...", reply)
            await self._bot.send_message(_REJECTION_REPLY)  # type: ignore[union-attr]


def _is_approved(text: str) -> bool:
    """Check if reply text is an approval keyword."""
    return bool(_APPROVED_PATTERN.match(text.strip()))


def _format_script(script: Script) -> list[str]:
    """Format script as readable Telegram messages."""
    lines: list[str] = [
        "【腳本審核】",
        f"標題：{script.video_title}",
        f"描述：{script.description}",
        f"語言：{script.language}",
        "",
    ]

    for scene in script.scenes:
        lines.append(f"── 場景 {scene.scene_number}：{scene.title} ({scene.duration_seconds}s) ──")
        lines.append(scene.narration)
        lines.append("")

    lines.append("確認請回覆 ok，需要修改請回覆任意文字。")

    full_text = "\n".join(lines)

    # Split if too long for Telegram
    if len(full_text) <= 4096:
        return [full_text]

    chunks: list[str] = []
    remaining = full_text
    while remaining:
        if len(remaining) <= 4096:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, 4096)
        if cut <= 0:
            cut = 4096
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    return chunks
