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
        assert "between 3 and 5" in prompt

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


class TestSystemPrompt:
    def test_system_prompt_not_empty(self) -> None:
        assert len(SYSTEM_PROMPT) > 0

    def test_system_prompt_mentions_youtube(self) -> None:
        assert "YouTube" in SYSTEM_PROMPT
