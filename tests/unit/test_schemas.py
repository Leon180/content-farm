"""Tests for script generation schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_farm.script_gen.schemas import (
    Scene,
    Script,
    ScriptRequest,
    VisualHint,
)
from content_farm.types import Tone, VideoLength


class TestScriptRequest:
    def test_valid_request(self) -> None:
        req = ScriptRequest(
            topic="How Bitcoin Works",
            keywords=["bitcoin", "blockchain"],
            video_length=VideoLength.MEDIUM,
            tone=Tone.EDUCATIONAL,
        )
        assert req.topic == "How Bitcoin Works"

    def test_topic_min_length(self) -> None:
        with pytest.raises(ValidationError):
            ScriptRequest(topic="ab")  # too short

    def test_topic_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ScriptRequest(topic="x" * 201)  # too long

    def test_defaults(self) -> None:
        req = ScriptRequest(topic="Test Topic")
        assert req.video_length == VideoLength.MEDIUM
        assert req.tone == Tone.EDUCATIONAL
        assert req.keywords == ()
        assert req.target_scene_count is None

    def test_frozen(self) -> None:
        req = ScriptRequest(topic="Test")
        with pytest.raises(ValidationError):
            req.topic = "Changed"  # type: ignore[misc]


class TestScene:
    def test_scene_creation(self) -> None:
        scene = Scene(
            scene_number=1,
            title="Introduction",
            narration="Welcome to this video...",
            visual_hint=VisualHint(description="Title card"),
            duration_seconds=30,
        )
        assert scene.scene_number == 1
        assert scene.transition == "cut"

    def test_scene_frozen(self) -> None:
        scene = Scene(
            scene_number=1,
            title="Test",
            narration="Test",
            visual_hint=VisualHint(description="Test"),
            duration_seconds=30,
        )
        with pytest.raises(ValidationError):
            scene.title = "Changed"  # type: ignore[misc]


class TestScript:
    def test_script_with_scenes(self) -> None:
        scenes = (
            Scene(
                scene_number=1,
                title="Intro",
                narration="Hello",
                visual_hint=VisualHint(description="Title"),
                duration_seconds=30,
            ),
            Scene(
                scene_number=2,
                title="Body",
                narration="Main content",
                visual_hint=VisualHint(description="Charts"),
                duration_seconds=60,
            ),
        )
        script = Script(
            video_title="Test Video",
            description="A test",
            scenes=scenes,
            total_duration_seconds=90,
        )
        assert len(script.scenes) == 2
        assert script.ai_disclosure is True

    def test_full_narration(self) -> None:
        scenes = (
            Scene(
                scene_number=1,
                title="A",
                narration="First part.",
                visual_hint=VisualHint(description="x"),
                duration_seconds=10,
            ),
            Scene(
                scene_number=2,
                title="B",
                narration="Second part.",
                visual_hint=VisualHint(description="y"),
                duration_seconds=10,
            ),
        )
        script = Script(
            video_title="Test",
            description="Test",
            scenes=scenes,
            total_duration_seconds=20,
        )
        assert script.full_narration == "First part.\n\nSecond part."
