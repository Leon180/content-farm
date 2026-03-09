"""Tests for YouTube upload domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.youtube.schemas import UploadArtifact, UploadInput, UploadSettings


def _make_script(title: str = "測試影片標題") -> Script:
    return Script(
        video_title=title,
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


class TestUploadSettings:
    def test_defaults(self) -> None:
        s = UploadSettings()
        assert s.privacy_status == "private"
        assert s.category_id == "22"
        assert s.made_for_kids is False
        assert s.default_language == "zh-TW"
        assert s.chunk_size_bytes == 256 * 1024 * 1024

    def test_custom_values(self) -> None:
        s = UploadSettings(privacy_status="public", category_id="20")
        assert s.privacy_status == "public"
        assert s.category_id == "20"

    def test_chunk_size_validation(self) -> None:
        with pytest.raises(ValidationError):
            UploadSettings(chunk_size_bytes=0)

    def test_frozen(self) -> None:
        s = UploadSettings()
        with pytest.raises(ValidationError):
            s.privacy_status = "public"  # type: ignore[misc]


class TestUploadInput:
    def test_create_minimal(self) -> None:
        inp = UploadInput(script=_make_script(), video_path="/tmp/video.mp4")
        assert inp.video_path == "/tmp/video.mp4"
        assert inp.thumbnail_path is None
        assert inp.subtitle_path is None
        assert inp.tags == ()

    def test_create_full(self) -> None:
        inp = UploadInput(
            script=_make_script(),
            video_path="/tmp/video.mp4",
            thumbnail_path="/tmp/thumb.jpg",
            subtitle_path="/tmp/subs.srt",
            tags=("教學", "科技"),
        )
        assert inp.thumbnail_path == "/tmp/thumb.jpg"
        assert inp.subtitle_path == "/tmp/subs.srt"
        assert inp.tags == ("教學", "科技")

    def test_frozen(self) -> None:
        inp = UploadInput(script=_make_script(), video_path="/tmp/video.mp4")
        with pytest.raises(ValidationError):
            inp.video_path = "/other.mp4"  # type: ignore[misc]


class TestUploadArtifact:
    def test_defaults(self) -> None:
        a = UploadArtifact()
        assert a.stage == "youtube_upload"
        assert a.video_id == ""
        assert a.url == ""
        assert a.privacy_status == "private"
        assert a.thumbnail_set is False
        assert a.captions_set is False

    def test_with_values(self) -> None:
        a = UploadArtifact(
            video_id="abc123",
            url="https://youtu.be/abc123",
            privacy_status="unlisted",
            thumbnail_set=True,
            captions_set=True,
        )
        assert a.video_id == "abc123"
        assert a.url == "https://youtu.be/abc123"
        assert a.thumbnail_set is True
        assert a.captions_set is True
