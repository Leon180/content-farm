#!/usr/bin/env python
"""Always-on Telegram bot daemon for Content Farm.

Usage:
    python scripts/run_bot.py

Commands available in Telegram:
    /topics     — Browse trending topics by category
    /go <topic> — Directly start pipeline with a topic
    /status     — Check current pipeline status
    /runs       — List recent pipeline runs
    /continue   — Resume from last checkpoint
    /retry      — Retry the most recent failed run
    /cancel     — Cancel the running pipeline
    /check      — Check and re-fetch missing artifacts for a completed run
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from content_farm.config import Settings
from content_farm.llm.client import LLMClient
from content_farm.telegram.bot import TelegramBot
from content_farm.telegram.dispatcher import UpdateDispatcher
from content_farm.telegram.handlers import (
    handle_cancel,
    handle_category_selection,
    handle_check,
    handle_compose,
    handle_continue,
    handle_done,
    handle_go,
    handle_retry,
    handle_runs,
    handle_status,
    handle_title_selection,
    handle_topics,
)
from content_farm.telegram.runner import PipelineRunner
from content_farm.trends.client import TrendsClient
from content_farm.trends.handler import TrendingHandler

logger = logging.getLogger(__name__)


def _validate_credentials(settings: Settings) -> None:
    """Validate required credentials are present at startup."""
    errors: list[str] = []

    if not settings.telegram_bot_token.get_secret_value():
        errors.append("CF_TELEGRAM_BOT_TOKEN is required")
    if not settings.telegram_chat_id:
        errors.append("CF_TELEGRAM_CHAT_ID is required")
    if not settings.anthropic_api_key.get_secret_value():
        errors.append("CF_ANTHROPIC_API_KEY is required")

    if errors:
        for err in errors:
            logger.error(err)
        sys.exit(1)


async def main() -> None:
    settings = Settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    _validate_credentials(settings)

    token = settings.telegram_bot_token.get_secret_value()
    chat_id = settings.telegram_chat_id

    bot = TelegramBot(token=token, chat_id=chat_id)
    dispatcher = UpdateDispatcher(bot)
    runner = PipelineRunner(settings, dispatcher, bot)

    # Shared LLM client for title generation
    llm = LLMClient(api_key=settings.anthropic_api_key.get_secret_value())
    trends_client = TrendsClient()
    trending_handler = TrendingHandler(bot, trends_client, llm)

    # Register command handlers
    dispatcher.register_command(
        "/topics", lambda u: handle_topics(u, bot),
    )
    dispatcher.register_command(
        "/go", lambda u: handle_go(u, bot, runner),
    )
    dispatcher.register_command(
        "/status", lambda u: handle_status(u, bot, runner),
    )
    dispatcher.register_command(
        "/runs", lambda u: handle_runs(u, bot, settings),
    )
    dispatcher.register_command(
        "/retry", lambda u: handle_retry(u, bot, runner),
    )
    dispatcher.register_command(
        "/cancel", lambda u: handle_cancel(u, bot, runner),
    )
    dispatcher.register_command(
        "/continue", lambda u: handle_continue(u, bot, runner),
    )
    dispatcher.register_command(
        "/check", lambda u: handle_check(u, bot, runner),
    )
    dispatcher.register_command(
        "/compose", lambda u: handle_compose(u, bot, runner),
    )
    dispatcher.register_command(
        "/done", lambda u: handle_done(u, bot, runner),
    )

    # Register callback prefix handlers
    dispatcher.register_callback_prefix(
        "cat:", lambda u: handle_category_selection(u, bot, trending_handler),
    )
    dispatcher.register_callback_prefix(
        "title:", lambda u: handle_title_selection(
            u, bot, runner, trending_handler.pending_titles,
        ),
    )

    # Graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, dispatcher.stop)

    # Register commands for Telegram's command menu
    await bot.set_my_commands([
        ("topics", "瀏覽熱門主題分類"),
        ("go", "直接開始 pipeline（/go <主題>）"),
        ("status", "查看目前 pipeline 狀態"),
        ("runs", "列出最近的 pipeline runs"),
        ("continue", "從上次 checkpoint 繼續"),
        ("retry", "重試最近失敗的 run"),
        ("cancel", "取消執行中的 pipeline"),
        ("check", "檢查並補抓缺少的素材（/check [run_id]）"),
        ("compose", "進入素材合成模式（/compose [run_id]）"),
        ("done", "完成素材上傳，開始合成"),
    ])

    logger.info("Content Farm Bot started. Listening for commands...")
    await bot.send_message("Bot 已啟動，使用 /topics 開始。")

    try:
        await dispatcher.run()
    finally:
        await bot.close()
        await llm.close()
        logger.info("Bot shutdown complete.")


if __name__ == "__main__":
    from content_farm.llm.paid import consent_from_argv

    sys.argv = consent_from_argv(sys.argv, "run_bot.py")   # metered API: --allow-paid or exit 2
    asyncio.run(main())
