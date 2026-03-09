"""Tests for TelegramBot — all httpx calls mocked."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from content_farm.telegram.bot import TelegramBot, _split_text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def bot() -> TelegramBot:
    return TelegramBot(token="fake-token", chat_id="12345")


_DUMMY_REQUEST = httpx.Request("GET", "https://api.telegram.org/test")


def _ok_response(result: dict | list | None = None) -> httpx.Response:
    """Build a fake 200 response from Telegram."""
    body = {"ok": True, "result": result or {}}
    return httpx.Response(200, json=body, request=_DUMMY_REQUEST)


def _message_response(message_id: int = 1) -> httpx.Response:
    return _ok_response({"message_id": message_id})


def _updates_response(updates: list[dict]) -> httpx.Response:
    return _ok_response(updates)


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------

class TestSendMessage:
    @pytest.mark.anyio()
    async def test_sends_correct_payload(self, bot: TelegramBot) -> None:
        bot._client.post = AsyncMock(return_value=_message_response(42))
        msg_id = await bot.send_message("hello")
        assert msg_id == 42
        bot._client.post.assert_called_once_with(
            "/sendMessage",
            json={"chat_id": "12345", "text": "hello"},
        )

    @pytest.mark.anyio()
    async def test_splits_long_text(self, bot: TelegramBot) -> None:
        long_text = "a" * 5000
        responses = [_message_response(1), _message_response(2)]
        bot._client.post = AsyncMock(side_effect=responses)
        msg_id = await bot.send_message(long_text)
        assert msg_id == 2
        assert bot._client.post.call_count == 2


# ---------------------------------------------------------------------------
# send_photo
# ---------------------------------------------------------------------------

class TestSendPhoto:
    @pytest.mark.anyio()
    async def test_sends_url(self, bot: TelegramBot) -> None:
        bot._client.post = AsyncMock(return_value=_message_response(10))
        msg_id = await bot.send_photo("https://example.com/photo.jpg", caption="test")
        assert msg_id == 10
        bot._client.post.assert_called_once()
        call_kwargs = bot._client.post.call_args
        assert call_kwargs.kwargs["json"]["photo"] == "https://example.com/photo.jpg"

    @pytest.mark.anyio()
    async def test_sends_file(self, bot: TelegramBot, tmp_path: Path) -> None:
        photo = tmp_path / "test.jpg"
        photo.write_bytes(b"\xff\xd8\xff\xe0")
        bot._client.post = AsyncMock(return_value=_message_response(11))
        msg_id = await bot.send_photo(photo, caption="file")
        assert msg_id == 11
        call_kwargs = bot._client.post.call_args
        assert "files" in call_kwargs.kwargs


# ---------------------------------------------------------------------------
# send_photos (media group)
# ---------------------------------------------------------------------------

class TestSendPhotos:
    @pytest.mark.anyio()
    async def test_sends_media_group(self, bot: TelegramBot) -> None:
        bot._client.post = AsyncMock(return_value=_ok_response([]))
        items = [("https://example.com/1.jpg", "cap1"), ("https://example.com/2.jpg", "cap2")]
        await bot.send_photos(items)
        bot._client.post.assert_called_once()
        call_kwargs = bot._client.post.call_args
        media = call_kwargs.kwargs["json"]["media"]
        assert len(media) == 2
        assert media[0]["caption"] == "cap1"

    @pytest.mark.anyio()
    async def test_batches_over_ten(self, bot: TelegramBot) -> None:
        bot._client.post = AsyncMock(return_value=_ok_response([]))
        items = [(f"https://example.com/{i}.jpg", f"cap{i}") for i in range(15)]
        await bot.send_photos(items)
        assert bot._client.post.call_count == 2


# ---------------------------------------------------------------------------
# wait_for_reply
# ---------------------------------------------------------------------------

class TestWaitForReply:
    @pytest.mark.anyio()
    async def test_returns_text_reply(self, bot: TelegramBot) -> None:
        flush_resp = _updates_response([])
        reply_resp = _updates_response([
            {
                "update_id": 100,
                "message": {
                    "chat": {"id": 12345},
                    "text": "ok",
                },
            }
        ])
        bot._client.get = AsyncMock(side_effect=[flush_resp, reply_resp])
        result = await bot.wait_for_reply(timeout_seconds=10)
        assert result == "ok"

    @pytest.mark.anyio()
    async def test_ignores_other_chats(self, bot: TelegramBot) -> None:
        flush_resp = _updates_response([])
        other_chat = _updates_response([
            {
                "update_id": 100,
                "message": {"chat": {"id": 99999}, "text": "hello"},
            }
        ])
        correct_chat = _updates_response([
            {
                "update_id": 101,
                "message": {"chat": {"id": 12345}, "text": "yes"},
            }
        ])
        bot._client.get = AsyncMock(side_effect=[flush_resp, other_chat, correct_chat])
        result = await bot.wait_for_reply(timeout_seconds=10)
        assert result == "yes"

    @pytest.mark.anyio()
    async def test_timeout_raises(self, bot: TelegramBot) -> None:
        flush_resp = _updates_response([])
        empty_resp = _updates_response([])
        bot._client.get = AsyncMock(return_value=empty_resp)
        # Override flush to return empty
        call_count = 0
        original_mono = time.monotonic

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return flush_resp
            return empty_resp

        bot._client.get = AsyncMock(side_effect=mock_get)

        with patch("content_farm.telegram.bot.time") as mock_time:
            # First call for flush, then deadline passed
            call_idx = 0

            def fake_monotonic():
                nonlocal call_idx
                call_idx += 1
                if call_idx <= 2:
                    return 0.0
                return 100.0  # past deadline

            mock_time.monotonic = fake_monotonic

            with pytest.raises(TimeoutError, match="No Telegram reply"):
                await bot.wait_for_reply(timeout_seconds=5)

    @pytest.mark.anyio()
    async def test_strips_whitespace(self, bot: TelegramBot) -> None:
        flush_resp = _updates_response([])
        reply_resp = _updates_response([
            {
                "update_id": 100,
                "message": {"chat": {"id": 12345}, "text": "  ok  \n"},
            }
        ])
        bot._client.get = AsyncMock(side_effect=[flush_resp, reply_resp])
        result = await bot.wait_for_reply(timeout_seconds=10)
        assert result == "ok"


# ---------------------------------------------------------------------------
# _split_text
# ---------------------------------------------------------------------------

class TestSplitText:
    def test_short_text_no_split(self) -> None:
        assert _split_text("hello", 4096) == ["hello"]

    def test_exact_boundary(self) -> None:
        text = "a" * 4096
        assert _split_text(text, 4096) == [text]

    def test_splits_at_newline(self) -> None:
        text = "a" * 4000 + "\n" + "b" * 200
        chunks = _split_text(text, 4096)
        assert len(chunks) == 2
        assert chunks[0] == "a" * 4000
        assert chunks[1] == "b" * 200

    def test_splits_at_max_if_no_newline(self) -> None:
        text = "a" * 5000
        chunks = _split_text(text, 4096)
        assert len(chunks) == 2
        assert len(chunks[0]) == 4096
        assert len(chunks[1]) == 904
