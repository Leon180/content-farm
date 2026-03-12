"""Tests for trends module — client, title generator, handler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from content_farm.trends.client import TrendsClient, _CATEGORY_SEEDS
from content_farm.trends.handler import TrendingHandler
from content_farm.trends.schemas import TrendingQuery
from content_farm.trends.title_generator import generate_titles


# ---------------------------------------------------------------------------
# TrendingQuery schema
# ---------------------------------------------------------------------------


class TestTrendingQuery:
    def test_create(self) -> None:
        q = TrendingQuery(query="太空", category="science")
        assert q.query == "太空"
        assert q.category == "science"
        assert q.rising_percent is None

    def test_frozen(self) -> None:
        q = TrendingQuery(query="太空", category="science")
        with pytest.raises(Exception):
            q.query = "changed"  # type: ignore[misc]

    def test_with_rising_percent(self) -> None:
        q = TrendingQuery(query="AI", category="technology", rising_percent=500)
        assert q.rising_percent == 500


# ---------------------------------------------------------------------------
# TrendsClient
# ---------------------------------------------------------------------------


class TestTrendsClient:
    @pytest.mark.anyio()
    async def test_fallback_on_failure(self) -> None:
        client = TrendsClient()

        with patch.object(client, "_fetch_sync", side_effect=Exception("API error")):
            result = await client.get_trending("science")

        assert len(result) > 0
        assert all(isinstance(r, TrendingQuery) for r in result)
        assert result[0].category == "science"

    @pytest.mark.anyio()
    async def test_fallback_seeds_content(self) -> None:
        client = TrendsClient()
        result = client._fallback_seeds("science")

        expected = _CATEGORY_SEEDS["science"]
        assert len(result) == len(expected)
        assert [r.query for r in result] == expected

    @pytest.mark.anyio()
    async def test_fallback_unknown_category(self) -> None:
        client = TrendsClient()
        result = client._fallback_seeds("nonexistent")

        assert len(result) == 1
        assert result[0].query == "冷知識"

    @pytest.mark.anyio()
    async def test_successful_fetch(self) -> None:
        client = TrendsClient()
        mock_results = [
            TrendingQuery(query="量子電腦", category="science"),
            TrendingQuery(query="黑洞", category="science"),
        ]

        with patch.object(client, "_fetch_sync", return_value=mock_results):
            result = await client.get_trending("science")

        assert result == mock_results


# ---------------------------------------------------------------------------
# Title generator
# ---------------------------------------------------------------------------


class TestGenerateTitles:
    @pytest.mark.anyio()
    async def test_parses_json_response(self) -> None:
        llm = AsyncMock()
        llm.generate_text = AsyncMock(
            return_value='["標題一", "標題二", "標題三"]'
        )

        trends = [
            TrendingQuery(query="太空", category="science"),
            TrendingQuery(query="黑洞", category="science"),
        ]

        result = await generate_titles(llm, trends, "科學", count=3)

        assert result == ["標題一", "標題二", "標題三"]
        llm.generate_text.assert_called_once()

    @pytest.mark.anyio()
    async def test_strips_markdown_code_block(self) -> None:
        llm = AsyncMock()
        llm.generate_text = AsyncMock(
            return_value='```json\n["標題一", "標題二"]\n```'
        )

        trends = [TrendingQuery(query="太空", category="science")]
        result = await generate_titles(llm, trends, "科學", count=2)

        assert result == ["標題一", "標題二"]

    @pytest.mark.anyio()
    async def test_fallback_on_llm_error(self) -> None:
        llm = AsyncMock()
        llm.generate_text = AsyncMock(side_effect=Exception("API error"))

        trends = [
            TrendingQuery(query="太空", category="science"),
            TrendingQuery(query="黑洞", category="science"),
        ]

        result = await generate_titles(llm, trends, "科學", count=5)

        assert result == ["太空", "黑洞"]

    @pytest.mark.anyio()
    async def test_fallback_on_invalid_json(self) -> None:
        llm = AsyncMock()
        llm.generate_text = AsyncMock(return_value="not json at all")

        trends = [TrendingQuery(query="AI", category="technology")]
        result = await generate_titles(llm, trends, "科技", count=5)

        assert result == ["AI"]

    @pytest.mark.anyio()
    async def test_limits_to_count(self) -> None:
        llm = AsyncMock()
        llm.generate_text = AsyncMock(
            return_value='["a", "b", "c", "d", "e", "f", "g"]'
        )

        trends = [TrendingQuery(query="太空", category="science")]
        result = await generate_titles(llm, trends, "科學", count=3)

        assert len(result) == 3

    @pytest.mark.anyio()
    async def test_uses_correct_model(self) -> None:
        llm = AsyncMock()
        llm.generate_text = AsyncMock(return_value='["標題"]')

        trends = [TrendingQuery(query="太空", category="science")]
        await generate_titles(llm, trends, "科學", model="claude-haiku-4-5")

        call_kwargs = llm.generate_text.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# TrendingHandler
# ---------------------------------------------------------------------------


class TestTrendingHandler:
    @pytest.mark.anyio()
    async def test_fetch_and_present_success(self) -> None:
        bot = AsyncMock()
        bot.send_message = AsyncMock(return_value=1)
        bot.send_inline_keyboard = AsyncMock(return_value=1)

        trends_client = AsyncMock()
        trends_client.get_trending = AsyncMock(return_value=[
            TrendingQuery(query="太空", category="science"),
        ])

        llm = AsyncMock()

        handler = TrendingHandler(bot, trends_client, llm)

        with patch(
            "content_farm.trends.handler.generate_titles",
            new_callable=AsyncMock,
            return_value=["為什麼太空是黑色的", "宇宙有多大"],
        ):
            await handler.fetch_and_present("science", "科學")

        # Should have called send_inline_keyboard with title buttons
        bot.send_inline_keyboard.assert_called_once()
        text, buttons = bot.send_inline_keyboard.call_args.args
        assert "選擇影片主題" in text

        # Should have 2 title buttons + custom button
        assert len(buttons) == 3  # 2 titles + custom

        # Pending titles should be populated
        assert handler.pending_titles["0"] == "為什麼太空是黑色的"
        assert handler.pending_titles["1"] == "宇宙有多大"

    @pytest.mark.anyio()
    async def test_no_trends_shows_fallback(self) -> None:
        bot = AsyncMock()
        bot.send_message = AsyncMock(return_value=1)

        trends_client = AsyncMock()
        trends_client.get_trending = AsyncMock(return_value=[])

        llm = AsyncMock()

        handler = TrendingHandler(bot, trends_client, llm)
        await handler.fetch_and_present("science", "科學")

        calls = [c.args[0] for c in bot.send_message.call_args_list]
        assert any("暫時無法使用" in c for c in calls)

    @pytest.mark.anyio()
    async def test_title_generation_failure_shows_fallback(self) -> None:
        bot = AsyncMock()
        bot.send_message = AsyncMock(return_value=1)

        trends_client = AsyncMock()
        trends_client.get_trending = AsyncMock(return_value=[
            TrendingQuery(query="太空", category="science"),
        ])

        llm = AsyncMock()

        handler = TrendingHandler(bot, trends_client, llm)

        with patch(
            "content_farm.trends.handler.generate_titles",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await handler.fetch_and_present("science", "科學")

        calls = [c.args[0] for c in bot.send_message.call_args_list]
        assert any("標題生成失敗" in c for c in calls)

    @pytest.mark.anyio()
    async def test_long_title_truncated_in_button(self) -> None:
        bot = AsyncMock()
        bot.send_message = AsyncMock(return_value=1)
        bot.send_inline_keyboard = AsyncMock(return_value=1)

        trends_client = AsyncMock()
        trends_client.get_trending = AsyncMock(return_value=[
            TrendingQuery(query="太空", category="science"),
        ])

        llm = AsyncMock()
        long_title = "這是一個非常非常非常非常非常非常非常非常非常非常非常非常長的標題"

        handler = TrendingHandler(bot, trends_client, llm)

        with patch(
            "content_farm.trends.handler.generate_titles",
            new_callable=AsyncMock,
            return_value=[long_title],
        ):
            await handler.fetch_and_present("science", "科學")

        _, buttons = bot.send_inline_keyboard.call_args.args
        label = buttons[0][0][0]  # first row, first button, label
        assert len(label) <= 43  # 40 chars + "..."
        assert handler.pending_titles["0"] == long_title

    @pytest.mark.anyio()
    async def test_pending_titles_cleared_on_new_fetch(self) -> None:
        bot = AsyncMock()
        bot.send_message = AsyncMock(return_value=1)
        bot.send_inline_keyboard = AsyncMock(return_value=1)

        trends_client = AsyncMock()
        trends_client.get_trending = AsyncMock(return_value=[
            TrendingQuery(query="太空", category="science"),
        ])

        llm = AsyncMock()

        handler = TrendingHandler(bot, trends_client, llm)
        handler._pending_titles["old"] = "old title"

        with patch(
            "content_farm.trends.handler.generate_titles",
            new_callable=AsyncMock,
            return_value=["new title"],
        ):
            await handler.fetch_and_present("science", "科學")

        assert "old" not in handler.pending_titles
        assert "0" in handler.pending_titles
