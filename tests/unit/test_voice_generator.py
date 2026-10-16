"""Tests for the VoiceGenerator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
    # Stub out concat and subtitle generation (tested separately)
    full_mp3 = tmp_path / "audio" / "full.mp3"
    gen._concat_full_audio = AsyncMock(return_value=full_mp3)  # type: ignore[method-assign]
    gen._generate_subtitles = AsyncMock(return_value=tmp_path / "subtitles" / "subtitles.srt")  # type: ignore[method-assign]
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


def _fish_generator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, voice_id: str) -> tuple[VoiceGenerator, AsyncMock]:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CF_TTS_PROVIDER", "fish_audio")
    monkeypatch.setenv("CF_FISH_AUDIO_REFERENCE_ID", "default-ref")
    monkeypatch.setenv("CF_TTS_VOICE_ID", voice_id)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    async def fake_tts(*, text: str, output_path: Path, **_: object) -> int:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\xff" * 16000)
        return 16000

    mock_tts = AsyncMock()
    mock_tts.generate_speech_with_context.side_effect = fake_tts
    gen = VoiceGenerator(tts=mock_tts, settings=settings, output_dir=tmp_path / "audio")
    gen._concat_full_audio = AsyncMock(return_value=tmp_path / "audio" / "full.mp3")  # type: ignore[method-assign]
    gen._generate_subtitles = AsyncMock(return_value=tmp_path / "subtitles.srt")  # type: ignore[method-assign]
    return gen, mock_tts


@pytest.mark.asyncio
async def test_channel_voice_id_reaches_the_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sample_script: Script,
) -> None:
    gen, mock_tts = _fish_generator(monkeypatch, tmp_path, "chipcat-voice")
    await gen.generate(sample_script)
    assert {c.kwargs["voice_id"] for c in mock_tts.generate_speech_with_context.call_args_list} == {"chipcat-voice"}


@pytest.mark.asyncio
async def test_no_override_lets_the_provider_use_its_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sample_script: Script,
) -> None:
    gen, mock_tts = _fish_generator(monkeypatch, tmp_path, "")
    await gen.generate(sample_script)
    assert {c.kwargs["voice_id"] for c in mock_tts.generate_speech_with_context.call_args_list} == {None}
    identities = json.loads((tmp_path / "audio" / "voice_identity.json").read_text(encoding="utf-8"))
    assert identities["scene_001.mp3"]["voice_id"] == "default-ref"


@pytest.mark.asyncio
async def test_existing_audio_is_reused_only_for_the_same_voice_and_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sample_script: Script,
) -> None:
    gen, mock_tts = _fish_generator(monkeypatch, tmp_path, "voice-a")
    await gen.generate(sample_script)
    assert mock_tts.generate_speech_with_context.call_count == 2

    same, same_tts = _fish_generator(monkeypatch, tmp_path, "voice-a")
    await same.generate(sample_script)
    assert same_tts.generate_speech_with_context.call_count == 0  # Reusing existing audio

    other, other_tts = _fish_generator(monkeypatch, tmp_path, "voice-b")
    await other.generate(sample_script)
    assert other_tts.generate_speech_with_context.call_count == 2  # new voice: redone

    fixed = sample_script.model_copy(update={"pronunciation_map": {"比特幣": "逼特幣"}})
    again, again_tts = _fish_generator(monkeypatch, tmp_path, "voice-b")
    await again.generate(fixed)
    assert again_tts.generate_speech_with_context.call_count == 2  # TTS text changed in both scenes


@pytest.mark.asyncio
async def test_changing_the_fish_model_redoes_the_audio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sample_script: Script,
) -> None:
    monkeypatch.setenv("CF_FISH_AUDIO_MODEL", "s2.1-pro")
    gen, _ = _fish_generator(monkeypatch, tmp_path, "voice-a")
    await gen.generate(sample_script)
    identities = json.loads((tmp_path / "audio" / "voice_identity.json").read_text(encoding="utf-8"))
    assert identities["scene_001.mp3"]["model"] == "s2.1-pro"

    same, same_tts = _fish_generator(monkeypatch, tmp_path, "voice-a")
    await same.generate(sample_script)
    assert same_tts.generate_speech_with_context.call_count == 0  # control: same model reuses

    monkeypatch.setenv("CF_FISH_AUDIO_MODEL", "speech-1.5")
    other, other_tts = _fish_generator(monkeypatch, tmp_path, "voice-a")
    await other.generate(sample_script)
    assert other_tts.generate_speech_with_context.call_count == 2


@pytest.mark.asyncio
async def test_records_without_a_model_count_as_the_old_sdk_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sample_script: Script,
) -> None:
    """Audio voiced before the model was tracked was made with speech-1.5 (SDK default)."""
    gen, _ = _fish_generator(monkeypatch, tmp_path, "voice-a")
    await gen.generate(sample_script)
    path = tmp_path / "audio" / "voice_identity.json"
    legacy = {name: {k: v for k, v in rec.items() if k != "model"}
              for name, rec in json.loads(path.read_text(encoding="utf-8")).items()}
    path.write_text(json.dumps(legacy), encoding="utf-8")

    monkeypatch.setenv("CF_FISH_AUDIO_MODEL", "speech-1.5")
    pinned, pinned_tts = _fish_generator(monkeypatch, tmp_path, "voice-a")
    await pinned.generate(sample_script)
    assert pinned_tts.generate_speech_with_context.call_count == 0

    monkeypatch.setenv("CF_FISH_AUDIO_MODEL", "s2.1-pro")
    new, new_tts = _fish_generator(monkeypatch, tmp_path, "voice-a")
    await new.generate(sample_script)
    assert new_tts.generate_speech_with_context.call_count == 2


@pytest.mark.asyncio
async def test_audio_without_an_identity_record_is_redone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sample_script: Script,
) -> None:
    audio = tmp_path / "audio"
    audio.mkdir()
    for n in (1, 2):
        (audio / f"scene_{n:03d}.mp3").write_bytes(b"old machine voice")
    gen, mock_tts = _fish_generator(monkeypatch, tmp_path, "voice-a")
    await gen.generate(sample_script)
    assert mock_tts.generate_speech_with_context.call_count == 2


@pytest.mark.asyncio
async def test_generate_output_paths(
    voice_generator: tuple[VoiceGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, mock_tts = voice_generator
    artifact = await gen.generate(sample_script)

    assert "scene_001" in artifact.segments[0].file_path
    assert "scene_002" in artifact.segments[1].file_path
