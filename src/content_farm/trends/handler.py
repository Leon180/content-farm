"""Trending flow handler — fetches trends, generates titles, presents choices."""

from __future__ import annotations

import logging

from content_farm.llm.client import LLMClient
from content_farm.telegram.bot import TelegramBot
from content_farm.trends.client import TrendsClient
from content_farm.trends.title_generator import generate_titles

logger = logging.getLogger(__name__)


class TrendingHandler:
    """Orchestrates the trending → title generation → selection flow.

    Maintains a mapping of short IDs to full titles for callback data
    (Telegram limits callback_data to 64 bytes).
    """

    def __init__(
        self,
        bot: TelegramBot,
        trends_client: TrendsClient,
        llm: LLMClient,
    ) -> None:
        self._bot = bot
        self._trends = trends_client
        self._llm = llm
        self._pending_titles: dict[str, str] = {}

    @property
    def pending_titles(self) -> dict[str, str]:
        """Mapping of short ID → full title for callback data."""
        return self._pending_titles

    async def fetch_and_present(
        self, category_key: str, category_name: str,
    ) -> None:
        """Fetch trends, generate titles, and present as inline keyboard."""
        await self._bot.send_message(
            f"正在搜尋 {category_name} 的熱門趨勢..."
        )

        trends = await self._trends.get_trending(category_key)

        if not trends:
            await self._bot.send_message(
                "Google Trends 暫時無法使用，稍後再試。\n"
                "你也可以直接輸入主題，例如：/go 為什麼飛機窗戶是圓的"
            )
            return

        await self._bot.send_message("趨勢查詢完成，正在生成標題...")

        titles = await generate_titles(
            self._llm, trends, category_name, count=5,
        )

        if not titles:
            await self._bot.send_message(
                "標題生成失敗，請直接輸入主題：/go <主題>"
            )
            return

        # Store titles with short IDs (callback_data limit = 64 bytes)
        self._pending_titles.clear()
        buttons: list[list[tuple[str, str]]] = []
        for i, title in enumerate(titles):
            key = str(i)
            self._pending_titles[key] = title
            # Truncate display label if too long
            label = title[:40] + "..." if len(title) > 40 else title
            buttons.append([(label, f"title:{key}")])

        buttons.append([("自訂主題", "title:custom")])

        await self._bot.send_inline_keyboard("選擇影片主題：", buttons)
