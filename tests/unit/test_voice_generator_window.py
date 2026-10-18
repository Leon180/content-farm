"""Window re-voicing inside VoiceGenerator: only the changed sentence ± radius is synthesized."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import AsyncMock

import numpy as np
import pytest

from content_farm.config import Settings
from content_farm.retention.timing import split_sentences
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.voice import splice
from content_farm.voice.generator import VoiceGenerator

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
SENTENCES = ["第一句。", "第二句。", "第三句。", "第四句。", "第五句。", "第六句。"]


def _burst_tts(calls: list[str]):
    """Fake TTS: one 0.6 s tone per sentence with 0.3 s pauses (decodable, so it can be spliced)."""

    async def fake(*, text: str, output_path: Path, **_: object) -> int:
        calls.append(text)
        t = np.arange(int(0.6 * splice.SR)) / splice.SR
        parts = []
        for k, _sentence in enumerate(split_sentences(text)):
            parts += [np.zeros(int(0.3 * splice.SR), np.float32),
                      (0.3 * np.sin(2 * np.pi * (200 + 10 * k) * t)).astype(np.float32)]
        parts.append(np.zeros(int(0.3 * splice.SR), np.float32))
        splice.encode(np.concatenate(parts), output_path)
        return output_path.stat().st_size

    return fake


def _script(lines: list[str]) -> Script:
    return Script(video_title="t", description="d", language="zh-TW", total_duration_seconds=30,
                  scenes=(Scene(scene_number=1, title="a", narration="".join(lines),
                                visual_hint=VisualHint(description="v"), duration_seconds=30),))


@pytest.mark.asyncio
async def test_one_changed_sentence_is_revoiced_with_its_window(monkeypatch: pytest.MonkeyPatch,
                                                                 tmp_path: Path) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CF_TTS_PROVIDER", "fish_audio")
    monkeypatch.setenv("CF_TTS_SPLICE_RADIUS", "1")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    async def run(lines: list[str]) -> list[str]:
        calls: list[str] = []
        tts = AsyncMock()
        tts.generate_speech_with_context.side_effect = _burst_tts(calls)
        gen = VoiceGenerator(tts=tts, settings=settings, output_dir=tmp_path / "audio")
        gen._concat_full_audio = AsyncMock(return_value=tmp_path / "audio" / "full.mp3")  # type: ignore[method-assign]
        gen._generate_subtitles = AsyncMock(return_value=tmp_path / "s.srt")  # type: ignore[method-assign]
        await gen.generate(_script(lines))
        return calls

    assert len(await run(SENTENCES)) == 1                      # first take: the whole scene
    edited = [*SENTENCES[:3], "改寫的第四句。", *SENTENCES[4:]]
    assert await run(edited) == ["第三句。改寫的第四句。第五句。"]  # window: 3rd–5th sentence only
    take = tmp_path / "audio" / "scene_001.mp3"
    assert len(splice.pauses(splice.decode(take))) >= 7        # still six bursts with pauses around
    assert await run(edited) == []                              # recorded: reused next time


@pytest.mark.asyncio
async def test_radius_minus_one_revoices_the_whole_scene(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CF_TTS_PROVIDER", "fish_audio")
    monkeypatch.setenv("CF_TTS_SPLICE_RADIUS", "-1")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    calls: list[str] = []
    tts = AsyncMock()
    tts.generate_speech_with_context.side_effect = _burst_tts(calls)
    for lines in (SENTENCES, [*SENTENCES[:3], "改寫的第四句。", *SENTENCES[4:]]):
        gen = VoiceGenerator(tts=tts, settings=settings, output_dir=tmp_path / "audio")
        gen._concat_full_audio = AsyncMock(return_value=tmp_path / "audio" / "full.mp3")  # type: ignore[method-assign]
        gen._generate_subtitles = AsyncMock(return_value=tmp_path / "s.srt")  # type: ignore[method-assign]
        await gen.generate(_script(lines))
    assert len(calls) == 2 and calls[1].startswith("第一句")
