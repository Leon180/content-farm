"""Approval gate — human-in-the-loop checkpoints via Telegram."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.telegram.bot import TelegramBot
from content_farm.telegram.schemas import ApprovalResult
from content_farm.visual.schemas import VisualAsset

logger = logging.getLogger(__name__)

_APPROVED_PATTERN = re.compile(
    r"^(ok|OK|Ok|好|通過|可以|沒問題|没问题|確認|确认|approve)",
)

_REJECTION_REPLY = "收到！請修改完成後回覆 ok 繼續 Pipeline。"

# Inline keyboard button callback data
_CB_APPROVE = "approve"
_CB_EDIT = "edit"

_SCRIPT_BUTTONS = [
    [("Approve", _CB_APPROVE), ("Edit", _CB_EDIT)],
]

_APPROVAL_BUTTONS = [
    [("Approve", _CB_APPROVE)],
]

# Pattern to parse user's scene edits: "場景1：旁白內容" or "場景 1: 旁白內容"
_SCENE_EDIT_PATTERN = re.compile(
    r"場景\s*(\d+)\s*[：:]\s*(.+?)"
    r"(?=場景\s*\d+\s*[：:]|場景\s*\d+\s*關鍵字|標題\s*[：:]|描述\s*[：:]|\Z)",
    re.DOTALL,
)
# Keyword edit: "場景1關鍵字：keyword1, keyword2"
_KEYWORD_EDIT_PATTERN = re.compile(
    r"場景\s*(\d+)\s*關鍵字\s*[：:]\s*(.+?)"
    r"(?=場景\s*\d+\s*[：:]|場景\s*\d+\s*關鍵字|標題\s*[：:]|描述\s*[：:]|\Z)",
    re.DOTALL,
)
# Patterns for title/description edits
_TITLE_EDIT_PATTERN = re.compile(
    r"標題\s*[：:]\s*(.+?)"
    r"(?=場景\s*\d+\s*[：:]|場景\s*\d+\s*關鍵字|描述\s*[：:]|\Z)",
    re.DOTALL,
)
_DESC_EDIT_PATTERN = re.compile(
    r"描述\s*[：:]\s*(.+?)"
    r"(?=場景\s*\d+\s*[：:]|場景\s*\d+\s*關鍵字|標題\s*[：:]|\Z)",
    re.DOTALL,
)


class ApprovalGate:
    """Telegram-based approval checkpoints for the pipeline.

    If bot is None, all checks auto-approve (for running without Telegram).
    Uses inline keyboard buttons for cleaner UX, with text fallback.
    """

    def __init__(
        self,
        bot: TelegramBot | None,
        update_queue: asyncio.Queue[dict] | None = None,
    ) -> None:
        self._bot = bot
        self._update_queue = update_queue

    async def check_script(self, script: Script) -> ApprovalResult:
        """Send script for review with Edit/Approve buttons.

        If user edits, parses changes, patches the script, and re-sends.
        Returns ApprovalResult with optional edited_script.
        """
        if self._bot is None:
            return ApprovalResult(approved=True, reply_text="auto-approved")

        current_script = script

        while True:
            messages = _format_script(current_script)
            for msg in messages[:-1]:
                await self._bot.send_message(msg)

            msg_id = await self._bot.send_inline_keyboard(
                messages[-1],
                _SCRIPT_BUTTONS,
            )

            result = await self._wait_for_script_action(current_script)
            await self._bot.edit_message_reply_markup(msg_id)

            if result.approved:
                if current_script is not script:
                    return ApprovalResult(
                        approved=True,
                        reply_text=result.reply_text,
                        edited_script=current_script,
                    )
                return result

            # User edited — current_script was updated, loop to re-send
            if result.edited_script is not None:
                current_script = result.edited_script
                continue

            break

        return ApprovalResult(approved=True, reply_text="auto-approved")

    async def check_visuals(
        self,
        assets: tuple[VisualAsset, ...],
        *,
        thumbnail_path: Path | None = None,
    ) -> ApprovalResult:
        """Send visual preview with thumbnail and inline buttons."""
        if self._bot is None:
            return ApprovalResult(approved=True, reply_text="auto-approved")

        if thumbnail_path and thumbnail_path.exists():
            await self._bot.send_photo(
                thumbnail_path,
                caption="Thumbnail 預覽",
            )

        lines = [f"【片段預覽】共 {len(assets)} 個場景", ""]
        for asset in assets:
            status = "OK" if asset.file_path else "MISSING"
            lines.append(
                f"場景 {asset.scene_number}：{asset.query_used} "
                f"({asset.duration_seconds:.1f}s) [{asset.source}] {status}"
            )
        lines.append("")
        lines.append("確認請按 Approve。")

        msg_id = await self._bot.send_inline_keyboard(
            "\n".join(lines),
            _APPROVAL_BUTTONS,
        )

        result = await self._wait_for_approval()
        await self._bot.edit_message_reply_markup(msg_id)
        return result

    async def deliver_materials(
        self,
        script: Script,
        drive_link: str,
    ) -> None:
        """Send materials package via Telegram: Drive link + script + storyboard."""
        if self._bot is None:
            return

        # 1. Drive link
        await self._bot.send_message(
            f"素材已上傳至 Google Drive:\n{drive_link}"
        )

        # 2. Script narration (per scene)
        script_lines = [f"【腳本】{script.video_title}", ""]
        for scene in script.scenes:
            script_lines.append(
                f"--- 場景 {scene.scene_number}: {scene.title} "
                f"({scene.duration_seconds}s) ---"
            )
            script_lines.append(scene.narration)
            script_lines.append("")
        await self._bot.send_message("\n".join(script_lines))

        # 3. Storyboard / visual prompts (for sourcing images & footage)
        board_lines = [f"【分鏡稿】共 {len(script.scenes)} 個場景", ""]
        for scene in script.scenes:
            hint = scene.visual_hint
            prompt_parts = [hint.description]
            if hint.keywords:
                prompt_parts.append(", ".join(hint.keywords[:4]))
            prompt_parts.append("cinematic, high quality, 9:16 vertical")
            prompt = ". ".join(prompt_parts)

            board_lines.append(f"場景 {scene.scene_number} ({scene.duration_seconds}s):")
            board_lines.append(f"Prompt: {prompt}")
            board_lines.append("")
        await self._bot.send_message("\n".join(board_lines))

    async def notify_completion(
        self,
        *,
        video_path: str,
        output_dir: str,
        script: Script | None = None,
        upload_url: str | None = None,
        drive_link: str | None = None,
    ) -> None:
        """Send completion notification with the final video."""
        if self._bot is None:
            return

        lines = ["Pipeline 完成!"]
        if drive_link:
            lines.append(f"  Google Drive: {drive_link}")
        if upload_url:
            lines.append(f"  YouTube: {upload_url}")
        lines.append(f"  輸出目錄: {output_dir}")
        await self._bot.send_message("\n".join(lines))

        # Send script + storyboard
        if script is not None:
            script_lines = [f"【腳本】{script.video_title}", ""]
            for scene in script.scenes:
                script_lines.append(
                    f"--- 場景 {scene.scene_number}: {scene.title} "
                    f"({scene.duration_seconds}s) ---"
                )
                script_lines.append(scene.narration)
                script_lines.append("")
            await self._bot.send_message("\n".join(script_lines))

            board_lines = [f"【分鏡稿】共 {len(script.scenes)} 個場景", ""]
            for scene in script.scenes:
                hint = scene.visual_hint
                prompt_parts = [hint.description]
                if hint.keywords:
                    prompt_parts.append(", ".join(hint.keywords[:4]))
                prompt_parts.append("cinematic, high quality, 9:16 vertical")
                prompt = ". ".join(prompt_parts)
                board_lines.append(f"場景 {scene.scene_number} ({scene.duration_seconds}s):")
                board_lines.append(f"Prompt: {prompt}")
                board_lines.append("")
            await self._bot.send_message("\n".join(board_lines))

        vpath = Path(video_path)
        if vpath.exists() and vpath.stat().st_size < 50 * 1024 * 1024:
            await self._bot.send_video(vpath, caption="最終影片")
        elif vpath.exists():
            logger.info("Video too large for Telegram (%d MB), skipping send",
                        vpath.stat().st_size // (1024 * 1024))

    async def notify_progress(
        self, step: int, total: int, description: str,
    ) -> None:
        """Send a brief progress update, e.g. '[2/5] 正在生成語音...'."""
        if self._bot is None:
            return
        await self._bot.send_message(f"[{step}/{total}] {description}")

    async def notify_failure(self, *, error: str, run_id: str = "") -> None:
        """Send failure notification."""
        if self._bot is None:
            return

        lines = ["Pipeline 失敗"]
        if run_id:
            lines.append(f"  Run ID: {run_id}")
            lines.append("  使用 /continue 從 checkpoint 繼續")
        lines.append(f"  錯誤: {error[-500:]}")
        await self._bot.send_message("\n".join(lines))

    async def confirm_action(self, message: str) -> bool:
        """Send a message with [Confirm] / [Cancel] buttons.

        Returns ``True`` if the user confirms, ``False`` if cancelled.
        Auto-confirms when no bot is configured.
        """
        if self._bot is None:
            return True

        _CB_CONFIRM = "confirm"
        _CB_CANCEL = "cancel"
        buttons = [[("確認", _CB_CONFIRM), ("取消", _CB_CANCEL)]]

        await self._bot.send_inline_keyboard(message, buttons)

        while True:
            reply = await self._wait_for_input()

            if reply in (_CB_CANCEL, "/abort", "/cancel"):
                logger.info("Action cancelled by user")
                return False

            if reply == _CB_CONFIRM or _is_approved(reply):
                logger.info("Action confirmed by user")
                return True

            # Unrecognised — prompt again
            await self._bot.send_inline_keyboard(
                "請按 確認 或 取消。", buttons,
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _wait_for_input(self) -> str:
        """Get next user input — from queue (daemon mode) or direct poll (CLI).

        In daemon mode, the central dispatcher feeds updates into the queue.
        In CLI mode, falls back to the legacy wait_for_callback().
        """
        if self._update_queue is not None:
            update = await self._update_queue.get()
            # Cancel sentinel from dispatcher
            if update.get("_cancel"):
                raise KeyboardInterrupt("Cancelled by user")
            # Extract callback_data or text
            callback = update.get("callback_query")
            if callback:
                await self._bot.answer_callback_query(callback["id"])  # type: ignore[union-attr]
                return callback.get("data", "")
            message = update.get("message", {})
            return message.get("text", "").strip()
        # Legacy mode: direct polling
        return await self._bot.wait_for_callback()  # type: ignore[union-attr]

    async def _wait_for_script_action(
        self, current_script: Script,
    ) -> ApprovalResult:
        """Wait for Approve/Edit action on script review."""
        while True:
            reply = await self._wait_for_input()

            if reply.strip().lower() in ("/abort", "/cancel"):
                logger.info("Abort requested via command")
                await self._bot.send_message("Pipeline 已取消。")  # type: ignore[union-attr]
                raise KeyboardInterrupt("Aborted by user via /abort")

            if reply.strip().lower() == "/status":
                await self._bot.send_message("等待腳本審核中…")  # type: ignore[union-attr]
                continue

            if reply == _CB_APPROVE or _is_approved(reply):
                logger.info("Script approved: %r", reply)
                return ApprovalResult(approved=True, reply_text=reply)

            if reply == _CB_EDIT:
                logger.info("Script edit requested")
                await self._bot.send_message(  # type: ignore[union-attr]
                    "請回覆要修改的內容，格式：\n"
                    "標題：新的標題\n"
                    "描述：新的描述\n"
                    "場景1：新的旁白\n"
                    "場景2：新的旁白\n"
                    "場景1關鍵字：keyword1, keyword2（用英文）\n\n"
                    "只需列出要修改的部分即可。"
                )
                edit_text = await self._wait_for_input()
                edited = _apply_script_edits(edit_text, current_script)
                if edited is not None:
                    await self._bot.send_message("已套用修改，重新檢視腳本。")  # type: ignore[union-attr]
                    return ApprovalResult(
                        approved=False,
                        reply_text=edit_text,
                        edited_script=edited,
                    )
                await self._bot.send_message(  # type: ignore[union-attr]
                    "無法解析修改內容，請確認格式：場景N：旁白內容"
                )
                continue

            # Text that looks like scene or keyword edits (direct reply)
            edits = _parse_scene_edits(reply)
            kw_edits = _parse_keyword_edits(reply)
            if edits or kw_edits:
                edited = _apply_scene_edits(
                    edits, current_script, keyword_edits=kw_edits,
                )
                if edited is not None:
                    await self._bot.send_message("已套用修改，重新檢視腳本。")  # type: ignore[union-attr]
                    return ApprovalResult(
                        approved=False,
                        reply_text=reply,
                        edited_script=edited,
                    )

            logger.info("Unrecognized reply: %r", reply)
            await self._bot.send_message(  # type: ignore[union-attr]
                "請按 Approve 確認或 Edit 修改。"
            )

    async def _wait_for_approval(self) -> ApprovalResult:
        """Wait for inline button tap or text reply (simple approve only)."""
        while True:
            reply = await self._wait_for_input()

            if reply.strip().lower() in ("/abort", "/cancel"):
                logger.info("Abort requested via command")
                await self._bot.send_message("Pipeline 已取消。")  # type: ignore[union-attr]
                raise KeyboardInterrupt("Aborted by user via /abort")

            if reply.strip().lower() == "/status":
                await self._bot.send_message("等待審批中…")  # type: ignore[union-attr]
                continue

            if reply == _CB_APPROVE or _is_approved(reply):
                logger.info("Approval granted: %r", reply)
                return ApprovalResult(approved=True, reply_text=reply)

            logger.info("Approval rejected: %r, waiting for ok...", reply)
            await self._bot.send_message(_REJECTION_REPLY)  # type: ignore[union-attr]


def _is_approved(text: str) -> bool:
    """Check if reply text is an approval keyword."""
    return bool(_APPROVED_PATTERN.match(text.strip()))


def _parse_scene_edits(text: str) -> dict[int, str]:
    """Parse user's scene edit text into {scene_number: new_narration}."""
    edits: dict[int, str] = {}
    for match in _SCENE_EDIT_PATTERN.finditer(text):
        scene_num = int(match.group(1))
        narration = match.group(2).strip()
        if narration:
            edits[scene_num] = narration
    return edits


def _parse_title_edit(text: str) -> str | None:
    """Parse title edit from user text."""
    match = _TITLE_EDIT_PATTERN.search(text)
    if match:
        title = match.group(1).strip()
        return title if title else None
    return None


def _parse_desc_edit(text: str) -> str | None:
    """Parse description edit from user text."""
    match = _DESC_EDIT_PATTERN.search(text)
    if match:
        desc = match.group(1).strip()
        return desc if desc else None
    return None


def _parse_keyword_edits(text: str) -> dict[int, tuple[str, ...]]:
    """Parse keyword edits: {scene_number: (kw1, kw2, ...)}."""
    edits: dict[int, tuple[str, ...]] = {}
    for match in _KEYWORD_EDIT_PATTERN.finditer(text):
        scene_num = int(match.group(1))
        raw = match.group(2).strip()
        keywords = tuple(k.strip() for k in raw.split(",") if k.strip())
        if keywords:
            edits[scene_num] = keywords
    return edits


def _apply_scene_edits(
    edits: dict[int, str],
    script: Script,
    *,
    keyword_edits: dict[int, tuple[str, ...]] | None = None,
) -> Script | None:
    """Apply narration and/or keyword edits, returning a new immutable Script."""
    kw = keyword_edits or {}

    if not edits and not kw:
        return None

    new_scenes = []
    changed = False

    for scene in script.scenes:
        narration = edits.get(scene.scene_number, scene.narration)
        hint = scene.visual_hint

        if scene.scene_number in kw:
            hint = VisualHint(
                description=hint.description,
                style=hint.style,
                keywords=kw[scene.scene_number],
                source_preference=hint.source_preference,
            )

        if narration != scene.narration or hint is not scene.visual_hint:
            new_scenes.append(Scene(
                scene_number=scene.scene_number,
                title=scene.title,
                narration=narration,
                visual_hint=hint,
                duration_seconds=scene.duration_seconds,
                transition=scene.transition,
            ))
            changed = True
        else:
            new_scenes.append(scene)

    if not changed:
        return None

    return Script(
        video_title=script.video_title,
        description=script.description,
        language=script.language,
        scenes=tuple(new_scenes),
        target_length=script.target_length,
        tone=script.tone,
        total_duration_seconds=script.total_duration_seconds,
        tags=script.tags,
        sources=script.sources,
        ai_disclosure=script.ai_disclosure,
    )


def _apply_script_edits(text: str, script: Script) -> Script | None:
    """Parse and apply all edits (title, description, scenes, keywords)."""
    scene_edits = _parse_scene_edits(text)
    kw_edits = _parse_keyword_edits(text)
    new_title = _parse_title_edit(text)
    new_desc = _parse_desc_edit(text)

    if not scene_edits and not kw_edits and new_title is None and new_desc is None:
        return None

    # Apply scene narration + keyword edits
    new_scenes = list(script.scenes)
    for i, scene in enumerate(script.scenes):
        narration = scene_edits.get(scene.scene_number, scene.narration)
        hint = scene.visual_hint

        if scene.scene_number in kw_edits:
            hint = VisualHint(
                description=hint.description,
                style=hint.style,
                keywords=kw_edits[scene.scene_number],
                source_preference=hint.source_preference,
            )

        if narration != scene.narration or hint is not scene.visual_hint:
            new_scenes[i] = Scene(
                scene_number=scene.scene_number,
                title=scene.title,
                narration=narration,
                visual_hint=hint,
                duration_seconds=scene.duration_seconds,
                transition=scene.transition,
            )

    return Script(
        video_title=new_title or script.video_title,
        description=new_desc or script.description,
        language=script.language,
        scenes=tuple(new_scenes),
        target_length=script.target_length,
        tone=script.tone,
        total_duration_seconds=script.total_duration_seconds,
        tags=script.tags,
        sources=script.sources,
        ai_disclosure=script.ai_disclosure,
    )


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
        if scene.visual_hint.keywords:
            kw = ", ".join(scene.visual_hint.keywords)
            lines.append(f"Keywords: {kw}")
        lines.append("")

    if script.sources:
        lines.append("── 參考來源 ──")
        for src in script.sources:
            lines.append(f"• {src}")
        lines.append("")

    lines.append("── 字幕節奏提示 ──")
    lines.append("句號（。）結尾 → 自動停頓 0.35s")
    lines.append("驚嘆/問號（！？）→ 自動停頓 0.35s")
    lines.append("省略號+句號（……。）→ 加倍停頓 0.7s")
    lines.append("可在 Edit 時調整標點來控制字幕間隔。")
    lines.append("")
    lines.append("確認請按 Approve，需要修改請按 Edit。")

    full_text = "\n".join(lines)

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
