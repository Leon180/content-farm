"""Tests for compose/staging.py — StagingManager."""

from __future__ import annotations

from pathlib import Path

from content_farm.compose.schemas import StagedClip
from content_farm.compose.staging import StagingManager


def _make_staging(tmp_path: Path, duration: float = 30.0) -> StagingManager:
    return StagingManager(
        staging_dir=tmp_path / "compose",
        run_id="test123",
        voice_duration=duration,
        voice_paths=(tmp_path / "audio" / "scene_01.mp3",),
        subtitle_path=tmp_path / "subtitles" / "subs.srt",
    )


class TestStagingManager:
    def test_add_valid_clip(self, tmp_path: Path) -> None:
        staging = _make_staging(tmp_path)
        fake_file = tmp_path / "compose" / "00:00to00:03.mp4"
        fake_file.parent.mkdir(parents=True, exist_ok=True)
        fake_file.touch()

        result = staging.add_clip(fake_file, "00:00to00:03.mp4")
        assert isinstance(result, StagedClip)
        assert result.start_seconds == 0.0
        assert result.end_seconds == 3.0
        assert result.media_type == "video"
        assert staging.clip_count == 1

    def test_add_image_clip(self, tmp_path: Path) -> None:
        staging = _make_staging(tmp_path)
        fake_file = tmp_path / "compose" / "00:05to00:10.jpg"
        fake_file.parent.mkdir(parents=True, exist_ok=True)
        fake_file.touch()

        result = staging.add_clip(fake_file, "00:05to00:10.jpg")
        assert isinstance(result, StagedClip)
        assert result.media_type == "image"

    def test_bad_filename(self, tmp_path: Path) -> None:
        staging = _make_staging(tmp_path)
        fake_file = tmp_path / "random.mp4"
        fake_file.parent.mkdir(parents=True, exist_ok=True)
        fake_file.touch()

        result = staging.add_clip(fake_file, "random.mp4")
        assert isinstance(result, str)
        assert "格式不正確" in result

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        staging = _make_staging(tmp_path)
        fake_file = tmp_path / "00:00to00:03.txt"
        fake_file.parent.mkdir(parents=True, exist_ok=True)
        fake_file.touch()

        result = staging.add_clip(fake_file, "00:00to00:03.txt")
        assert isinstance(result, str)
        assert "不支援" in result

    def test_start_beyond_duration(self, tmp_path: Path) -> None:
        staging = _make_staging(tmp_path, duration=10.0)
        fake_file = tmp_path / "00:15to00:20.mp4"
        fake_file.parent.mkdir(parents=True, exist_ok=True)
        fake_file.touch()

        result = staging.add_clip(fake_file, "00:15to00:20.mp4")
        assert isinstance(result, str)
        assert "超出" in result

    def test_clamp_end_to_duration(self, tmp_path: Path) -> None:
        staging = _make_staging(tmp_path, duration=10.0)
        fake_file = tmp_path / "compose" / "00:05to00:15.mp4"
        fake_file.parent.mkdir(parents=True, exist_ok=True)
        fake_file.touch()

        result = staging.add_clip(fake_file, "00:05to00:15.mp4")
        assert isinstance(result, StagedClip)
        assert result.end_seconds == 10.0  # clamped

    def test_overlap_rejected(self, tmp_path: Path) -> None:
        staging = _make_staging(tmp_path)
        staging_dir = tmp_path / "compose"
        staging_dir.mkdir(parents=True, exist_ok=True)

        f1 = staging_dir / "00:00to00:05.mp4"
        f1.touch()
        staging.add_clip(f1, "00:00to00:05.mp4")

        f2 = staging_dir / "00:03to00:08.mp4"
        f2.touch()
        result = staging.add_clip(f2, "00:03to00:08.mp4")
        assert isinstance(result, str)
        assert "重疊" in result
        assert staging.clip_count == 1

    def test_get_clips_sorted(self, tmp_path: Path) -> None:
        staging = _make_staging(tmp_path)
        staging_dir = tmp_path / "compose"
        staging_dir.mkdir(parents=True, exist_ok=True)

        f1 = staging_dir / "00:10to00:15.mp4"
        f1.touch()
        staging.add_clip(f1, "00:10to00:15.mp4")

        f2 = staging_dir / "00:00to00:05.mp4"
        f2.touch()
        staging.add_clip(f2, "00:00to00:05.mp4")

        clips = staging.get_clips()
        assert len(clips) == 2
        assert clips[0].start_seconds == 0.0
        assert clips[1].start_seconds == 10.0

    def test_format_summary_empty(self, tmp_path: Path) -> None:
        staging = _make_staging(tmp_path)
        assert "尚未" in staging.format_summary()

    def test_format_summary_with_clips(self, tmp_path: Path) -> None:
        staging = _make_staging(tmp_path, duration=30.0)
        staging_dir = tmp_path / "compose"
        staging_dir.mkdir(parents=True, exist_ok=True)

        f1 = staging_dir / "00:00to00:10.mp4"
        f1.touch()
        staging.add_clip(f1, "00:00to00:10.mp4")

        summary = staging.format_summary()
        assert "1 個素材" in summary
        assert "覆蓋率" in summary
        assert "空白區間" in summary
