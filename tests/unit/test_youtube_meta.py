"""Tests for YouTube metadata template generation and loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.script_gen.schemas import Scene, Script, VisualHint
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
