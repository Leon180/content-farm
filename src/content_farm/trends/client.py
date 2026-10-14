"""Google Trends client — fetch trending queries for zh-TW."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from content_farm.trends.schemas import TrendingQuery

logger = logging.getLogger(__name__)

# Map our categories to Google Trends category IDs
_CATEGORY_IDS: dict[str, int] = {
    "science": 174,
    "history": 433,
    "psychology": 6,
    "culture": 0,  # No specific ID — use seed keywords
    "technology": 5,
    "space": 174,  # Shares Science ID, differentiated by seeds
}

# Seed keywords per category (fallback when pytrends fails)
_CATEGORY_SEEDS: dict[str, list[str]] = {
    "science": ["科學", "冷知識", "物理", "化學", "生物"],
    "history": ["歷史", "古代", "戰爭", "文明", "考古"],
    "psychology": ["心理學", "人類行為", "大腦", "情緒", "認知"],
    "culture": ["台灣冷知識", "文化", "台灣全球排名", "習俗", "台灣第一"],
    "technology": ["科技", "AI", "人工智慧", "手機", "未來"],
    "space": ["太空", "宇宙", "黑洞", "NASA", "火星"],
}


class TrendsClient:
    """Fetch trending queries from Google Trends for zh-TW.

    Uses pytrends (unofficial). Falls back to seed keywords on failure.
    """

    async def get_trending(
        self,
        category: str,
        geo: str = "TW",
        limit: int = 10,
    ) -> list[TrendingQuery]:
        """Return trending queries for a category."""
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None, self._fetch_sync, category, geo, limit,
            )
        except Exception:
            logger.warning(
                "Google Trends query failed for '%s', using seeds",
                category, exc_info=True,
            )
            return self._fallback_seeds(category)

    def _fetch_sync(
        self, category: str, geo: str, limit: int,
    ) -> list[TrendingQuery]:
        """Synchronous trends fetch using pytrends."""
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="zh-TW", tz=480)
        cat_id = _CATEGORY_IDS.get(category, 0)
        seeds = _CATEGORY_SEEDS.get(category, ["冷知識"])[:3]

        queries: list[str] = []

        # Try related queries for seed keywords
        try:
            pytrends.build_payload(
                seeds, cat=cat_id, timeframe="now 7-d", geo=geo,
            )
            related: dict[str, Any] = pytrends.related_queries()

            for keyword_data in related.values():
                rising = keyword_data.get("rising")
                if rising is not None and not rising.empty:
                    for _, row in rising.head(limit).iterrows():
                        q = str(row.get("query", "")).strip()
                        if q and q not in queries:
                            queries.append(q)

                top = keyword_data.get("top")
                if top is not None and not top.empty:
                    for _, row in top.head(limit).iterrows():
                        q = str(row.get("query", "")).strip()
                        if q and q not in queries:
                            queries.append(q)
        except Exception:
            logger.warning("Related queries failed", exc_info=True)

        # Deduplicate and limit
        queries = queries[:limit]

        if not queries:
            return self._fallback_seeds(category)

        return [
            TrendingQuery(query=q, category=category)
            for q in queries
        ]

    def _fallback_seeds(self, category: str) -> list[TrendingQuery]:
        """Return seed keywords as TrendingQuery objects."""
        seeds = _CATEGORY_SEEDS.get(category, ["冷知識"])
        return [
            TrendingQuery(query=s, category=category)
            for s in seeds
        ]
