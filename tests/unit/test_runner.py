"""Tests for PipelineRunner — pipeline lifecycle manager."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from content_farm.telegram.runner import PipelineRunner


def _make_runner() -> tuple[PipelineRunner, AsyncMock, AsyncMock]:
    """Create runner with mock settings, dispatcher, and bot."""
    settings = MagicMock()
    settings.output_dir = "/tmp/test_output"
    settings.anthropic_api_key = MagicMock()
    settings.anthropic_api_key.get_secret_value.return_value = "test-key"

    dispatcher = AsyncMock()
    dispatcher.set_approval_queue = MagicMock()
    dispatcher.has_approval_queue = False
    dispatcher._approval_queue = None

    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=1)

    runner = PipelineRunner(settings, dispatcher, bot)
    return runner, dispatcher, bot


class TestIsRunning:
    def test_not_running_initially(self) -> None:
        runner, _, _ = _make_runner()
        assert not runner.is_running

    def test_not_running_when_task_is_none(self) -> None:
        runner, _, _ = _make_runner()
        runner._current_task = None
        assert not runner.is_running


class TestStatusSummary:
    def test_idle_status(self) -> None:
        runner, _, _ = _make_runner()
        assert "沒有執行中" in runner.status_summary

    def test_running_status(self) -> None:
        runner, _, _ = _make_runner()
        task = MagicMock()
        task.done.return_value = False
        runner._current_task = task
        runner._current_topic = "test topic"
        assert "test topic" in runner.status_summary


class TestStart:
    @pytest.mark.anyio()
    async def test_reject_if_already_running(self) -> None:
        runner, _, bot = _make_runner()
        task = MagicMock()
        task.done.return_value = False
        runner._current_task = task
        runner._current_topic = "existing"

        await runner.start("new topic")

        # Should send rejection message
        msg = bot.send_message.call_args.args[0]
        assert "正在執行中" in msg
        assert "existing" in msg

    @pytest.mark.anyio()
    async def test_start_creates_task(self) -> None:
        runner, dispatcher, bot = _make_runner()

        with patch.object(runner, "_run_pipeline", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = None
            await runner.start("test topic")

            assert runner._current_topic == "test topic"
            assert runner._current_task is not None
            dispatcher.set_approval_queue.assert_called_once()

            # Wait for task to complete
            await asyncio.sleep(0.05)


class TestCancel:
    @pytest.mark.anyio()
    async def test_cancel_when_not_running(self) -> None:
        runner, _, bot = _make_runner()
        await runner.cancel()

        msg = bot.send_message.call_args.args[0]
        assert "沒有執行中" in msg

    @pytest.mark.anyio()
    async def test_cancel_puts_sentinel_in_queue(self) -> None:
        runner, dispatcher, bot = _make_runner()

        queue: asyncio.Queue[dict] = asyncio.Queue()
        dispatcher.has_approval_queue = True
        dispatcher._approval_queue = queue

        task = MagicMock()
        task.done.return_value = False
        runner._current_task = task

        await runner.cancel()

        assert queue.qsize() == 1
        sentinel = await queue.get()
        assert sentinel.get("_cancel") is True


class TestOnDone:
    def test_cleanup_on_completion(self) -> None:
        runner, dispatcher, _ = _make_runner()
        runner._current_topic = "test"
        runner._current_run_id = "run_123"

        task = MagicMock()
        task.cancelled.return_value = False
        task.exception.return_value = None
        runner._current_task = task

        runner._on_done(task)

        assert runner._current_task is None
        assert runner._current_topic is None
        assert runner._current_run_id is None
        dispatcher.set_approval_queue.assert_called_once_with(None)

    def test_cleanup_on_failure(self) -> None:
        runner, dispatcher, _ = _make_runner()
        runner._current_topic = "test"

        task = MagicMock()
        task.cancelled.return_value = False
        task.exception.return_value = RuntimeError("test error")
        runner._current_task = task

        runner._on_done(task)

        assert runner._current_task is None
        dispatcher.set_approval_queue.assert_called_once_with(None)

    def test_cleanup_on_cancel(self) -> None:
        runner, dispatcher, _ = _make_runner()
        runner._current_topic = "test"

        task = MagicMock()
        task.cancelled.return_value = True
        runner._current_task = task

        runner._on_done(task)

        assert runner._current_task is None


class TestLastFailedRunId:
    def test_returns_none_when_no_failures(self) -> None:
        runner, _, _ = _make_runner()

        with patch("content_farm.telegram.runner.PipelineStateDB") as MockDB:
            db = MockDB.return_value
            db.list_runs.return_value = []
            db.close = MagicMock()

            result = runner.last_failed_run_id
            assert result is None

    def test_returns_first_failed_run(self) -> None:
        runner, _, _ = _make_runner()

        run1 = MagicMock()
        run1.status = "completed"
        run1.run_id = "run_1"

        run2 = MagicMock()
        run2.status = "failed"
        run2.run_id = "run_2"

        with patch("content_farm.telegram.runner.PipelineStateDB") as MockDB:
            db = MockDB.return_value
            db.list_runs.return_value = [run1, run2]
            db.close = MagicMock()

            result = runner.last_failed_run_id
            assert result == "run_2"
