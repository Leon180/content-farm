"""Generate video title candidates from trending queries using LLM."""

from __future__ import annotations

import json
import logging

from content_farm.llm.client import LLMClient
from content_farm.trends.schemas import TrendingQuery

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = "你是一位短影音標題專家，擅長為 30-90 秒的 zh-TW 知識型短影片創作吸引人的標題。"

_USER_PROMPT = """\
以下是 {category} 類別近期的熱門搜尋關鍵字：
{queries}

請根據這些趨勢，產出 {count} 個適合短影片的標題。

要求：
1. 標題要有懸念或反直覺（引發好奇心）
2. 適合 30-90 秒的科普/知識型內容
3. 使用繁體中文（zh-TW）
4. 不要用誇張的語氣詞（如「絕了」「狂」）

回傳純 JSON 陣列格式，例如：
["標題一", "標題二", "標題三"]
"""


async def generate_titles(
    llm: LLMClient,
    trends: list[TrendingQuery],
    category: str,
    count: int = 5,
    model: str = "claude-haiku-4-5",
) -> list[str]:
    """Generate video title candidates from trending queries.

    Falls back to raw trend queries if LLM fails.
    """
    queries_text = "\n".join(f"- {t.query}" for t in trends)

    user_prompt = _USER_PROMPT.format(
        category=category,
        queries=queries_text,
        count=count,
    )

    try:
        response = await llm.generate_text(
            system=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=model,
            max_tokens=500,
        )

        # Parse JSON array from response
        text = response.strip()
        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        titles = json.loads(text)

        if isinstance(titles, list) and all(isinstance(t, str) for t in titles):
            return titles[:count]

    except Exception:
        logger.warning(
            "Title generation failed, using raw trend queries",
            exc_info=True,
        )

    # Fallback: use raw trend queries as titles
    return [t.query for t in trends[:count]]
