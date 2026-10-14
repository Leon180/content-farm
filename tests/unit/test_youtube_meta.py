"""Tests for YouTube metadata template generation and loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.script_gen.schemas import (
    ChapterOutline,
    Scene,
    Script,
    VisualHint,
)
from content_farm.types import Orientation
from content_farm.youtube.meta import (
    generate_meta_template,
    load_meta_template,
    save_meta_template,
)


def _make_script() -> Script:
    return Script(
        video_title="測試影片標題",
        description="這是測試影片的描述",
        language="zh-TW",
        scenes=(
            Scene(
                scene_number=1,
                title="場景1",
                narration="旁白",
                visual_hint=VisualHint(description="test"),
                duration_seconds=10,
            ),
        ),
        tags=("標籤1", "標籤2", "science"),
        sources=(
            "Source A — https://example.com/a",
            "Source B — https://example.com/b",
        ),
        ai_disclosure=True,
    )


class TestGenerateMetaTemplate:
    def test_fills_title_from_script(self, tmp_path: Path) -> None:
        script = _make_script()
        video = tmp_path / "upload" / "video_portrait.mp4"
        video.parent.mkdir(parents=True)
        video.touch()

        meta = generate_meta_template(script, tmp_path, video)
        assert meta["title"] == "測試影片標題"

    def test_fills_tags_from_script(self, tmp_path: Path) -> None:
        script = _make_script()
        video = tmp_path / "upload" / "v.mp4"
        video.parent.mkdir(parents=True)
        video.touch()

        meta = generate_meta_template(script, tmp_path, video)
        assert meta["tags"] == ["標籤1", "標籤2", "science"]

    def test_description_includes_sources(self, tmp_path: Path) -> None:
        script = _make_script()
        video = tmp_path / "upload" / "v.mp4"
        video.parent.mkdir(parents=True)
        video.touch()

        meta = generate_meta_template(script, tmp_path, video)
        assert "Source A" in meta["description"]
        assert "Source B" in meta["description"]
        assert "AI 輔助製作" in meta["description"]

    def test_video_path_is_relative(self, tmp_path: Path) -> None:
        script = _make_script()
        video = tmp_path / "upload" / "test_portrait.mp4"
        video.parent.mkdir(parents=True)
        video.touch()

        meta = generate_meta_template(script, tmp_path, video)
        assert meta["video_path"] == "upload/test_portrait.mp4"

    def test_finds_thumbnail(self, tmp_path: Path) -> None:
        script = _make_script()
        video = tmp_path / "upload" / "v.mp4"
        video.parent.mkdir(parents=True)
        video.touch()
        thumb = tmp_path / "thumbnails" / "thumb.png"
        thumb.parent.mkdir(parents=True)
        thumb.touch()

        meta = generate_meta_template(script, tmp_path, video)
        assert meta["thumbnail_path"] == "thumbnails/thumb.png"

    def test_finds_subtitle(self, tmp_path: Path) -> None:
        script = _make_script()
        video = tmp_path / "upload" / "v.mp4"
        video.parent.mkdir(parents=True)
        video.touch()
        srt = tmp_path / "subtitles" / "subs.srt"
        srt.parent.mkdir(parents=True)
        srt.touch()

        meta = generate_meta_template(script, tmp_path, video)
        assert meta["subtitle_path"] == "subtitles/subs.srt"

    def test_empty_paths_when_missing(self, tmp_path: Path) -> None:
        script = _make_script()
        video = tmp_path / "upload" / "v.mp4"
        video.parent.mkdir(parents=True)
        video.touch()

        meta = generate_meta_template(script, tmp_path, video)
        assert meta["thumbnail_path"] == ""
        assert meta["subtitle_path"] == ""

    def test_default_settings(self, tmp_path: Path) -> None:
        script = _make_script()
        video = tmp_path / "upload" / "v.mp4"
        video.parent.mkdir(parents=True)
        video.touch()

        meta = generate_meta_template(script, tmp_path, video)
        assert meta["privacy_status"] == "private"
        assert meta["category_id"] == "22"
        assert meta["made_for_kids"] is False
        assert meta["default_language"] == "zh-TW"


class TestSaveAndLoad:
    def test_round_trip(self, tmp_path: Path) -> None:
        meta = {
            "title": "test",
            "tags": ["a", "b"],
            "privacy_status": "unlisted",
        }
        path = save_meta_template(meta, tmp_path)
        assert path.exists()
        assert path.name == "youtube_meta.json"

        loaded = load_meta_template(tmp_path)
        assert loaded["title"] == "test"
        assert loaded["tags"] == ["a", "b"]
        assert loaded["privacy_status"] == "unlisted"

    def test_load_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="youtube_meta.json"):
            load_meta_template(tmp_path)

    def test_chinese_preserved(self, tmp_path: Path) -> None:
        meta = {"title": "中文標題測試", "description": "描述"}
        save_meta_template(meta, tmp_path)
        loaded = load_meta_template(tmp_path)
        assert loaded["title"] == "中文標題測試"


def _make_long_form_script(chapter_count: int = 3) -> Script:
    """Build a long-form Script with ``chapter_count`` chapters."""
    chapters = tuple(
        ChapterOutline(
            chapter_number=i + 1,
            title=f"章節 {i + 1}",
            summary=f"summary {i + 1}",
            duration_seconds=120.0,
            key_points=("point",),
            hook=f"hook {i + 1}",
            payoff=f"payoff {i + 1}",
            start_timestamp=i * 120.0,
        )
        for i in range(chapter_count)
    )
    return Script(
        video_title="長影片測試",
        description="長影片描述",
        language="zh-TW",
        scenes=(
            Scene(
                scene_number=1,
                title="場景1",
                narration="旁白",
                visual_hint=VisualHint(description="test"),
                duration_seconds=120,
                chapter_number=1,
            ),
        ),
        tags=("test",),
        sources=(),
        ai_disclosure=True,
        orientation=Orientation.LANDSCAPE,
        chapters=chapters,
    )


class TestChapterMarkers:
    def test_short_form_description_has_no_chapters(self, tmp_path: Path) -> None:
        """Short-form scripts must emit a description without a chapter block."""
        script = _make_script()
        video = tmp_path / "upload" / "v.mp4"
        video.parent.mkdir(parents=True)
        video.touch()

        meta = generate_meta_template(script, tmp_path, video)
        assert meta["chapters"] == []
        assert "章節" not in meta["description"]

    def test_long_form_chapter_block_at_top(self, tmp_path: Path) -> None:
        """Long-form description must start with chapter markers (YouTube parser)."""
        script = _make_long_form_script(chapter_count=5)
        video = tmp_path / "upload" / "v.mp4"
        video.parent.mkdir(parents=True)
        video.touch()

        meta = generate_meta_template(script, tmp_path, video)

        lines = meta["description"].split("\n")
        assert lines[0] == "章節："
        assert lines[1].startswith("0:00")  # YouTube requires 0:00 first
        assert " 章節 1" in lines[1]
        # Each chapter gets its own line; 5 chapters → timestamps at 0:00, 2:00, 4:00, 6:00, 8:00
        assert "2:00 章節 2" in meta["description"]
        assert "8:00 章節 5" in meta["description"]

    def test_long_form_chapters_in_meta_dict(self, tmp_path: Path) -> None:
        script = _make_long_form_script(chapter_count=3)
        video = tmp_path / "upload" / "v.mp4"
        video.parent.mkdir(parents=True)
        video.touch()

        meta = generate_meta_template(script, tmp_path, video)
        assert len(meta["chapters"]) == 3
        assert meta["chapters"][0] == {"timestamp": "0:00", "title": "章節 1"}
        assert meta["chapters"][2] == {"timestamp": "4:00", "title": "章節 3"}

    def test_two_chapters_are_skipped(self, tmp_path: Path) -> None:
        """YouTube requires at least 3 chapters; fewer → no block emitted."""
        script = _make_long_form_script(chapter_count=2)
        video = tmp_path / "upload" / "v.mp4"
        video.parent.mkdir(parents=True)
        video.touch()

        meta = generate_meta_template(script, tmp_path, video)
        # meta["chapters"] still populated for reference
        assert len(meta["chapters"]) == 2
        # but description has no chapter block — YouTube won't parse 2 entries
        assert "章節：" not in meta["description"]

    def test_over_one_hour_uses_h_mm_ss(self, tmp_path: Path) -> None:
        """Videos >1 hour need H:MM:SS format."""
        chapters = (
            ChapterOutline(chapter_number=1, title="開頭", summary="", duration_seconds=1800, start_timestamp=0.0),
            ChapterOutline(chapter_number=2, title="中段", summary="", duration_seconds=1800, start_timestamp=1800.0),
            ChapterOutline(chapter_number=3, title="結尾", summary="", duration_seconds=900, start_timestamp=3600.0),
        )
        script = Script(
            video_title="長片",
            description="desc",
            language="zh-TW",
            scenes=(Scene(
                scene_number=1, title="s", narration="n",
                visual_hint=VisualHint(description="x"), duration_seconds=1,
            ),),
            orientation=Orientation.LANDSCAPE,
            chapters=chapters,
        )
        video = tmp_path / "upload" / "v.mp4"
        video.parent.mkdir(parents=True)
        video.touch()

        meta = generate_meta_template(script, tmp_path, video)
        assert "0:00 開頭" in meta["description"]
        assert "30:00 中段" in meta["description"]
        assert "1:00:00 結尾" in meta["description"]
