"""Tests for sync_script_durations — scene + chapter timestamp resync after voice."""

from __future__ import annotations

from content_farm.pipeline.stages import sync_script_durations
from content_farm.script_gen.schemas import (
    ChapterOutline,
    Scene,
    Script,
    VisualHint,
)
from content_farm.types import Orientation
from content_farm.voice.schemas import AudioSegment, VoiceArtifact


def _make_scene(n: int, chapter: int | None = None, dur: float = 20.0) -> Scene:
    return Scene(
        scene_number=n,
        title=f"scene {n}",
        narration="...",
        visual_hint=VisualHint(description="x"),
        duration_seconds=dur,
        chapter_number=chapter,
    )


def _make_voice(durations: dict[int, float]) -> VoiceArtifact:
    segments = tuple(
        AudioSegment(
            scene_number=n,
            file_path=f"/tmp/scene_{n:03d}.mp3",
            duration_seconds=d,
            character_count=0,
        )
        for n, d in sorted(durations.items())
    )
    total = sum(s.duration_seconds for s in segments)
    return VoiceArtifact(
        segments=segments,
        total_duration_seconds=total,
        output_dir="/tmp",
        full_audio_path="/tmp/full.mp3",
    )


def test_short_form_script_only_updates_scene_durations() -> None:
    """No chapters → only scenes + total updated; no chapter recomputation."""
    script = Script(
        video_title="short",
        description="",
        scenes=(_make_scene(1, dur=30), _make_scene(2, dur=30)),
        language="zh-TW",
    )
    voice = _make_voice({1: 25.0, 2: 28.0})

    result = sync_script_durations(script, voice)

    assert [s.duration_seconds for s in result.scenes] == [25.0, 28.0]
    assert result.total_duration_seconds == 53.0
    assert result.chapters == ()  # untouched


def test_long_form_recomputes_chapter_timestamps_from_actual_audio() -> None:
    """Long-form: chapter start_timestamp + duration rebuilt from real scene durations."""
    chapters = (
        ChapterOutline(chapter_number=1, title="A", summary="", duration_seconds=30, start_timestamp=0.0),
        ChapterOutline(chapter_number=2, title="B", summary="", duration_seconds=30, start_timestamp=30.0),
        ChapterOutline(chapter_number=3, title="C", summary="", duration_seconds=30, start_timestamp=60.0),
    )
    # 3 scenes in ch1, 2 in ch2, 1 in ch3
    scenes = (
        _make_scene(1, chapter=1),
        _make_scene(2, chapter=1),
        _make_scene(3, chapter=1),
        _make_scene(4, chapter=2),
        _make_scene(5, chapter=2),
        _make_scene(6, chapter=3),
    )
    script = Script(
        video_title="long",
        description="",
        scenes=scenes,
        chapters=chapters,
        orientation=Orientation.LANDSCAPE,
        language="zh-TW",
    )
    # Actual audio: ch1 = 5+5+5=15, ch2 = 10+10=20, ch3 = 25 → 60s total (not 90)
    voice = _make_voice({1: 5, 2: 5, 3: 5, 4: 10, 5: 10, 6: 25})

    result = sync_script_durations(script, voice)

    assert result.total_duration_seconds == 60.0
    # Chapters rebuilt
    assert result.chapters[0].start_timestamp == 0.0
    assert result.chapters[0].duration_seconds == 15.0
    assert result.chapters[1].start_timestamp == 15.0
    assert result.chapters[1].duration_seconds == 20.0
    assert result.chapters[2].start_timestamp == 35.0
    assert result.chapters[2].duration_seconds == 25.0


def test_chapter_preserves_metadata() -> None:
    """Hook, payoff, key_points, title must survive the resync."""
    chapters = (
        ChapterOutline(
            chapter_number=1, title="original title", summary="sum",
            duration_seconds=30, key_points=("p1", "p2"),
            hook="hook text", payoff="payoff text", start_timestamp=0.0,
        ),
        ChapterOutline(
            chapter_number=2, title="second", summary="",
            duration_seconds=30, start_timestamp=30.0,
        ),
        ChapterOutline(
            chapter_number=3, title="third", summary="",
            duration_seconds=30, start_timestamp=60.0,
        ),
    )
    script = Script(
        video_title="x", description="",
        scenes=(_make_scene(1, chapter=1), _make_scene(2, chapter=2), _make_scene(3, chapter=3)),
        chapters=chapters, orientation=Orientation.LANDSCAPE, language="zh-TW",
    )
    voice = _make_voice({1: 12, 2: 18, 3: 24})
    result = sync_script_durations(script, voice)

    assert result.chapters[0].title == "original title"
    assert result.chapters[0].hook == "hook text"
    assert result.chapters[0].payoff == "payoff text"
    assert result.chapters[0].key_points == ("p1", "p2")
