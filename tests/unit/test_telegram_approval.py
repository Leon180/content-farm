"""Tests for ApprovalGate — Telegram-based approval checkpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.telegram.approval import (
    ApprovalGate,
    _apply_scene_edits,
    _apply_script_edits,
    _format_script,
    _is_approved,
    _parse_desc_edit,
    _parse_keyword_edits,
    _parse_scene_edits,
    _parse_title_edit,
)
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
    bot.send_inline_keyboard = AsyncMock(return_value=1)
    bot.send_photos = AsyncMock()
    bot.send_photo = AsyncMock(return_value=1)
    bot.send_video = AsyncMock(return_value=1)
    bot.wait_for_callback = AsyncMock(return_value="approve")
    bot.wait_for_reply = AsyncMock(return_value="")
    bot.edit_message_reply_markup = AsyncMock()
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
        assert "確認請按 Approve" in msgs[0]

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
        assert result.reply_text == "approve"
        # Last chunk sent via inline keyboard
        bot.send_inline_keyboard.assert_called_once()
        bot.wait_for_callback.assert_called_once()
        # Buttons removed after response
        bot.edit_message_reply_markup.assert_called_once()

    @pytest.mark.anyio()
    async def test_check_visuals_sends_summary(self) -> None:
        bot = _make_bot()
        gate = ApprovalGate(bot=bot)
        assets = _make_assets(2)
        result = await gate.check_visuals(assets)
        assert result.approved is True
        # Summary sent via inline keyboard
        sent_text = bot.send_inline_keyboard.call_args.args[0]
        assert "場景 1" in sent_text
        assert "場景 2" in sent_text
        assert "search term 1" in sent_text

    @pytest.mark.anyio()
    async def test_unrecognized_text_prompts_buttons(self) -> None:
        bot = _make_bot()
        # First callback is unrecognized text, second approved
        bot.wait_for_callback = AsyncMock(side_effect=["reject", "approve"])
        gate = ApprovalGate(bot=bot)
        result = await gate.check_script(_make_script())
        assert result.approved is True
        assert result.reply_text == "approve"
        # Should have sent button prompt
        calls = [c.args[0] for c in bot.send_message.call_args_list]
        assert any("請按 Approve 確認或 Edit 修改" in c for c in calls)

    @pytest.mark.anyio()
    async def test_multiple_unrecognized_before_approve(self) -> None:
        bot = _make_bot()
        bot.wait_for_callback = AsyncMock(
            side_effect=["reject", "不對", "approve"]
        )
        gate = ApprovalGate(bot=bot)
        result = await gate.check_script(_make_script())
        assert result.approved is True
        assert bot.wait_for_callback.call_count == 3

    @pytest.mark.anyio()
    async def test_check_visuals_with_thumbnail(self) -> None:
        bot = _make_bot()
        gate = ApprovalGate(bot=bot)
        assets = _make_assets(1)
        # Use a real temp file as thumbnail
        import tempfile
        from pathlib import Path
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake-jpg")
            thumb = Path(f.name)
        try:
            result = await gate.check_visuals(assets, thumbnail_path=thumb)
            assert result.approved is True
            bot.send_photo.assert_called_once()
        finally:
            thumb.unlink()

    @pytest.mark.anyio()
    async def test_notify_completion(self) -> None:
        bot = _make_bot()
        gate = ApprovalGate(bot=bot)
        await gate.notify_completion(
            video_path="/nonexistent/video.mp4",
            output_dir="/output/dir",
            upload_url="https://youtube.com/watch?v=xxx",
        )
        sent_text = bot.send_message.call_args.args[0]
        assert "Pipeline 完成" in sent_text
        assert "YouTube" in sent_text

    @pytest.mark.anyio()
    async def test_notify_failure(self) -> None:
        bot = _make_bot()
        gate = ApprovalGate(bot=bot)
        await gate.notify_failure(error="Something broke", run_id="run123")
        sent_text = bot.send_message.call_args.args[0]
        assert "Pipeline 失敗" in sent_text
        assert "run123" in sent_text
        assert "/continue" in sent_text

    @pytest.mark.anyio()
    async def test_notify_completion_none_bot(self) -> None:
        gate = ApprovalGate(bot=None)
        # Should not raise
        await gate.notify_completion(video_path="/v.mp4", output_dir="/out")

    @pytest.mark.anyio()
    async def test_notify_failure_none_bot(self) -> None:
        gate = ApprovalGate(bot=None)
        await gate.notify_failure(error="err")

    @pytest.mark.anyio()
    async def test_abort_command_raises(self) -> None:
        bot = _make_bot()
        bot.wait_for_callback = AsyncMock(return_value="/abort")
        gate = ApprovalGate(bot=bot)
        with pytest.raises(KeyboardInterrupt, match="Aborted"):
            await gate.check_script(_make_script())

    @pytest.mark.anyio()
    async def test_status_command_keeps_waiting(self) -> None:
        bot = _make_bot()
        # /status first, then approve
        bot.wait_for_callback = AsyncMock(side_effect=["/status", "approve"])
        gate = ApprovalGate(bot=bot)
        result = await gate.check_script(_make_script())
        assert result.approved is True
        # Should have sent status reply
        calls = [c.args[0] for c in bot.send_message.call_args_list]
        assert any("等待腳本審核中" in c for c in calls)

    @pytest.mark.anyio()
    async def test_edit_button_triggers_edit_flow(self) -> None:
        bot = _make_bot()
        # User clicks Edit, sends edit text (via wait_for_callback), then approves re-sent
        bot.wait_for_callback = AsyncMock(
            side_effect=["edit", "場景1：修改後的旁白", "approve"],
        )
        gate = ApprovalGate(bot=bot)
        script = _make_script(scene_count=2)
        result = await gate.check_script(script)
        assert result.approved is True
        # The edited script should have been applied
        assert result.edited_script is not None
        assert result.edited_script.scenes[0].narration == "修改後的旁白"
        # Scene 2 unchanged
        assert result.edited_script.scenes[1].narration == "旁白內容2"

    @pytest.mark.anyio()
    async def test_edit_button_invalid_format_retries(self) -> None:
        bot = _make_bot()
        # Edit → invalid text (via wait_for_callback) → retry → approve
        bot.wait_for_callback = AsyncMock(
            side_effect=["edit", "garbage text no scene format", "approve"],
        )
        gate = ApprovalGate(bot=bot)
        result = await gate.check_script(_make_script())
        assert result.approved is True
        calls = [c.args[0] for c in bot.send_message.call_args_list]
        assert any("無法解析" in c for c in calls)

    @pytest.mark.anyio()
    async def test_direct_scene_edit_text(self) -> None:
        bot = _make_bot()
        # User sends scene edit directly (no Edit button)
        bot.wait_for_callback = AsyncMock(
            side_effect=["場景1：直接修改", "approve"]
        )
        gate = ApprovalGate(bot=bot)
        script = _make_script(scene_count=2)
        result = await gate.check_script(script)
        assert result.approved is True
        assert result.edited_script is not None
        assert result.edited_script.scenes[0].narration == "直接修改"

    @pytest.mark.anyio()
    async def test_deliver_materials(self) -> None:
        bot = _make_bot()
        gate = ApprovalGate(bot=bot)
        script = _make_script(scene_count=2)
        await gate.deliver_materials(script, "https://drive.google.com/test")
        calls = [c.args[0] for c in bot.send_message.call_args_list]
        assert any("Google Drive" in c for c in calls)
        assert any("腳本" in c for c in calls)
        assert any("分鏡稿" in c for c in calls)

    @pytest.mark.anyio()
    async def test_deliver_materials_none_bot(self) -> None:
        gate = ApprovalGate(bot=None)
        await gate.deliver_materials(_make_script(), "https://link")


# ---------------------------------------------------------------------------
# _parse_scene_edits / _apply_scene_edits
# ---------------------------------------------------------------------------

class TestParseSceneEdits:
    def test_single_edit(self) -> None:
        edits = _parse_scene_edits("場景1：新的旁白")
        assert edits == {1: "新的旁白"}

    def test_multiple_edits(self) -> None:
        text = "場景1：旁白A\n場景2：旁白B"
        edits = _parse_scene_edits(text)
        assert edits == {1: "旁白A", 2: "旁白B"}

    def test_colon_variants(self) -> None:
        edits = _parse_scene_edits("場景1:半形冒號")
        assert edits == {1: "半形冒號"}

    def test_spaces_around_number(self) -> None:
        edits = _parse_scene_edits("場景 1 ：有空格")
        assert edits == {1: "有空格"}

    def test_empty_text(self) -> None:
        assert _parse_scene_edits("") == {}

    def test_no_match(self) -> None:
        assert _parse_scene_edits("隨便寫一些東西") == {}


class TestApplySceneEdits:
    def test_applies_edits(self) -> None:
        script = _make_script(scene_count=2)
        edited = _apply_scene_edits({1: "新旁白"}, script)
        assert edited is not None
        assert edited.scenes[0].narration == "新旁白"
        assert edited.scenes[1].narration == "旁白內容2"

    def test_no_matching_scene(self) -> None:
        script = _make_script(scene_count=1)
        result = _apply_scene_edits({99: "不存在"}, script)
        assert result is None

    def test_empty_edits(self) -> None:
        result = _apply_scene_edits({}, _make_script())
        assert result is None

    def test_preserves_other_fields(self) -> None:
        script = _make_script(scene_count=1)
        edited = _apply_scene_edits({1: "新"}, script)
        assert edited is not None
        assert edited.video_title == script.video_title
        assert edited.language == script.language
        assert edited.scenes[0].title == script.scenes[0].title


class TestApplyScriptEdits:
    def test_end_to_end(self) -> None:
        script = _make_script(scene_count=2)
        result = _apply_script_edits("場景2：修改後", script)
        assert result is not None
        assert result.scenes[1].narration == "修改後"
        assert result.scenes[0].narration == "旁白內容1"

    def test_invalid_text_returns_none(self) -> None:
        result = _apply_script_edits("no scene pattern", _make_script())
        assert result is None

    def test_title_only(self) -> None:
        script = _make_script()
        result = _apply_script_edits("標題：新標題", script)
        assert result is not None
        assert result.video_title == "新標題"
        assert result.description == script.description

    def test_description_only(self) -> None:
        script = _make_script()
        result = _apply_script_edits("描述：新描述", script)
        assert result is not None
        assert result.description == "新描述"
        assert result.video_title == script.video_title

    def test_title_and_scenes(self) -> None:
        script = _make_script(scene_count=2)
        result = _apply_script_edits("標題：新標題\n場景1：新旁白", script)
        assert result is not None
        assert result.video_title == "新標題"
        assert result.scenes[0].narration == "新旁白"
        assert result.scenes[1].narration == "旁白內容2"

    def test_all_fields(self) -> None:
        script = _make_script(scene_count=1)
        text = "標題：改標題\n描述：改描述\n場景1：改旁白"
        result = _apply_script_edits(text, script)
        assert result is not None
        assert result.video_title == "改標題"
        assert result.description == "改描述"
        assert result.scenes[0].narration == "改旁白"

    def test_preserves_sources(self) -> None:
        script = Script(
            video_title="T",
            description="D",
            language="zh-TW",
            scenes=_make_script(scene_count=1).scenes,
            sources=("來源1", "來源2"),
        )
        result = _apply_script_edits("標題：新標題", script)
        assert result is not None
        assert result.sources == ("來源1", "來源2")


# ---------------------------------------------------------------------------
# _parse_title_edit / _parse_desc_edit
# ---------------------------------------------------------------------------

class TestParseTitleEdit:
    def test_basic(self) -> None:
        assert _parse_title_edit("標題：新標題") == "新標題"

    def test_half_width_colon(self) -> None:
        assert _parse_title_edit("標題:半形") == "半形"

    def test_with_spaces(self) -> None:
        assert _parse_title_edit("標題 ： 有空格 ") == "有空格"

    def test_no_match(self) -> None:
        assert _parse_title_edit("場景1：旁白") is None

    def test_empty_value(self) -> None:
        assert _parse_title_edit("標題：") is None

    def test_stops_at_scene(self) -> None:
        result = _parse_title_edit("標題：新標題\n場景1：旁白")
        assert result == "新標題"

    def test_stops_at_description(self) -> None:
        result = _parse_title_edit("標題：新標題\n描述：新描述")
        assert result == "新標題"


class TestParseDescEdit:
    def test_basic(self) -> None:
        assert _parse_desc_edit("描述：新描述") == "新描述"

    def test_no_match(self) -> None:
        assert _parse_desc_edit("場景1：旁白") is None

    def test_stops_at_scene(self) -> None:
        result = _parse_desc_edit("描述：新描述\n場景1：旁白")
        assert result == "新描述"


# ---------------------------------------------------------------------------
# _format_script — sources display
# ---------------------------------------------------------------------------

class TestFormatScriptSources:
    def test_no_sources(self) -> None:
        script = _make_script(scene_count=1)
        msgs = _format_script(script)
        assert all("參考來源" not in m for m in msgs)

    def test_with_sources(self) -> None:
        script = Script(
            video_title="T",
            description="D",
            language="zh-TW",
            scenes=_make_script(scene_count=1).scenes,
            sources=("來源A", "來源B"),
        )
        msgs = _format_script(script)
        text = "\n".join(msgs)
        assert "參考來源" in text
        assert "來源A" in text
        assert "來源B" in text


# ---------------------------------------------------------------------------
# Keyword display + editing
# ---------------------------------------------------------------------------

def _make_script_with_keywords(
    keywords: tuple[str, ...] = ("airplane", "window", "round"),
) -> Script:
    scenes = (
        Scene(
            scene_number=1,
            title="場景1",
            narration="旁白1",
            visual_hint=VisualHint(description="stock", keywords=keywords),
            duration_seconds=10,
        ),
        Scene(
            scene_number=2,
            title="場景2",
            narration="旁白2",
            visual_hint=VisualHint(description="stock", keywords=("ocean", "wave")),
            duration_seconds=10,
        ),
    )
    return Script(
        video_title="T",
        description="D",
        language="zh-TW",
        scenes=scenes,
    )


class TestFormatScriptKeywords:
    def test_keywords_displayed(self) -> None:
        script = _make_script_with_keywords()
        msgs = _format_script(script)
        text = "\n".join(msgs)
        assert "Keywords: airplane, window, round" in text
        assert "Keywords: ocean, wave" in text

    def test_no_keywords_no_line(self) -> None:
        script = _make_script(scene_count=1)
        msgs = _format_script(script)
        text = "\n".join(msgs)
        assert "Keywords:" not in text


class TestParseKeywordEdits:
    def test_single(self) -> None:
        edits = _parse_keyword_edits("場景1關鍵字：cat, dog, fish")
        assert edits == {1: ("cat", "dog", "fish")}

    def test_multiple(self) -> None:
        text = "場景1關鍵字：cat, dog\n場景2關鍵字：ocean, wave"
        edits = _parse_keyword_edits(text)
        assert edits == {1: ("cat", "dog"), 2: ("ocean", "wave")}

    def test_half_width_colon(self) -> None:
        edits = _parse_keyword_edits("場景1關鍵字:a, b")
        assert edits == {1: ("a", "b")}

    def test_spaces(self) -> None:
        edits = _parse_keyword_edits("場景 1 關鍵字 ： x , y ")
        assert edits == {1: ("x", "y")}

    def test_no_match(self) -> None:
        assert _parse_keyword_edits("場景1：旁白") == {}

    def test_empty(self) -> None:
        assert _parse_keyword_edits("") == {}

    def test_mixed_with_scene_edit(self) -> None:
        text = "場景1：新旁白\n場景1關鍵字：sunset, beach"
        scene_edits = _parse_scene_edits(text)
        kw_edits = _parse_keyword_edits(text)
        assert scene_edits == {1: "新旁白"}
        assert kw_edits == {1: ("sunset", "beach")}


class TestApplyKeywordEdits:
    def test_keyword_only_edit(self) -> None:
        script = _make_script_with_keywords()
        edited = _apply_scene_edits(
            {}, script, keyword_edits={1: ("new", "keywords")},
        )
        assert edited is not None
        assert edited.scenes[0].visual_hint.keywords == ("new", "keywords")
        # Narration unchanged
        assert edited.scenes[0].narration == "旁白1"
        # Scene 2 unchanged
        assert edited.scenes[1].visual_hint.keywords == ("ocean", "wave")

    def test_narration_and_keyword_edit(self) -> None:
        script = _make_script_with_keywords()
        edited = _apply_scene_edits(
            {1: "新旁白"},
            script,
            keyword_edits={2: ("space", "star")},
        )
        assert edited is not None
        assert edited.scenes[0].narration == "新旁白"
        assert edited.scenes[1].visual_hint.keywords == ("space", "star")

    def test_apply_script_edits_with_keywords(self) -> None:
        script = _make_script_with_keywords()
        text = "場景1關鍵字：sun, moon\n場景2：新旁白"
        result = _apply_script_edits(text, script)
        assert result is not None
        assert result.scenes[0].visual_hint.keywords == ("sun", "moon")
        assert result.scenes[1].narration == "新旁白"

    def test_keyword_edit_preserves_hint_fields(self) -> None:
        script = Script(
            video_title="T",
            description="D",
            language="zh-TW",
            scenes=(
                Scene(
                    scene_number=1,
                    title="s1",
                    narration="n1",
                    visual_hint=VisualHint(
                        description="desc",
                        style="ai_image",
                        keywords=("old",),
                        source_preference="ai",
                    ),
                    duration_seconds=10,
                ),
            ),
        )
        edited = _apply_scene_edits(
            {}, script, keyword_edits={1: ("new",)},
        )
        assert edited is not None
        hint = edited.scenes[0].visual_hint
        assert hint.keywords == ("new",)
        assert hint.description == "desc"
        assert hint.style == "ai_image"
        assert hint.source_preference == "ai"


class TestDirectKeywordEdit:
    @pytest.mark.anyio()
    async def test_direct_keyword_edit(self) -> None:
        bot = _make_bot()
        # User directly sends keyword edit, then approves
        bot.wait_for_callback = AsyncMock(
            side_effect=["場景1關鍵字：sunset, beach", "approve"],
        )
        gate = ApprovalGate(bot=bot)
        script = _make_script_with_keywords()
        result = await gate.check_script(script)
        assert result.approved is True
        assert result.edited_script is not None
        assert result.edited_script.scenes[0].visual_hint.keywords == ("sunset", "beach")
