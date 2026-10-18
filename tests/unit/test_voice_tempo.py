"""voice.tempo: takes in audio/raw/, scene files re-timed with atempo, never re-synthesized."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from content_farm.config import Settings
from content_farm.production.channels import load_channel
from content_farm.production.voice_choice import choose_voice
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.voice import tempo
from content_farm.voice.generator import VoiceGenerator, _get_audio_duration

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _mp3(path: Path, seconds: float = 2.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                    "-t", str(seconds), "-codec:a", "libmp3lame", str(path)], check=True)
    return path


class ToneTTS:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_speech_with_context(self, text: str, *, output_path: Path, **_: object) -> int:
        self.calls += 1
        _mp3(output_path)
        return output_path.stat().st_size


def _script() -> Script:
    return Script(video_title="t", description="d", language="zh-TW", total_duration_seconds=2, scenes=(
        Scene(scene_number=1, title="a", narration="一段旁白。", visual_hint=VisualHint(description="x"),
              duration_seconds=2),))


async def _voice(settings: Settings, audio: Path, tts: ToneTTS, rate: float) -> float:
    gen = VoiceGenerator(tts=tts, settings=settings.model_copy(update={"tts_tempo": rate}),  # type: ignore[arg-type]
                         output_dir=audio)
    gen._concat_full_audio = AsyncMock(return_value=audio / "full.mp3")  # type: ignore[method-assign]
    gen._generate_subtitles = AsyncMock(return_value=audio / "s.srt")  # type: ignore[method-assign]
    artifact = await gen.generate(_script())
    return artifact.segments[0].duration_seconds


@needs_ffmpeg
@pytest.mark.asyncio
async def test_tempo_retimes_without_resynthesis_and_round_trips(test_settings: Settings, tmp_path: Path) -> None:
    audio, tts = tmp_path / "audio", ToneTTS()
    plain = await _voice(test_settings, audio, tts, 1.0)
    assert tts.calls == 1 and not (audio / "raw").exists()  # tempo 1.0: the old layout
    fast = await _voice(test_settings, audio, tts, 1.25)
    assert tts.calls == 1  # the take moved to raw/ and was re-timed, not re-synthesized
    assert (audio / "raw" / "scene_001.mp3").is_file()
    assert fast == pytest.approx(plain / 1.25, abs=0.1)
    assert tempo.applied(audio, "scene_001.mp3") == 1.25
    again = await _voice(test_settings, audio, tts, 1.25)
    assert tts.calls == 1 and again == pytest.approx(fast, abs=0.01)
    back = await _voice(test_settings, audio, tts, 1.0)
    assert tts.calls == 1 and back == pytest.approx(plain, abs=0.05)
    assert not (audio / "raw" / "scene_001.mp3").exists()


@needs_ffmpeg
@pytest.mark.asyncio
async def test_retime_rejects_out_of_range(tmp_path: Path) -> None:
    raw = _mp3(tmp_path / "a.mp3")
    with pytest.raises(ValueError):
        await tempo.retime("ffmpeg", raw, tmp_path / "b.mp3", 2.5)
    await tempo.retime("ffmpeg", raw, tmp_path / "b.mp3", 2.0)
    assert await _get_audio_duration(tmp_path / "b.mp3") == pytest.approx(1.0, abs=0.1)


def test_channel_tempo_follows_decision_and_enters_identity(tmp_path: Path) -> None:
    assert load_channel("yokai").voice.tempo == 1.29 and load_channel("cel").voice.tempo == 1.12
    assert load_channel("chipcat").voice.tempo == 1.15 and load_channel("offwork").voice.tempo == 1.0
    yokai = choose_voice(load_channel("yokai"), tmp_path / "none.env", mock=False)
    assert yokai.env()["CF_TTS_TEMPO"] == "1.29" and "tempo=1.29" in yokai.describe()
    assert "tempo=" not in choose_voice(load_channel("offwork"), tmp_path / "none.env", mock=False).describe()
