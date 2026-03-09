"""Tests for ApprovalGate — Telegram-based approval checkpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.telegram.approval import ApprovalGate, _format_script, _is_approved
from content_farm.telegram.bot import TelegramBot
from content_farm.telegram.schemas import ApprovalResult
from content_farm.visual.schemas import VisualAsset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_script(
    title: str = "測試標題",
    scene_count: int = 2,
) -> Script:
    scenes = tuple(
        Scene(
            scene_number=i + 1,
            title=f"場景{i + 1}",
            narration=f"旁白內容{i + 1}",
            visual_hint=VisualHint(description="stock"),
            duration_seconds=10,
        )
        for i in range(scene_count)
    )
    return Script(
        video_title=title,
        description="測試描述",
        language="zh-TW",
        scenes=scenes,
    )


def _make_assets(count: int = 3) -> tuple[VisualAsset, ...]:
    return tuple(
        VisualAsset(
            scene_number=i + 1,
            file_path=f"/tmp/scene_{i + 1}.mp4",
            source="pexels",
            duration_seconds=10.5,
            query_used=f"search term {i + 1}",
        )
        for i in range(count)
    )


def _make_bot() -> TelegramBot:
    bot = TelegramBot(token="fake", chat_id="12345")
    bot.send_message = AsyncMock(return_value=1)
    bot.send_photos = AsyncMock()
    bot.wait_for_reply = AsyncMock(return_value="ok")
    return bot


# ---------------------------------------------------------------------------
# _is_approved
# ---------------------------------------------------------------------------

class TestIsApproved:
    @pytest.mark.parametrize(
        "text",
        ["ok", "OK", "Ok", "好", "通過", "可以", "沒問題", "没问题", "確認", "确认"],
    )
    def test_approved_keywords(self, text: str) -> None:
        assert _is_approved(text) is True

    @pytest.mark.parametrize(
        "text",
        ["ok 我覺得不錯", "OK fine", "好的繼續"],
    )
    def test_approved_prefix_match(self, text: str) -> None:
        assert _is_approved(text) is True

    @pytest.mark.parametrize(
        "text",
        ["不好", "修改一下", "no", "需要調整", "重做"],
    )
    def test_rejected(self, text: str) -> None:
        assert _is_approved(text) is False

    def test_whitespace_stripped(self) -> None:
        assert _is_approved("  ok  ") is True

    def test_empty_string(self) -> None:
        assert _is_approved("") is False


# ---------------------------------------------------------------------------
# _format_script
# ---------------------------------------------------------------------------

class TestFormatScript:
    def test_single_message_for_short_script(self) -> None:
        script = _make_script(scene_count=2)
        msgs = _format_script(script)
        assert len(msgs) == 1
        assert "【腳本審核】" in msgs[0]
        assert "測試標題" in msgs[0]
        assert "場景 1" in msgs[0]
        assert "場景 2" in msgs[0]
        assert "確認請回覆 ok" in msgs[0]

    def test_splits_long_script(self) -> None:
        # Create a script with enough scenes to exceed 4096 chars
        scenes = tuple(
            Scene(
                scene_number=i + 1,
                title=f"超長場景標題{i + 1}",
                narration="長旁白 " * 200,
                visual_hint=VisualHint(description="stock"),
                duration_seconds=30,
            )
            for i in range(10)
        )
        script = Script(
            video_title="很長的腳本",
            description="描述",
            language="zh-TW",
            scenes=scenes,
        )
        msgs = _format_script(script)
        assert len(msgs) > 1
        for msg in msgs:
            assert len(msg) <= 4096

    def test_includes_scene_details(self) -> None:
        script = _make_script(scene_count=1)
        msgs = _format_script(script)
        text = msgs[0]
        assert "場景 1：場景1" in text
        assert "旁白內容1" in text
        assert "10s" in text


# ---------------------------------------------------------------------------
# ApprovalGate — None bot (auto-approve)
# ---------------------------------------------------------------------------

class TestApprovalGateNone:
    @pytest.mark.anyio()
    async def test_check_script_auto_approves(self) -> None:
        gate = ApprovalGate(bot=None)
        result = await gate.check_script(_make_script())
        assert result.approved is True
        assert result.reply_text == "auto-approved"

    @pytest.mark.anyio()
    async def test_check_visuals_auto_approves(self) -> None:
        gate = ApprovalGate(bot=None)
        result = await gate.check_visuals(_make_assets())
        assert result.approved is True
        assert result.reply_text == "auto-approved"


# ---------------------------------------------------------------------------
# ApprovalGate — with bot
# ---------------------------------------------------------------------------

class TestApprovalGateWithBot:
    @pytest.mark.anyio()
    async def test_check_script_sends_and_waits(self) -> None:
        bot = _make_bot()
        gate = ApprovalGate(bot=bot)
        result = await gate.check_script(_make_script())
        assert result.approved is True
        assert result.reply_text == "ok"
        assert bot.send_message.call_count >= 1
        bot.wait_for_reply.assert_called_once()

    @pytest.mark.anyio()
    async def test_check_visuals_sends_summary(self) -> None:
        bot = _make_bot()
        gate = ApprovalGate(bot=bot)
        assets = _make_assets(2)
        result = await gate.check_visuals(assets)
        assert result.approved is True
        # Check the message contains scene info
        sent_text = bot.send_message.call_args_list[0].args[0]
        assert "場景 1" in sent_text
        assert "場景 2" in sent_text
        assert "search term 1" in sent_text

    @pytest.mark.anyio()
    async def test_rejection_sends_instructions(self) -> None:
        bot = _make_bot()
        # First reply rejected, second approved
        bot.wait_for_reply = AsyncMock(side_effect=["不好，重做", "ok"])
        gate = ApprovalGate(bot=bot)
        result = await gate.check_script(_make_script())
        assert result.approved is True
        assert result.reply_text == "ok"
        # Should have sent rejection reply
        calls = [c.args[0] for c in bot.send_message.call_args_list]
        assert any("修改完成後回覆 ok" in c for c in calls)

    @pytest.mark.anyio()
    async def test_multiple_rejections_before_approve(self) -> None:
        bot = _make_bot()
        bot.wait_for_reply = AsyncMock(
            side_effect=["改一下", "還是不對", "ok"]
        )
        gate = ApprovalGate(bot=bot)
        result = await gate.check_script(_make_script())
        assert result.approved is True
        assert bot.wait_for_reply.call_count == 3
