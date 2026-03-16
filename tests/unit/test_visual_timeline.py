"""Tests for visual timeline — SRT parsing, block building, markdown rendering."""

from __future__ import annotations

import pytest

from content_farm.visual.timeline import (
    TimelineBlock,
    build_scene_boundaries,
    build_timeline_from_srt,
    format_time,
    parse_srt,
    render_timeline_md,
)

SAMPLE_SRT = """\
1
00:00:00,000 --> 00:00:03,000
First subtitle line

2
00:00:03,000 --> 00:00:07,500
Second subtitle line

3
00:00:07,500 --> 00:00:12,000
Third subtitle line
"""


def test_format_time() -> None:
    assert format_time(0) == "00:00"
    assert format_time(65) == "01:05"
    assert format_time(125.7) == "02:05"


def test_parse_srt() -> None:
    entries = parse_srt(SAMPLE_SRT)
    assert len(entries) == 3
    assert entries[0] == (0.0, 3.0, "First subtitle line")
    assert entries[1] == (3.0, 7.5, "Second subtitle line")
    assert entries[2] == (7.5, 12.0, "Third subtitle line")


def test_parse_srt_comma_separator() -> None:
    srt = "1\n00:00:01,500 --> 00:00:03,200\nHello\n"
    entries = parse_srt(srt)
    assert len(entries) == 1
    assert entries[0][0] == pytest.approx(1.5)
    assert entries[0][1] == pytest.approx(3.2)


def test_build_scene_boundaries() -> None:
    script_data = {
        "scenes": [
            {"scene_number": 1, "duration_seconds": 7, "visual_hint": {"keywords": ["factory"]}},
            {"scene_number": 2, "duration_seconds": 5, "visual_hint": {"keywords": ["train"]}},
        ]
    }
    boundaries = build_scene_boundaries(script_data)
    assert len(boundaries) == 2
    assert boundaries[0] == (1, 0.0, 7.0, ["factory"])
    assert boundaries[1] == (2, 7.0, 12.0, ["train"])


def test_build_scene_boundaries_with_voice_override() -> None:
    script_data = {
        "scenes": [
            {"scene_number": 1, "duration_seconds": 10, "visual_hint": {"keywords": []}},
        ]
    }
    voice_data = {
        "segments": [{"scene_number": 1, "duration_seconds": 8.5}]
    }
    boundaries = build_scene_boundaries(script_data, voice_data)
    assert boundaries[0] == (1, 0.0, 8.5, [])


def test_build_timeline_from_srt() -> None:
    boundaries = [
        (1, 0.0, 7.5, ["factory", "printing"]),
        (2, 7.5, 12.0, ["train", "fog"]),
    ]
    blocks = build_timeline_from_srt(SAMPLE_SRT, boundaries)
    assert len(blocks) == 2

    assert blocks[0].scene_number == 1
    assert blocks[0].start_seconds == 0.0
    assert blocks[0].end_seconds == 7.5
    assert "First" in blocks[0].narration
    assert "Second" in blocks[0].narration
    assert blocks[0].keywords == ["factory", "printing"]
    assert blocks[0].label == "00:00~00:07"

    assert blocks[1].scene_number == 2
    assert blocks[1].start_seconds == 7.5
    assert blocks[1].end_seconds == 12.0
    assert "Third" in blocks[1].narration


def test_timeline_block_duration() -> None:
    block = TimelineBlock(
        start_seconds=10.0, end_seconds=25.0,
        scene_number=1, narration="test",
    )
    assert block.duration == 15.0


def test_render_timeline_md() -> None:
    blocks = [
        TimelineBlock(
            start_seconds=0.0, end_seconds=7.0,
            scene_number=1, narration="First scene text",
            keywords=["factory", "printing"],
        ),
        TimelineBlock(
            start_seconds=7.0, end_seconds=12.0,
            scene_number=2, narration="Second scene text",
            keywords=["train"],
        ),
    ]
    md = render_timeline_md(blocks)
    assert "# Visual Timeline" in md
    assert "`00:00~00:07`" in md
    assert "`00:07~00:12`" in md
    assert "factory, printing" in md
    assert "## Instructions" in md
