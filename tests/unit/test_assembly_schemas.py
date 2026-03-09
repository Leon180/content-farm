"""Tests for assembly domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_farm.assembly.schemas import (
    AssemblyArtifact,
    AssemblyInput,
    AssemblySettings,
    ComposedScene,
)
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.visual.schemas import VisualArtifact, VisualAsset
from content_farm.voice.schemas import AudioSegment, VoiceArtifact


def _make_script() -> Script:
    return Script(
        video_title="測試影片",
        description="測試",
        language="zh-TW",
        scenes=(
            Scene(
                scene_number=1,
                title="開場",
                narration="歡迎",
                visual_hint=VisualHint(description="title"),
                duration_seconds=10,
            ),
        ),
    )


class TestAssemblyInput:
    def test_create(self) -> None:
        inp = AssemblyInput(
            script=_make_script(),
            voice=VoiceArtifact(
                segments=(
                    AudioSegment(
                        scene_number=1,
                        file_path="/tmp/s1.mp3",
                        duration_seconds=10.0,
                        character_count=5,
                    ),
                ),
                total_duration_seconds=10.0,
            ),
            visual=VisualArtifact(
                assets=(
                    VisualAsset(
                        scene_number=1,
                        file_path="/tmp/s1.mp4",
                        source="pexels",
                        duration_seconds=12.0,
                        query_used="title",
                    ),
                ),
                total_duration_seconds=12.0,
            ),
        )
        assert inp.background_music_path is None
        assert inp.subtitle_path is None

    def test_frozen(self) -> None:
        inp = AssemblyInput(
            script=_make_script(),
            voice=VoiceArtifact(),
            visual=VisualArtifact(),
        )
        with pytest.raises(ValidationError):
            inp.subtitle_path = "foo.srt"  # type: ignore[misc]


class TestComposedScene:
    def test_create(self) -> None:
        cs = ComposedScene(
            scene_number=1,
            file_path="/tmp/s1_composed.mp4",
            duration_seconds=10.5,
            video_source="/tmp/s1.mp4",
            audio_source="/tmp/s1.mp3",
        )
        assert cs.scene_number == 1

    def test_frozen(self) -> None:
        cs = ComposedScene(
            scene_number=1,
            file_path="/tmp/s1.mp4",
            duration_seconds=10.0,
            video_source="a",
            audio_source="b",
        )
        with pytest.raises(ValidationError):
            cs.file_path = "other.mp4"  # type: ignore[misc]


class TestAssemblySettings:
    def test_defaults(self) -> None:
        s = AssemblySettings()
        assert s.width == 1920
        assert s.height == 1080
        assert s.fps == 30
        assert s.crf == 23
        assert s.preset == "medium"

    def test_crf_validation(self) -> None:
        with pytest.raises(ValidationError):
            AssemblySettings(crf=52)
        with pytest.raises(ValidationError):
            AssemblySettings(crf=-1)

    def test_volume_validation(self) -> None:
        with pytest.raises(ValidationError):
            AssemblySettings(background_music_volume=1.5)


class TestAssemblyArtifact:
    def test_defaults(self) -> None:
        a = AssemblyArtifact()
        assert a.stage == "video_assembly"
        assert a.scenes == ()
        assert a.file_size_bytes == 0

    def test_with_scenes(self) -> None:
        cs = ComposedScene(
            scene_number=1,
            file_path="/tmp/s1.mp4",
            duration_seconds=10.0,
            video_source="a",
            audio_source="b",
        )
        a = AssemblyArtifact(
            file_path="/tmp/final.mp4",
            scenes=(cs,),
            total_duration_seconds=10.0,
            file_size_bytes=5_000_000,
        )
        assert len(a.scenes) == 1
        assert a.file_size_bytes == 5_000_000
