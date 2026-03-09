"""Tests for thumbnail domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.thumbnail.schemas import (
    ThumbnailArtifact,
    ThumbnailInput,
    ThumbnailSettings,
)


def _make_script() -> Script:
    return Script(
        video_title="測試影片標題",
        description="測試",
        language="zh-TW",
        scenes=(
            Scene(
                scene_number=1,
                title="開場",
                narration="歡迎",
                visual_hint=VisualHint(description="title"),
                duration_seconds=10,
            ),
        ),
    )


class TestThumbnailSettings:
    def test_defaults(self) -> None:
        s = ThumbnailSettings()
        assert s.width == 1280
        assert s.height == 720
        assert s.font_size == 100
        assert s.stroke_width == 4
        assert s.quality == 85
        assert s.text_color == "#FFFFFF"
        assert s.stroke_color == "#000000"
        assert s.max_title_chars == 40

    def test_quality_validation(self) -> None:
        with pytest.raises(ValidationError):
            ThumbnailSettings(quality=0)
        with pytest.raises(ValidationError):
            ThumbnailSettings(quality=101)

    def test_frozen(self) -> None:
        s = ThumbnailSettings()
        with pytest.raises(ValidationError):
            s.width = 640  # type: ignore[misc]


class TestThumbnailInput:
    def test_create_without_video(self) -> None:
        inp = ThumbnailInput(script=_make_script())
        assert inp.video_path is None

    def test_create_with_video(self) -> None:
        inp = ThumbnailInput(
            script=_make_script(),
            video_path="/tmp/video.mp4",
        )
        assert inp.video_path == "/tmp/video.mp4"

    def test_frozen(self) -> None:
        inp = ThumbnailInput(script=_make_script())
        with pytest.raises(ValidationError):
            inp.video_path = "/other.mp4"  # type: ignore[misc]


class TestThumbnailArtifact:
    def test_defaults(self) -> None:
        a = ThumbnailArtifact()
        assert a.stage == "thumbnail_generation"
        assert a.width == 1280
        assert a.height == 720
        assert a.file_size_bytes == 0
        assert a.used_keyframe is False

    def test_with_values(self) -> None:
        a = ThumbnailArtifact(
            file_path="/tmp/thumb.jpg",
            file_size_bytes=150_000,
            used_keyframe=True,
        )
        assert a.file_path == "/tmp/thumb.jpg"
        assert a.file_size_bytes == 150_000
        assert a.used_keyframe is True
