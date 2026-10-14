"""Command handlers for the Telegram bot daemon."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from content_farm.config import Settings
from content_farm.pipeline.state import PipelineStateDB
from content_farm.telegram.bot import TelegramBot

logger = logging.getLogger(__name__)

# Topic categories for /topics command
CATEGORIES: dict[str, str] = {
    "science": "科學/冷知識",
    "technology": "科技/AI",
    "psychology": "心理學",
    "history": "歷史",
    "space": "宇宙/太空",
    "culture": "文化/台灣",
}


async def handle_topics(
    update: dict[str, Any],
    bot: TelegramBot,
) -> None:
    """Handle /topics — show category selection keyboard."""
    buttons = [
        [(label, f"cat:{key}") for key, label in list(CATEGORIES.items())[i:i+3]]
        for i in range(0, len(CATEGORIES), 3)
    ]
    await bot.send_inline_keyboard("選擇一個主題分類：", buttons)


async def handle_go(
    update: dict[str, Any],
    bot: TelegramBot,
    runner: Any,  # PipelineRunner (avoid circular import)
) -> None:
    """Handle /go <topic> — directly start pipeline with a topic."""
    message = update.get("message", {})
    text = message.get("text", "")
    parts = text.split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        await bot.send_message("請提供主題，例如：/go 為什麼飛機窗戶是圓的")
        return

    topic = parts[1].strip()
    await runner.start(topic)


async def handle_status(
    update: dict[str, Any],
    bot: TelegramBot,
    runner: Any,
) -> None:
    """Handle /status — show current pipeline status."""
    await bot.send_message(runner.status_summary)


async def handle_runs(
    update: dict[str, Any],
    bot: TelegramBot,
    settings: Settings,
) -> None:
    """Handle /runs — list recent pipeline runs."""
    output_dir = Path(settings.output_dir)
    db = PipelineStateDB(output_dir / "pipeline_state.db")
    try:
        runs = db.list_runs(limit=10)
    finally:
        db.close()

    if not runs:
        await bot.send_message("還沒有任何 pipeline runs。")
        return

    lines = ["最近的 Pipeline Runs:", ""]
    for run in runs:
        status_emoji = {
            "completed": "V",
            "failed": "X",
            "in_progress": ">",
        }.get(run.status, "?")
        stages = ", ".join(run.completed_stages) if run.completed_stages else "none"
        lines.append(
            f"[{status_emoji}] {run.run_id} | {run.topic[:30]}\n"
            f"    {run.status} | stages: {stages}\n"
            f"    {run.created_at[:16]}"
        )
        lines.append("")

    await bot.send_message("\n".join(lines))


async def handle_retry(
    update: dict[str, Any],
    bot: TelegramBot,
    runner: Any,
) -> None:
    """Handle /retry — resume the most recent failed run."""
    run_id = runner.last_failed_run_id
    if run_id is None:
        await bot.send_message("沒有找到失敗的 run 可以重試。")
        return

    await runner.resume(run_id)


async def handle_continue(
    update: dict[str, Any],
    bot: TelegramBot,
    runner: Any,
) -> None:
    """Handle /continue — resume the most recent incomplete run from checkpoint."""
    run_id = runner.last_resumable_run_id
    if run_id is None:
        await bot.send_message("沒有找到可以繼續的 run。")
        return

    await runner.resume(run_id)


async def handle_cancel(
    update: dict[str, Any],
    bot: TelegramBot,
    runner: Any,
) -> None:
    """Handle /cancel — cancel the running pipeline."""
    await runner.cancel()


async def handle_check(
    update: dict[str, Any],
    bot: TelegramBot,
    runner: Any,
) -> None:
    """Handle /check [run_id] — check and re-fetch missing artifacts for a run."""
    message = update.get("message", {})
    text = message.get("text", "")
    parts = text.split(maxsplit=1)

    run_id = parts[1].strip() if len(parts) > 1 else None
    await runner.fetch(run_id)


async def handle_compose(
    update: dict[str, Any],
    bot: TelegramBot,
    runner: Any,
) -> None:
    """Handle /compose [run_id] — enter material staging mode."""
    message = update.get("message", {})
    text = message.get("text", "")
    parts = text.split(maxsplit=1)

    run_id = parts[1].strip() if len(parts) > 1 else None
    await runner.start_compose(run_id)


async def handle_done(
    update: dict[str, Any],
    bot: TelegramBot,
    runner: Any,
) -> None:
    """Handle /done — trigger final composition from staged materials."""
    await runner.finish_compose()


async def handle_category_selection(
    update: dict[str, Any],
    bot: TelegramBot,
    trending_handler: Any,  # TrendingHandler
) -> None:
    """Handle cat:* callback — fetch trends for selected category."""
    callback = update.get("callback_query", {})
    data = callback.get("data", "")
    await bot.answer_callback_query(callback.get("id", ""))

    if not data.startswith("cat:"):
        return

    category_key = data[4:]
    category_name = CATEGORIES.get(category_key, category_key)
    await trending_handler.fetch_and_present(category_key, category_name)


async def handle_title_selection(
    update: dict[str, Any],
    bot: TelegramBot,
    runner: Any,
    pending_titles: dict[str, str],
) -> None:
    """Handle title:* callback — start pipeline with selected title."""
    callback = update.get("callback_query", {})
    data = callback.get("data", "")
    await bot.answer_callback_query(callback.get("id", ""))

    if not data.startswith("title:"):
        return

    title_key = data[6:]
    if title_key == "custom":
        await bot.send_message("請輸入你的自訂主題：\n（使用 /go <主題> 格式）")
        return

    title = pending_titles.get(title_key, title_key)
    await runner.start(title)
