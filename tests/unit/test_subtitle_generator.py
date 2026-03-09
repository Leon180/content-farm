"""Tests for SubtitleGenerator and SubtitleStage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from content_farm.config import Settings
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.subtitle.factory import create_subtitle_provider
from content_farm.subtitle.generator import (
    SubtitleGenerator,
    SubtitleStage,
    _find_audio_segment,
)
from content_farm.subtitle.schemas import SubtitleInput, SubtitleSegment
from content_farm.voice.schemas import AudioSegment, VoiceArtifact


def _make_subtitle_input() -> SubtitleInput:
    script = Script(
        video_title="測試影片",
        description="測試用",
        language="zh-TW",
        scenes=(
            Scene(
                scene_number=1,
                title="開場",
                narration="歡迎來到我們的頻道",
                visual_hint=VisualHint(description="title"),
                duration_seconds=10,
            ),
            Scene(
                scene_number=2,
                title="主體",
                narration="今天要介紹的主題",
                visual_hint=VisualHint(description="content"),
                duration_seconds=20,
            ),
        ),
        total_duration_seconds=30,
    )
    voice = VoiceArtifact(
        segments=(
            AudioSegment(
                scene_number=1,
                file_path="/tmp/audio/s1.mp3",
                duration_seconds=5.0,
                character_count=9,
            ),
            AudioSegment(
                scene_number=2,
                file_path="/tmp/audio/s2.mp3",
                duration_seconds=8.0,
                character_count=8,
            ),
        ),
        total_duration_seconds=13.0,
    )
    return SubtitleInput(script=script, voice=voice)


@pytest.fixture
def mock_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.generate_segments.side_effect = [
        (
            SubtitleSegment(
                index=1, start_seconds=0.0, end_seconds=5.0,
                text="歡迎來到我們的頻道", scene_number=0,
            ),
        ),
        (
            SubtitleSegment(
                index=1, start_seconds=5.0, end_seconds=13.0,
                text="今天要介紹的主題", scene_number=0,
            ),
        ),
    ]
    return provider


@pytest.mark.asyncio
async def test_generate_produces_srt_file(
    monkeypatch: pytest.MonkeyPatch,
    mock_provider: AsyncMock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]
    gen = SubtitleGenerator(mock_provider, settings, output_dir=tmp_path)

    artifact = await gen.generate(_make_subtitle_input())

    assert Path(artifact.file_path).exists()
    assert artifact.stage == "subtitle_generation"
    assert artifact.total_segments == 2
    assert artifact.total_duration_seconds == pytest.approx(13.0)
    assert artifact.language == "zh-TW"

    srt_content = Path(artifact.file_path).read_text(encoding="utf-8")
    assert "-->" in srt_content


@pytest.mark.asyncio
async def test_segments_globally_renumbered(
    monkeypatch: pytest.MonkeyPatch,
    mock_provider: AsyncMock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]
    gen = SubtitleGenerator(mock_provider, settings, output_dir=tmp_path)

    artifact = await gen.generate(_make_subtitle_input())

    indices = [s.index for s in artifact.segments]
    assert indices == [1, 2]
    assert artifact.segments[0].scene_number == 1
    assert artifact.segments[1].scene_number == 2


@pytest.mark.asyncio
async def test_provider_called_with_correct_offsets(
    monkeypatch: pytest.MonkeyPatch,
    mock_provider: AsyncMock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]
    gen = SubtitleGenerator(mock_provider, settings, output_dir=tmp_path)

    await gen.generate(_make_subtitle_input())

    calls = mock_provider.generate_segments.call_args_list
    assert len(calls) == 2

    # Scene 1: offset=0.0, duration=5.0
    assert calls[0].kwargs["offset_seconds"] == 0.0
    assert calls[0].kwargs["duration_seconds"] == 5.0

    # Scene 2: offset=5.0 (cumulative), duration=8.0
    assert calls[1].kwargs["offset_seconds"] == 5.0
    assert calls[1].kwargs["duration_seconds"] == 8.0


class TestSubtitleStage:
    @pytest.mark.asyncio
    async def test_validate_empty_segments_raises(self) -> None:
        stage = SubtitleStage(generator=AsyncMock())  # type: ignore[arg-type]
        inp = SubtitleInput(
            script=_make_subtitle_input().script,
            voice=VoiceArtifact(),
        )
        with pytest.raises(ValueError, match="no segments"):
            await stage.validate_input(inp)

    @pytest.mark.asyncio
    async def test_validate_empty_scenes_raises(self) -> None:
        stage = SubtitleStage(generator=AsyncMock())  # type: ignore[arg-type]
        inp = SubtitleInput(
            script=Script(
                video_title="t", description="d", language="zh-TW", scenes=(),
            ),
            voice=_make_subtitle_input().voice,
        )
        with pytest.raises(ValueError, match="no scenes"):
            await stage.validate_input(inp)

    @pytest.mark.asyncio
    async def test_validate_scene_mismatch_raises(self) -> None:
        stage = SubtitleStage(generator=AsyncMock())  # type: ignore[arg-type]
        inp = SubtitleInput(
            script=_make_subtitle_input().script,
            voice=VoiceArtifact(
                segments=(
                    AudioSegment(
                        scene_number=1,
                        file_path="/tmp/s1.mp3",
                        duration_seconds=5.0,
                        character_count=5,
                    ),
                ),
            ),
        )
        with pytest.raises(ValueError, match="mismatch"):
            await stage.validate_input(inp)


class TestHelpers:
    def test_find_audio_segment_found(self) -> None:
        inp = _make_subtitle_input()
        seg = _find_audio_segment(inp, 1)
        assert seg.scene_number == 1

    def test_find_audio_segment_missing(self) -> None:
        inp = _make_subtitle_input()
        with pytest.raises(ValueError, match="No audio segment for scene 99"):
            _find_audio_segment(inp, 99)


class TestFactory:
    def test_creates_estimation_provider(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        settings = Settings()  # type: ignore[call-arg]
        provider = create_subtitle_provider(settings)
        assert type(provider).__name__ == "EstimationProvider"

    def test_unknown_provider_raises(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("CF_SUBTITLE_PROVIDER", "unknown")
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="Unknown subtitle provider"):
            create_subtitle_provider(settings)

    def test_default_provider_is_estimation(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.subtitle_provider == "estimation"
