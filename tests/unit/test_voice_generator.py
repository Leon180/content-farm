"""Tests for the VoiceGenerator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from content_farm.config import Settings
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.voice.generator import VoiceGenerator


@pytest.fixture
def sample_script() -> Script:
    return Script(
        video_title="測試影片",
        description="測試用影片",
        language="zh-TW",
        scenes=(
            Scene(
                scene_number=1,
                title="開場",
                narration="歡迎來到本期影片，今天我們要探討比特幣的運作原理。",
                visual_hint=VisualHint(description="標題畫面"),
                duration_seconds=30,
            ),
            Scene(
                scene_number=2,
                title="主體",
                narration="比特幣是一種去中心化的數位貨幣，由中本聰在2009年發明。",
                visual_hint=VisualHint(description="區塊鏈示意圖"),
                duration_seconds=60,
            ),
        ),
        total_duration_seconds=90,
    )


@pytest.fixture
def voice_generator(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> tuple[VoiceGenerator, AsyncMock]:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CF_ELEVENLABS_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]

    mock_tts = AsyncMock()
    # Return 16000 bytes (~1 second at 128kbps)
    mock_tts.generate_speech_with_context.return_value = 16000

    gen = VoiceGenerator(
        tts=mock_tts,
        settings=settings,
        output_dir=tmp_path / "audio",
    )
    return gen, mock_tts


@pytest.mark.asyncio
async def test_generate_creates_segments(
    voice_generator: tuple[VoiceGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, mock_tts = voice_generator
    artifact = await gen.generate(sample_script)

    assert len(artifact.segments) == 2
    assert artifact.total_characters > 0
    assert artifact.stage == "voice_generation"


@pytest.mark.asyncio
async def test_generate_calls_tts_with_context(
    voice_generator: tuple[VoiceGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, mock_tts = voice_generator
    await gen.generate(sample_script)

    # Should be called once per scene
    assert mock_tts.generate_speech_with_context.call_count == 2

    # First scene: no previous_text, has next_text
    first_call = mock_tts.generate_speech_with_context.call_args_list[0]
    assert first_call.kwargs["previous_text"] is None
    assert first_call.kwargs["next_text"] is not None

    # Second scene: has previous_text, no next_text
    second_call = mock_tts.generate_speech_with_context.call_args_list[1]
    assert second_call.kwargs["previous_text"] is not None
    assert second_call.kwargs["next_text"] is None


@pytest.mark.asyncio
async def test_generate_output_paths(
    voice_generator: tuple[VoiceGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, mock_tts = voice_generator
    artifact = await gen.generate(sample_script)

    assert "scene_001" in artifact.segments[0].file_path
    assert "scene_002" in artifact.segments[1].file_path
