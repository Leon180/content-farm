"""Tests for timeline assembly — clip scanning, sorting, filename parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from content_farm.assembly.timeline_assembly import (
    TimelineClip,
    has_timeline_clips,
    scan_timeline_clips,
)


def test_scan_timeline_clips_finds_selected(tmp_path: Path) -> None:
    """Only MM:SS~MM:SS.mp4 files (no index) should be found."""
    # Selected clips (no index suffix)
    (tmp_path / "00:00~00:07.mp4").write_bytes(b"video1")
    (tmp_path / "00:07~00:12.mp4").write_bytes(b"video2")

    # Candidate clips (with index suffix — should be ignored)
    (tmp_path / "00:00~00:07_01.mp4").write_bytes(b"candidate")
    (tmp_path / "00:00~00:07_02.mp4").write_bytes(b"candidate")

    # Other files — should be ignored
    (tmp_path / "scene_001.mp4").write_bytes(b"old")
    (tmp_path / "timeline.md").write_text("markdown")

    clips = scan_timeline_clips(tmp_path)
    assert len(clips) == 2
    assert clips[0].start_seconds == 0.0
    assert clips[0].end_seconds == 7.0
    assert clips[1].start_seconds == 7.0
    assert clips[1].end_seconds == 12.0


def test_scan_timeline_clips_sorted_by_start(tmp_path: Path) -> None:
    """Clips should be sorted by start time regardless of filesystem order."""
    (tmp_path / "01:00~01:30.mp4").write_bytes(b"v")
    (tmp_path / "00:30~01:00.mp4").write_bytes(b"v")
    (tmp_path / "00:00~00:30.mp4").write_bytes(b"v")

    clips = scan_timeline_clips(tmp_path)
    assert [c.start_seconds for c in clips] == [0, 30, 60]


def test_scan_timeline_clips_empty(tmp_path: Path) -> None:
    """Empty directory should return empty list."""
    clips = scan_timeline_clips(tmp_path)
    assert clips == []


def test_has_timeline_clips_true(tmp_path: Path) -> None:
    (tmp_path / "00:00~00:10.mp4").write_bytes(b"v")
    assert has_timeline_clips(tmp_path) is True


def test_has_timeline_clips_false(tmp_path: Path) -> None:
    (tmp_path / "scene_001.mp4").write_bytes(b"v")
    assert has_timeline_clips(tmp_path) is False


def test_timeline_clip_target_duration() -> None:
    clip = TimelineClip(
        path=Path("/tmp/00:00~00:15.mp4"),
        start_seconds=0.0,
        end_seconds=15.0,
    )
    assert clip.target_duration == 15.0


def test_scan_clips_minute_boundary(tmp_path: Path) -> None:
    """Verify clips spanning minute boundaries parse correctly."""
    (tmp_path / "00:55~01:10.mp4").write_bytes(b"v")
    clips = scan_timeline_clips(tmp_path)
    assert len(clips) == 1
    assert clips[0].start_seconds == 55.0
    assert clips[0].end_seconds == 70.0
