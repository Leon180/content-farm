"""Tests for Telegram command handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from content_farm.telegram.handlers import (
    CATEGORIES,
    handle_cancel,
    handle_category_selection,
    handle_go,
    handle_retry,
    handle_runs,
    handle_status,
    handle_title_selection,
    handle_topics,
)


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=1)
    bot.send_inline_keyboard = AsyncMock(return_value=1)
    bot.answer_callback_query = AsyncMock()
    return bot


class TestHandleTopics:
    @pytest.mark.anyio()
    async def test_sends_category_keyboard(self) -> None:
        bot = _make_bot()
        update = {"message": {"text": "/topics"}}
        await handle_topics(update, bot)

        bot.send_inline_keyboard.assert_called_once()
        text, buttons = bot.send_inline_keyboard.call_args.args
        assert "分類" in text

        # Should have all categories in buttons
        all_labels = [label for row in buttons for label, _ in row]
        for label in CATEGORIES.values():
            assert label in all_labels


class TestHandleGo:
    @pytest.mark.anyio()
    async def test_starts_pipeline_with_topic(self) -> None:
        bot = _make_bot()
        runner = AsyncMock()
        update = {"message": {"text": "/go 為什麼天空是藍色的"}}
        await handle_go(update, bot, runner)

        runner.start.assert_called_once_with("為什麼天空是藍色的")

    @pytest.mark.anyio()
    async def test_missing_topic_shows_help(self) -> None:
        bot = _make_bot()
        runner = AsyncMock()
        update = {"message": {"text": "/go"}}
        await handle_go(update, bot, runner)

        runner.start.assert_not_called()
        bot.send_message.assert_called_once()
        assert "請提供主題" in bot.send_message.call_args.args[0]

    @pytest.mark.anyio()
    async def test_empty_topic_shows_help(self) -> None:
        bot = _make_bot()
        runner = AsyncMock()
        update = {"message": {"text": "/go   "}}
        await handle_go(update, bot, runner)

        runner.start.assert_not_called()


class TestHandleStatus:
    @pytest.mark.anyio()
    async def test_sends_runner_summary(self) -> None:
        bot = _make_bot()
        runner = MagicMock()
        runner.status_summary = "目前沒有執行中的 Pipeline。"
        update = {"message": {"text": "/status"}}
        await handle_status(update, bot, runner)

        bot.send_message.assert_called_once_with("目前沒有執行中的 Pipeline。")


class TestHandleRuns:
    @pytest.mark.anyio()
    async def test_no_runs_shows_message(self) -> None:
        bot = _make_bot()

        with patch("content_farm.telegram.handlers.PipelineStateDB") as MockDB:
            db = MockDB.return_value
            db.list_runs.return_value = []
            db.close = MagicMock()

            settings = MagicMock()
            settings.output_dir = "/tmp/test_output"
            update = {"message": {"text": "/runs"}}
            await handle_runs(update, bot, settings)

        bot.send_message.assert_called_once()
        assert "還沒有" in bot.send_message.call_args.args[0]

    @pytest.mark.anyio()
    async def test_with_runs_shows_list(self) -> None:
        bot = _make_bot()

        run = MagicMock()
        run.run_id = "abc123"
        run.topic = "test topic"
        run.status = "completed"
        run.completed_stages = ["script", "voice"]
        run.created_at = "2026-03-10T12:00:00"

        with patch("content_farm.telegram.handlers.PipelineStateDB") as MockDB:
            db = MockDB.return_value
            db.list_runs.return_value = [run]
            db.close = MagicMock()

            settings = MagicMock()
            settings.output_dir = "/tmp/test_output"
            update = {"message": {"text": "/runs"}}
            await handle_runs(update, bot, settings)

        msg = bot.send_message.call_args.args[0]
        assert "abc123" in msg
        assert "test topic" in msg


class TestHandleRetry:
    @pytest.mark.anyio()
    async def test_no_failed_run(self) -> None:
        bot = _make_bot()
        runner = MagicMock()
        runner.last_failed_run_id = None
        runner.resume = AsyncMock()
        update = {"message": {"text": "/retry"}}
        await handle_retry(update, bot, runner)

        bot.send_message.assert_called_once()
        assert "沒有找到" in bot.send_message.call_args.args[0]

    @pytest.mark.anyio()
    async def test_resumes_failed_run(self) -> None:
        bot = _make_bot()
        runner = MagicMock()
        runner.last_failed_run_id = "run_123"
        runner.resume = AsyncMock()
        update = {"message": {"text": "/retry"}}
        await handle_retry(update, bot, runner)

        runner.resume.assert_called_once_with("run_123")


class TestHandleCancel:
    @pytest.mark.anyio()
    async def test_cancels_pipeline(self) -> None:
        bot = _make_bot()
        runner = AsyncMock()
        update = {"message": {"text": "/cancel"}}
        await handle_cancel(update, bot, runner)

        runner.cancel.assert_called_once()


class TestHandleCategorySelection:
    @pytest.mark.anyio()
    async def test_fetches_trends_for_category(self) -> None:
        bot = _make_bot()
        trending_handler = AsyncMock()
        update = {"callback_query": {"id": "123", "data": "cat:science"}}
        await handle_category_selection(update, bot, trending_handler)

        bot.answer_callback_query.assert_called_once_with("123")
        trending_handler.fetch_and_present.assert_called_once_with("science", "科學")

    @pytest.mark.anyio()
    async def test_unknown_category_uses_key_as_name(self) -> None:
        bot = _make_bot()
        trending_handler = AsyncMock()
        update = {"callback_query": {"id": "123", "data": "cat:unknown"}}
        await handle_category_selection(update, bot, trending_handler)

        trending_handler.fetch_and_present.assert_called_once_with("unknown", "unknown")


class TestHandleTitleSelection:
    @pytest.mark.anyio()
    async def test_starts_pipeline_with_title(self) -> None:
        bot = _make_bot()
        runner = AsyncMock()
        pending = {"0": "為什麼飛機窗戶是圓的"}
        update = {"callback_query": {"id": "123", "data": "title:0"}}
        await handle_title_selection(update, bot, runner, pending)

        bot.answer_callback_query.assert_called_once()
        runner.start.assert_called_once_with("為什麼飛機窗戶是圓的")

    @pytest.mark.anyio()
    async def test_custom_title_sends_instructions(self) -> None:
        bot = _make_bot()
        runner = AsyncMock()
        pending: dict[str, str] = {}
        update = {"callback_query": {"id": "123", "data": "title:custom"}}
        await handle_title_selection(update, bot, runner, pending)

        runner.start.assert_not_called()
        bot.send_message.assert_called_once()
        assert "/go" in bot.send_message.call_args.args[0]

    @pytest.mark.anyio()
    async def test_missing_key_uses_key_as_title(self) -> None:
        bot = _make_bot()
        runner = AsyncMock()
        pending: dict[str, str] = {}
        update = {"callback_query": {"id": "123", "data": "title:99"}}
        await handle_title_selection(update, bot, runner, pending)

        runner.start.assert_called_once_with("99")
