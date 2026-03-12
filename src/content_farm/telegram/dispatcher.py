"""Central update dispatcher — single polling loop for the daemon bot."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

from content_farm.telegram.bot import TelegramBot

logger = logging.getLogger(__name__)

# Handler type: async function that takes a raw Telegram update dict
Handler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]

_HELP_TEXT = (
    "可用指令：\n"
    "/topics — 瀏覽熱門主題\n"
    "/go <主題> — 直接指定主題開始\n"
    "/status — 查看 pipeline 狀態\n"
    "/runs — 列出最近的 runs\n"
    "/continue — 從 checkpoint 繼續上次的 run\n"
    "/retry — 重試最近一次失敗的 run\n"
    "/cancel — 取消執行中的 pipeline\n"
    "/check [run_id] — 檢查並補抓缺少的素材\n"
    "/compose [run_id] — 進入素材合成模式\n"
    "/done — 完成素材上傳，開始合成"
)


class UpdateDispatcher:
    """Central getUpdates loop. Routes to command handlers or approval waiters.

    Only one instance should exist per bot token — Telegram enforces
    single-consumer for getUpdates.
    """

    def __init__(self, bot: TelegramBot) -> None:
        self._bot = bot
        self._offset: int = 0
        self._running: bool = False
        self._approval_queue: asyncio.Queue[dict[str, Any]] | None = None
        self._command_handlers: dict[str, Handler] = {}
        self._callback_handlers: dict[str, Handler] = {}
        self._document_handler: Handler | None = None

    def register_command(self, command: str, handler: Handler) -> None:
        """Register a handler for a /command (include the slash)."""
        self._command_handlers[command] = handler

    def register_callback_prefix(self, prefix: str, handler: Handler) -> None:
        """Register a handler for callback_query data with a given prefix."""
        self._callback_handlers[prefix] = handler

    def set_document_handler(self, handler: Handler | None) -> None:
        """Set or clear the handler for incoming documents (files)."""
        self._document_handler = handler

    def set_approval_queue(
        self, queue: asyncio.Queue[dict[str, Any]] | None,
    ) -> None:
        """Set or clear the approval queue for pipeline input routing."""
        self._approval_queue = queue

    @property
    def has_approval_queue(self) -> bool:
        return self._approval_queue is not None

    async def run(self) -> None:
        """Main polling loop. Runs until stop() is called."""
        self._offset = await self._bot.flush_updates()
        self._running = True
        logger.info("Dispatcher started, listening for updates...")

        while self._running:
            try:
                updates, self._offset = await self._bot.get_updates(
                    self._offset, timeout=30,
                )
                for update in updates:
                    await self._route(update)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("Polling error, retrying in 5s", exc_info=True)
                await asyncio.sleep(5)

    def stop(self) -> None:
        """Signal the polling loop to stop."""
        self._running = False

    async def _route(self, update: dict[str, Any]) -> None:
        """Route an update to the appropriate handler."""
        # 1. Handle callback queries (inline button taps)
        callback = update.get("callback_query")
        if callback:
            data = callback.get("data", "")
            # Check registered callback prefixes
            for prefix, handler in self._callback_handlers.items():
                if data.startswith(prefix):
                    await handler(update)
                    return
            # If no prefix matches and approval queue is active, forward
            if self._approval_queue is not None:
                await self._approval_queue.put(update)
                return
            return

        # 2. Handle documents (files sent by user)
        message = update.get("message", {})
        if message.get("document") and self._document_handler:
            await self._document_handler(update)
            return

        # 3. Handle text messages
        text = message.get("text", "")

        if text.startswith("/"):
            command = text.split()[0].lower()
            # Always route these commands, even during pipeline
            if command in self._command_handlers:
                await self._command_handlers[command](update)
                return

        # 3. Forward to approval queue if pipeline is running
        if self._approval_queue is not None and text.strip():
            await self._approval_queue.put(update)
            return

        # 4. Unrecognized message when idle
        if text.strip() and not self.has_approval_queue:
            await self._bot.send_message(_HELP_TEXT)
