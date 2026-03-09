"""Tests for voice generation schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_farm.voice.schemas import AudioSegment, VoiceArtifact, VoiceSettings


class TestVoiceSettings:
    def test_defaults(self) -> None:
        settings = VoiceSettings()
        assert settings.stability == 0.5
        assert settings.similarity_boost == 0.75
        assert settings.style == 0.0
        assert settings.use_speaker_boost is False

    def test_custom_values(self) -> None:
        settings = VoiceSettings(stability=0.8, similarity_boost=0.9)
        assert settings.stability == 0.8

    def test_stability_range(self) -> None:
        with pytest.raises(ValidationError):
            VoiceSettings(stability=1.5)

    def test_frozen(self) -> None:
        settings = VoiceSettings()
        with pytest.raises(ValidationError):
            settings.stability = 0.9  # type: ignore[misc]


class TestAudioSegment:
    def test_creation(self) -> None:
        seg = AudioSegment(
            scene_number=1,
            file_path="/tmp/scene_001.mp3",
            duration_seconds=30.5,
            character_count=200,
        )
        assert seg.scene_number == 1
        assert seg.format == "mp3"


class TestVoiceArtifact:
    def test_empty_artifact(self) -> None:
        artifact = VoiceArtifact()
        assert artifact.stage == "voice_generation"
        assert artifact.segments == ()
        assert artifact.total_duration_seconds == 0.0

    def test_with_segments(self) -> None:
        segs = (
            AudioSegment(
                scene_number=1,
                file_path="/tmp/s1.mp3",
                duration_seconds=30.0,
                character_count=100,
            ),
            AudioSegment(
                scene_number=2,
                file_path="/tmp/s2.mp3",
                duration_seconds=60.0,
                character_count=200,
            ),
        )
        artifact = VoiceArtifact(
            segments=segs,
            total_duration_seconds=90.0,
            total_characters=300,
            voice_id="test-voice",
            model_id="eleven_v3",
        )
        assert len(artifact.segments) == 2
        assert artifact.total_characters == 300
