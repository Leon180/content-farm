"""Tests for compose/timeline.py — timestamp parsing and timeline building."""

from __future__ import annotations

import pytest

from content_farm.compose.timeline import (
    _check_overlaps,
    classify_media,
    parse_clip_filename,
    parse_timestamp,
)
from content_farm.compose.schemas import StagedClip


# ------------------------------------------------------------------
# parse_timestamp
# ------------------------------------------------------------------


class TestParseTimestamp:
    def test_mm_ss(self) -> None:
        assert parse_timestamp("00:00") == 0.0
        assert parse_timestamp("01:30") == 90.0
        assert parse_timestamp("10:05") == 605.0

    def test_h_mm_ss(self) -> None:
        assert parse_timestamp("1:00:00") == 3600.0
        assert parse_timestamp("0:01:30") == 90.0

    def test_invalid_format(self) -> None:
        with pytest.raises(ValueError, match="Invalid timestamp"):
            parse_timestamp("123")


# ------------------------------------------------------------------
# parse_clip_filename
# ------------------------------------------------------------------


class TestParseClipFilename:
    def test_basic_video(self) -> None:
        result = parse_clip_filename("00:00to00:03.mp4")
        assert result == (0.0, 3.0, "mp4")

    def test_image(self) -> None:
        result = parse_clip_filename("00:10to00:15.jpg")
        assert result == (10.0, 15.0, "jpg")

    def test_long_format(self) -> None:
        result = parse_clip_filename("1:00:00to1:00:30.mov")
        assert result == (3600.0, 3630.0, "mov")

    def test_no_match(self) -> None:
        assert parse_clip_filename("scene_01.mp4") is None
        assert parse_clip_filename("random.txt") is None

    def test_end_before_start(self) -> None:
        assert parse_clip_filename("00:10to00:05.mp4") is None

    def test_same_start_end(self) -> None:
        assert parse_clip_filename("00:05to00:05.mp4") is None

    def test_extension_case_insensitive(self) -> None:
        result = parse_clip_filename("00:00to00:03.MP4")
        assert result is not None
        assert result[2] == "mp4"


# ------------------------------------------------------------------
# classify_media
# ------------------------------------------------------------------


class TestClassifyMedia:
    def test_video_extensions(self) -> None:
        for ext in ("mp4", "mov", "avi", "mkv", "webm"):
            assert classify_media(ext) == "video"

    def test_image_extensions(self) -> None:
        for ext in ("jpg", "jpeg", "png", "webp"):
            assert classify_media(ext) == "image"

    def test_with_dot(self) -> None:
        assert classify_media(".mp4") == "video"
        assert classify_media(".png") == "image"

    def test_unsupported(self) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            classify_media("txt")


# ------------------------------------------------------------------
# _check_overlaps
# ------------------------------------------------------------------


def _clip(start: float, end: float, name: str = "test.mp4") -> StagedClip:
    return StagedClip(
        file_path="/tmp/test.mp4",
        original_filename=name,
        start_seconds=start,
        end_seconds=end,
        media_type="video",
    )


class TestCheckOverlaps:
    def test_no_overlap(self) -> None:
        clips = (_clip(0, 3), _clip(3, 6), _clip(10, 15))
        assert _check_overlaps(clips) is None

    def test_overlap(self) -> None:
        clips = (_clip(0, 5), _clip(3, 8))
        result = _check_overlaps(clips)
        assert result is not None
        assert "時間重疊" in result

    def test_single_clip(self) -> None:
        assert _check_overlaps((_clip(0, 3),)) is None

    def test_adjacent_no_overlap(self) -> None:
        clips = (_clip(0, 3), _clip(3, 6))
        assert _check_overlaps(clips) is None

    def test_unsorted_input(self) -> None:
        clips = (_clip(10, 15), _clip(0, 3), _clip(5, 8))
        assert _check_overlaps(clips) is None
