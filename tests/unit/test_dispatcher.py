"""Tests for UpdateDispatcher — central polling loop and routing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from content_farm.telegram.dispatcher import UpdateDispatcher


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.flush_updates = AsyncMock(return_value=0)
    bot.get_updates = AsyncMock(return_value=([], 0))
    bot.send_message = AsyncMock(return_value=1)
    return bot


class TestRouting:
    """Test _route dispatching logic."""

    @pytest.mark.anyio()
    async def test_command_routed_to_handler(self) -> None:
        bot = _make_bot()
        dispatcher = UpdateDispatcher(bot)
        handler = AsyncMock()
        dispatcher.register_command("/test", handler)

        update = {"message": {"text": "/test"}}
        await dispatcher._route(update)

        handler.assert_called_once_with(update)

    @pytest.mark.anyio()
    async def test_command_with_args_routed(self) -> None:
        bot = _make_bot()
        dispatcher = UpdateDispatcher(bot)
        handler = AsyncMock()
        dispatcher.register_command("/go", handler)

        update = {"message": {"text": "/go some topic"}}
        await dispatcher._route(update)

        handler.assert_called_once_with(update)

    @pytest.mark.anyio()
    async def test_callback_prefix_routed(self) -> None:
        bot = _make_bot()
        dispatcher = UpdateDispatcher(bot)
        handler = AsyncMock()
        dispatcher.register_callback_prefix("cat:", handler)

        update = {"callback_query": {"data": "cat:science"}}
        await dispatcher._route(update)

        handler.assert_called_once_with(update)

    @pytest.mark.anyio()
    async def test_callback_no_prefix_forwarded_to_queue(self) -> None:
        bot = _make_bot()
        dispatcher = UpdateDispatcher(bot)
        queue: asyncio.Queue[dict] = asyncio.Queue()
        dispatcher.set_approval_queue(queue)

        update = {"callback_query": {"data": "approve"}}
        await dispatcher._route(update)

        assert queue.qsize() == 1
        assert (await queue.get()) == update

    @pytest.mark.anyio()
    async def test_callback_no_queue_ignored(self) -> None:
        bot = _make_bot()
        dispatcher = UpdateDispatcher(bot)

        update = {"callback_query": {"data": "approve"}}
        await dispatcher._route(update)

        # No error, no message sent
        bot.send_message.assert_not_called()

    @pytest.mark.anyio()
    async def test_text_forwarded_to_approval_queue(self) -> None:
        bot = _make_bot()
        dispatcher = UpdateDispatcher(bot)
        queue: asyncio.Queue[dict] = asyncio.Queue()
        dispatcher.set_approval_queue(queue)

        update = {"message": {"text": "some text"}}
        await dispatcher._route(update)

        assert queue.qsize() == 1

    @pytest.mark.anyio()
    async def test_unrecognized_text_sends_help(self) -> None:
        bot = _make_bot()
        dispatcher = UpdateDispatcher(bot)

        update = {"message": {"text": "hello"}}
        await dispatcher._route(update)

        bot.send_message.assert_called_once()
        assert "可用指令" in bot.send_message.call_args.args[0]

    @pytest.mark.anyio()
    async def test_unrecognized_command_no_help_during_pipeline(self) -> None:
        bot = _make_bot()
        dispatcher = UpdateDispatcher(bot)
        queue: asyncio.Queue[dict] = asyncio.Queue()
        dispatcher.set_approval_queue(queue)

        update = {"message": {"text": "/unknown"}}
        await dispatcher._route(update)

        # Unknown command with no handler should NOT send help when queue is set
        # It should not be forwarded to queue either (starts with /)
        bot.send_message.assert_not_called()

    @pytest.mark.anyio()
    async def test_empty_text_not_forwarded(self) -> None:
        bot = _make_bot()
        dispatcher = UpdateDispatcher(bot)
        queue: asyncio.Queue[dict] = asyncio.Queue()
        dispatcher.set_approval_queue(queue)

        update = {"message": {"text": ""}}
        await dispatcher._route(update)

        assert queue.qsize() == 0

    @pytest.mark.anyio()
    async def test_command_case_insensitive(self) -> None:
        bot = _make_bot()
        dispatcher = UpdateDispatcher(bot)
        handler = AsyncMock()
        dispatcher.register_command("/status", handler)

        update = {"message": {"text": "/Status"}}
        await dispatcher._route(update)

        handler.assert_called_once()


class TestPollingLoop:
    """Test the run() polling loop."""

    @pytest.mark.anyio()
    async def test_stop_ends_loop(self) -> None:
        bot = _make_bot()
        dispatcher = UpdateDispatcher(bot)

        # After first poll, stop
        call_count = 0

        async def fake_get_updates(offset: int, timeout: int = 30):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                dispatcher.stop()
            return [], offset

        bot.get_updates = fake_get_updates

        await dispatcher.run()
        assert call_count >= 2
        bot.flush_updates.assert_called_once()

    @pytest.mark.anyio()
    async def test_polling_error_retries(self) -> None:
        bot = _make_bot()
        dispatcher = UpdateDispatcher(bot)

        call_count = 0

        async def fake_get_updates(offset: int, timeout: int = 30):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("network error")
            dispatcher.stop()
            return [], offset

        bot.get_updates = fake_get_updates

        # Patch sleep to avoid actual waiting
        original_sleep = asyncio.sleep
        asyncio.sleep = AsyncMock()
        try:
            await dispatcher.run()
        finally:
            asyncio.sleep = original_sleep  # type: ignore[assignment]

        assert call_count >= 2


class TestApprovalQueue:
    """Test approval queue management."""

    def test_set_and_clear_queue(self) -> None:
        bot = _make_bot()
        dispatcher = UpdateDispatcher(bot)

        assert not dispatcher.has_approval_queue

        queue: asyncio.Queue[dict] = asyncio.Queue()
        dispatcher.set_approval_queue(queue)
        assert dispatcher.has_approval_queue

        dispatcher.set_approval_queue(None)
        assert not dispatcher.has_approval_queue
