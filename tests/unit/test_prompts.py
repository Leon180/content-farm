"""Tests for prompt templates."""

from __future__ import annotations

from content_farm.script_gen.prompts import (
    SYSTEM_PROMPT,
    build_outline_prompt,
    build_scene_narration_prompt,
)
from content_farm.script_gen.schemas import ScriptRequest
from content_farm.types import Tone, VideoLength


class TestBuildOutlinePrompt:
    def test_includes_topic(self) -> None:
        req = ScriptRequest(topic="How Bitcoin Works")
        prompt = build_outline_prompt(req)
        assert "How Bitcoin Works" in prompt

    def test_includes_keywords(self) -> None:
        req = ScriptRequest(topic="Test", keywords=["crypto", "blockchain"])
        prompt = build_outline_prompt(req)
        assert "crypto" in prompt
        assert "blockchain" in prompt

    def test_includes_tone(self) -> None:
        req = ScriptRequest(topic="Test", tone=Tone.DRAMATIC)
        prompt = build_outline_prompt(req)
        assert "dramatic" in prompt

    def test_scene_count_for_short(self) -> None:
        req = ScriptRequest(topic="Test", video_length=VideoLength.SHORT)
        prompt = build_outline_prompt(req)
        assert "between 2 and 3" in prompt

    def test_scene_count_for_medium(self) -> None:
        req = ScriptRequest(topic="Test", video_length=VideoLength.MEDIUM)
        prompt = build_outline_prompt(req)
        assert "between 6 and 10" in prompt

    def test_scene_count_for_long(self) -> None:
        req = ScriptRequest(topic="Test", video_length=VideoLength.LONG)
        prompt = build_outline_prompt(req)
        assert "between 10 and 18" in prompt

    def test_no_keywords(self) -> None:
        req = ScriptRequest(topic="Test")
        prompt = build_outline_prompt(req)
        assert "none specified" in prompt

    def test_short_form_guide_included(self) -> None:
        req = ScriptRequest(topic="Test", video_length=VideoLength.SHORT)
        prompt = build_outline_prompt(req)
        assert "50-65" in prompt
        assert "Hook" in prompt
        assert "反轉" in prompt

    def test_short_form_narrative_structures(self) -> None:
        req = ScriptRequest(topic="Test", video_length=VideoLength.SHORT)
        prompt = build_outline_prompt(req)
        assert "懸念揭曉型" in prompt
        assert "誤導反轉型" in prompt
        assert "層層遞進型" in prompt

    def test_short_form_guide_not_in_medium(self) -> None:
        req = ScriptRequest(topic="Test", video_length=VideoLength.MEDIUM)
        prompt = build_outline_prompt(req)
        assert "SHORT-FORM" not in prompt


class TestBuildSceneNarrationPrompt:
    def test_opening_hook_position(self) -> None:
        prompt = build_scene_narration_prompt(
            topic="Test",
            tone="educational",
            language="zh-TW",
            scene_title="Intro",
            scene_summary="Opening",
            scene_number=1,
            total_scenes=5,
            duration_seconds=30,
        )
        assert "opening hook" in prompt

    def test_closing_position(self) -> None:
        prompt = build_scene_narration_prompt(
            topic="Test",
            tone="educational",
            language="zh-TW",
            scene_title="Outro",
            scene_summary="Closing",
            scene_number=5,
            total_scenes=5,
            duration_seconds=30,
        )
        assert "closing/CTA" in prompt

    def test_body_position(self) -> None:
        prompt = build_scene_narration_prompt(
            topic="Test",
            tone="educational",
            language="zh-TW",
            scene_title="Middle",
            scene_summary="Content",
            scene_number=3,
            total_scenes=5,
            duration_seconds=30,
        )
        assert "body" in prompt

    def test_includes_duration(self) -> None:
        prompt = build_scene_narration_prompt(
            topic="Test",
            tone="educational",
            language="en",
            scene_title="Title",
            scene_summary="Summary",
            scene_number=1,
            total_scenes=1,
            duration_seconds=45,
        )
        assert "45 seconds" in prompt

    def test_short_form_narration_guide(self) -> None:
        prompt = build_scene_narration_prompt(
            topic="Test",
            tone="educational",
            language="zh-TW",
            scene_title="Hook",
            scene_summary="Opening hook",
            scene_number=1,
            total_scenes=3,
            duration_seconds=20,
            is_short_form=True,
        )
        assert "55-70" in prompt
        assert "好奇缺口" in prompt
        assert "開放迴圈" in prompt

    def test_short_form_opening_has_hook_techniques(self) -> None:
        prompt = build_scene_narration_prompt(
            topic="Test",
            tone="educational",
            language="zh-TW",
            scene_title="Hook",
            scene_summary="Opening",
            scene_number=1,
            total_scenes=3,
            duration_seconds=20,
            is_short_form=True,
        )
        assert "挑戰認知" in prompt
        assert "前 2 秒" in prompt

    def test_short_form_closing_no_cta(self) -> None:
        prompt = build_scene_narration_prompt(
            topic="Test",
            tone="educational",
            language="zh-TW",
            scene_title="Ending",
            scene_summary="Conclusion",
            scene_number=3,
            total_scenes=3,
            duration_seconds=20,
            is_short_form=True,
        )
        assert "反轉結尾" in prompt
        assert "回扣開頭" in prompt
        assert "不要用 CTA" in prompt

    def test_short_form_body_has_open_loop(self) -> None:
        prompt = build_scene_narration_prompt(
            topic="Test",
            tone="educational",
            language="zh-TW",
            scene_title="Middle",
            scene_summary="Explanation",
            scene_number=2,
            total_scenes=3,
            duration_seconds=25,
            is_short_form=True,
        )
        assert "開放迴圈" in prompt
        assert "情緒轉折" in prompt

    def test_short_form_includes_example(self) -> None:
        prompt = build_scene_narration_prompt(
            topic="Test",
            tone="educational",
            language="zh-TW",
            scene_title="Hook",
            scene_summary="Opening",
            scene_number=1,
            total_scenes=3,
            duration_seconds=20,
            is_short_form=True,
        )
        assert "彗星客機" in prompt

    def test_non_short_form_no_guide(self) -> None:
        prompt = build_scene_narration_prompt(
            topic="Test",
            tone="educational",
            language="zh-TW",
            scene_title="Intro",
            scene_summary="Opening",
            scene_number=1,
            total_scenes=5,
            duration_seconds=30,
            is_short_form=False,
        )
        assert "SHORT-FORM" not in prompt
        assert "彗星客機" not in prompt


class TestSystemPrompt:
    def test_system_prompt_not_empty(self) -> None:
        assert len(SYSTEM_PROMPT) > 0

    def test_system_prompt_mentions_short_form(self) -> None:
        assert "short-form" in SYSTEM_PROMPT

    def test_system_prompt_has_anti_patterns(self) -> None:
        assert "NEVER" in SYSTEM_PROMPT
        assert "大家好" in SYSTEM_PROMPT

    def test_system_prompt_requires_spoken_language(self) -> None:
        assert "spoken language" in SYSTEM_PROMPT
