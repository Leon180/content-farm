"""Tests for pipeline/fetch.py — Drive-based and local missing artifact detection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from content_farm.drive.uploader import extract_folder_id
from content_farm.pipeline.fetch import (
    FetchResult,
    _MissingReport,
    _build_missing_report,
    _count_local_files,
    _detect_missing_drive,
    _detect_missing_local,
    _format_report,
    fetch_missing_artifacts,
)
from content_farm.script_gen.schemas import Scene, Script, VisualHint


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

def _make_script(n_scenes: int = 3) -> Script:
    scenes = tuple(
        Scene(
            scene_number=i + 1,
            title=f"場景{i + 1}",
            narration=f"旁白{i + 1}",
            visual_hint=VisualHint(
                description=f"desc {i + 1}",
                keywords=(f"kw{i + 1}a", f"kw{i + 1}b"),
            ),
            duration_seconds=10,
        )
        for i in range(n_scenes)
    )
    return Script(
        video_title="測試影片",
        description="測試描述",
        language="zh-TW",
        scenes=scenes,
    )


def _populate_dir(
    run_dir: Path,
    *,
    voice: int = 0,
    visual: int = 0,
    subtitle: bool = False,
    thumbnail: bool = False,
) -> None:
    """Create expected files in the run directory."""
    if voice > 0:
        d = run_dir / "audio"
        d.mkdir(parents=True, exist_ok=True)
        for i in range(voice):
            (d / f"scene_{i + 1:03d}.mp3").write_bytes(b"\x00" * 50)

    if visual > 0:
        d = run_dir / "visual"
        d.mkdir(parents=True, exist_ok=True)
        for i in range(visual):
            (d / f"scene_{i + 1:03d}.mp4").write_bytes(b"\x00" * 100)

    if subtitle:
        d = run_dir / "subtitles"
        d.mkdir(parents=True, exist_ok=True)
        (d / "subtitles.srt").write_text("1\n00:00:00,000 --> 00:00:10,000\ntest\n")

    if thumbnail:
        d = run_dir / "thumbnails"
        d.mkdir(parents=True, exist_ok=True)
        (d / "thumb.jpg").write_bytes(b"\x00" * 50)


# ---------------------------------------------------------------------------
# extract_folder_id
# ---------------------------------------------------------------------------

class TestExtractFolderId:
    def test_standard_url(self) -> None:
        url = "https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsT"
        assert extract_folder_id(url) == "1aBcDeFgHiJkLmNoPqRsT"

    def test_url_with_query_params(self) -> None:
        url = "https://drive.google.com/drive/folders/abc123?usp=sharing"
        assert extract_folder_id(url) == "abc123"

    def test_file_url_returns_none(self) -> None:
        assert extract_folder_id("file:///tmp/run") is None

    def test_empty_string(self) -> None:
        assert extract_folder_id("") is None

    def test_no_folders_segment(self) -> None:
        assert extract_folder_id("https://drive.google.com/drive/my-drive") is None


# ---------------------------------------------------------------------------
# _detect_missing_local
# ---------------------------------------------------------------------------

class TestDetectMissingLocal:
    def test_empty_run_dir_all_missing(self, tmp_path: Path) -> None:
        """Empty directory = all 4 stages missing."""
        report = _detect_missing_local(tmp_path, _make_script(3))
        assert len(report.missing_stages) == 4
        assert "voice" in report.missing_stages
        assert "visual" in report.missing_stages
        assert "subtitle" in report.missing_stages
        assert "thumbnail" in report.missing_stages
        for detail in report.stage_details.values():
            assert "不存在" in detail

    def test_all_present(self, tmp_path: Path) -> None:
        """All folders populated = nothing missing."""
        _populate_dir(
            tmp_path, voice=3, visual=3,
            subtitle=True, thumbnail=True,
        )
        report = _detect_missing_local(tmp_path, _make_script(3))
        assert not report.has_missing

    def test_visual_missing(self, tmp_path: Path) -> None:
        _populate_dir(
            tmp_path, voice=3, subtitle=True, thumbnail=True,
        )
        report = _detect_missing_local(tmp_path, _make_script(3))
        assert report.missing_stages == ["visual"]

    def test_voice_missing(self, tmp_path: Path) -> None:
        _populate_dir(
            tmp_path, visual=3, subtitle=True, thumbnail=True,
        )
        report = _detect_missing_local(tmp_path, _make_script(3))
        assert report.missing_stages == ["voice"]

    def test_subtitle_missing(self, tmp_path: Path) -> None:
        _populate_dir(
            tmp_path, voice=3, visual=3, thumbnail=True,
        )
        report = _detect_missing_local(tmp_path, _make_script(3))
        assert report.missing_stages == ["subtitle"]

    def test_thumbnail_missing(self, tmp_path: Path) -> None:
        _populate_dir(
            tmp_path, voice=3, visual=3, subtitle=True,
        )
        report = _detect_missing_local(tmp_path, _make_script(3))
        assert report.missing_stages == ["thumbnail"]

    def test_empty_folder_detected(self, tmp_path: Path) -> None:
        """Folder exists but is empty = still missing."""
        for name in ("audio", "visual", "subtitles", "thumbnails"):
            (tmp_path / name).mkdir()
        report = _detect_missing_local(tmp_path, _make_script(3))
        assert len(report.missing_stages) == 4
        for detail in report.stage_details.values():
            assert "空的" in detail

    def test_partial_visual_scenes(self, tmp_path: Path) -> None:
        _populate_dir(
            tmp_path, voice=3, visual=1,
            subtitle=True, thumbnail=True,
        )
        report = _detect_missing_local(tmp_path, _make_script(3))
        assert "visual" in report.missing_stages
        assert "1/3" in report.stage_details["visual"]

    def test_partial_voice_scenes(self, tmp_path: Path) -> None:
        _populate_dir(
            tmp_path, voice=1, visual=3,
            subtitle=True, thumbnail=True,
        )
        report = _detect_missing_local(tmp_path, _make_script(3))
        assert "voice" in report.missing_stages
        assert "1/3" in report.stage_details["voice"]


# ---------------------------------------------------------------------------
# _detect_missing_drive
# ---------------------------------------------------------------------------

class TestDetectMissingDrive:
    def _mock_uploader(self, subfolder_files: dict[str, int]) -> MagicMock:
        """Create a mock uploader where subfolder_files maps name → file count."""
        uploader = MagicMock()

        def find_subfolder(_parent_id: str, name: str):
            if name in subfolder_files:
                return f"folder_id_{name}"
            return None

        def list_files(folder_id: str):
            name = folder_id.replace("folder_id_", "")
            count = subfolder_files.get(name, 0)
            return [{"id": f"f{i}", "name": f"file_{i}"} for i in range(count)]

        uploader.find_subfolder.side_effect = find_subfolder
        uploader.list_files.side_effect = list_files
        return uploader

    def test_all_present_on_drive(self, tmp_path: Path) -> None:
        uploader = self._mock_uploader({
            "audio": 3, "visual": 3,
            "subtitles": 1, "thumbnails": 1,
        })
        report = _detect_missing_drive(
            uploader, "root_id", tmp_path, _make_script(3),
        )
        assert not report.has_missing

    def test_cloud_missing_local_present(self, tmp_path: Path) -> None:
        """Cloud has no visual folder, but local does → local_only_stages."""
        uploader = self._mock_uploader({
            "audio": 3, "subtitles": 1, "thumbnails": 1,
        })
        _populate_dir(tmp_path, visual=3)
        report = _detect_missing_drive(
            uploader, "root_id", tmp_path, _make_script(3),
        )
        assert "visual" in report.missing_stages
        assert "visual" in report.local_only_stages
        assert "本地有" in report.stage_details["visual"]

    def test_both_missing(self, tmp_path: Path) -> None:
        """Cloud and local both empty for subtitle."""
        uploader = self._mock_uploader({
            "audio": 3, "visual": 3, "thumbnails": 1,
        })
        report = _detect_missing_drive(
            uploader, "root_id", tmp_path, _make_script(3),
        )
        assert "subtitle" in report.missing_stages
        assert "subtitle" not in report.local_only_stages
        assert "都沒有" in report.stage_details["subtitle"]

    def test_partial_cloud_files(self, tmp_path: Path) -> None:
        """Cloud has 1 of 3 visual files, local has 0."""
        uploader = self._mock_uploader({
            "audio": 3, "visual": 1,
            "subtitles": 1, "thumbnails": 1,
        })
        report = _detect_missing_drive(
            uploader, "root_id", tmp_path, _make_script(3),
        )
        assert "visual" in report.missing_stages
        assert "1/3" in report.stage_details["visual"]

    def test_drive_error_returns_zero(self, tmp_path: Path) -> None:
        """Drive API failure → count as 0 files."""
        uploader = MagicMock()
        uploader.find_subfolder.side_effect = Exception("API error")
        report = _detect_missing_drive(
            uploader, "root_id", tmp_path, _make_script(1),
        )
        assert report.has_missing


# ---------------------------------------------------------------------------
# _build_missing_report — fallback chain
# ---------------------------------------------------------------------------

class TestBuildMissingReport:
    def test_no_drive_credentials_falls_back(self, tmp_path: Path) -> None:
        container = MagicMock()
        container.has_drive_credentials.return_value = False
        db = MagicMock()

        _populate_dir(tmp_path, voice=3, visual=3,
                      subtitle=True, thumbnail=True)
        report = _build_missing_report(
            container, db, "run1", tmp_path, _make_script(3),
        )
        assert not report.has_missing
        # Should not try to get drive checkpoint
        db.get_checkpoint.assert_not_called()

    def test_no_drive_link_falls_back(self, tmp_path: Path) -> None:
        container = MagicMock()
        container.has_drive_credentials.return_value = True
        db = MagicMock()
        db.get_checkpoint.return_value = None

        report = _build_missing_report(
            container, db, "run1", tmp_path, _make_script(3),
        )
        assert report.has_missing  # empty dir → all missing via local check

    def test_drive_error_classifies_as_local_only(self, tmp_path: Path) -> None:
        """Per-folder Drive errors → cloud_count=0, local has files → local_only."""
        container = MagicMock()
        container.has_drive_credentials.return_value = True
        db = MagicMock()
        db.get_checkpoint.return_value = "https://drive.google.com/drive/folders/abc"

        uploader = MagicMock()
        uploader.find_subfolder.side_effect = Exception("Network error")
        container.create_drive_uploader.return_value = uploader

        _populate_dir(tmp_path, voice=3, visual=3,
                      subtitle=True, thumbnail=True)
        report = _build_missing_report(
            container, db, "run1", tmp_path, _make_script(3),
        )
        # Drive errors per-folder → all stages classified as local_only (upload needed)
        assert report.has_missing
        assert set(report.local_only_stages) == set(report.missing_stages)


# ---------------------------------------------------------------------------
# _format_report
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_visual_shows_keywords(self) -> None:
        report = _MissingReport(
            missing_stages=["visual"],
            stage_details={"visual": "資料夾不存在"},
        )
        text = _format_report(report, _make_script(3), "abc")
        assert "visual/" in text
        assert "kw1a" in text
        assert "確認要重新生成並上傳嗎" in text

    def test_missing_thumbnail(self) -> None:
        report = _MissingReport(
            missing_stages=["thumbnail"],
            stage_details={"thumbnail": "資料夾不存在"},
        )
        text = _format_report(report, _make_script(), "abc")
        assert "thumbnails/" in text

    def test_missing_voice(self) -> None:
        report = _MissingReport(
            missing_stages=["voice"],
            stage_details={"voice": "資料夾是空的"},
        )
        text = _format_report(report, _make_script(), "abc")
        assert "audio/" in text

    def test_missing_subtitle(self) -> None:
        report = _MissingReport(
            missing_stages=["subtitle"],
            stage_details={"subtitle": "資料夾不存在"},
        )
        text = _format_report(report, _make_script(), "abc")
        assert "subtitles/" in text

    def test_run_id_shown(self) -> None:
        report = _MissingReport(
            missing_stages=["visual"],
            stage_details={"visual": "資料夾不存在"},
        )
        text = _format_report(report, _make_script(), "run999")
        assert "run999" in text

    def test_multiple_missing(self) -> None:
        report = _MissingReport(
            missing_stages=["voice", "visual", "subtitle", "thumbnail"],
            stage_details={
                "voice": "資料夾不存在",
                "visual": "資料夾不存在",
                "subtitle": "資料夾不存在",
                "thumbnail": "資料夾不存在",
            },
        )
        text = _format_report(report, _make_script(), "abc")
        assert "audio/" in text
        assert "visual/" in text
        assert "subtitles/" in text
        assert "thumbnails/" in text

    def test_local_only_tag(self) -> None:
        report = _MissingReport(
            missing_stages=["visual", "subtitle"],
            stage_details={
                "visual": "雲端缺少，本地有 3 個檔案，需要上傳",
                "subtitle": "雲端和本地都沒有檔案",
            },
            local_only_stages=["visual"],
        )
        text = _format_report(report, _make_script(), "abc")
        assert "只需上傳" in text


# ---------------------------------------------------------------------------
# fetch_missing_artifacts
# ---------------------------------------------------------------------------

class TestFetchMissingArtifacts:
    @pytest.mark.anyio()
    async def test_nothing_missing_returns_early(self, tmp_path: Path) -> None:
        _populate_dir(
            tmp_path, voice=1, visual=1,
            subtitle=True, thumbnail=True,
        )

        script = _make_script(1)
        db = MagicMock()
        db.get_run.return_value = MagicMock(
            output_dir=str(tmp_path),
            completed_stages=("script", "voice", "visual", "subtitle", "thumbnail"),
        )
        db.get_script_json.return_value = script.model_dump_json()

        gate = MagicMock()
        gate.notify_progress = AsyncMock()
        gate.confirm_action = AsyncMock()

        container = MagicMock()
        container.has_drive_credentials.return_value = False

        result = await fetch_missing_artifacts(
            run_id="abc",
            settings=MagicMock(),
            container=container,
            gate=gate,
            db=db,
        )

        assert result.refetched_stages == ()
        gate.confirm_action.assert_not_called()

    @pytest.mark.anyio()
    async def test_user_cancels(self, tmp_path: Path) -> None:
        _populate_dir(tmp_path, voice=2)

        script = _make_script(2)
        db = MagicMock()
        db.get_run.return_value = MagicMock(
            output_dir=str(tmp_path),
            completed_stages=("script", "voice"),
        )
        db.get_script_json.return_value = script.model_dump_json()

        gate = MagicMock()
        gate.notify_progress = AsyncMock()
        gate.confirm_action = AsyncMock(return_value=False)

        container = MagicMock()
        container.has_drive_credentials.return_value = False

        result = await fetch_missing_artifacts(
            run_id="abc",
            settings=MagicMock(),
            container=container,
            gate=gate,
            db=db,
        )

        assert result.refetched_stages == ()
        gate.confirm_action.assert_called_once()

    @pytest.mark.anyio()
    async def test_run_not_found_raises(self) -> None:
        db = MagicMock()
        db.get_run.return_value = None

        with pytest.raises(ValueError, match="Run not found"):
            await fetch_missing_artifacts(
                run_id="nonexistent",
                settings=MagicMock(),
                container=MagicMock(),
                gate=MagicMock(),
                db=db,
            )

    @pytest.mark.anyio()
    async def test_no_script_notifies(self, tmp_path: Path) -> None:
        db = MagicMock()
        db.get_run.return_value = MagicMock(
            output_dir=str(tmp_path),
            completed_stages=(),
        )
        db.get_script_json.return_value = None

        gate = MagicMock()
        gate.notify_progress = AsyncMock()

        result = await fetch_missing_artifacts(
            run_id="abc",
            settings=MagicMock(),
            container=MagicMock(),
            gate=gate,
            db=db,
        )

        assert result.refetched_stages == ()
        gate.notify_progress.assert_called_once()
        msg = gate.notify_progress.call_args[0][2]
        assert "script" in msg.lower() or "沒有儲存" in msg


# ---------------------------------------------------------------------------
# confirm_action
# ---------------------------------------------------------------------------

class TestConfirmAction:
    @pytest.mark.anyio()
    async def test_auto_confirms_without_bot(self) -> None:
        from content_farm.telegram.approval import ApprovalGate

        gate = ApprovalGate(bot=None)
        assert await gate.confirm_action("test?") is True

    @pytest.mark.anyio()
    async def test_confirm_button(self) -> None:
        from content_farm.telegram.approval import ApprovalGate

        bot = MagicMock()
        bot.send_inline_keyboard = AsyncMock(return_value=1)

        queue: __import__("asyncio").Queue = __import__("asyncio").Queue()
        gate = ApprovalGate(bot=bot, update_queue=queue)

        bot.answer_callback_query = AsyncMock()
        await queue.put({"callback_query": {"id": "cb1", "data": "confirm"}})

        result = await gate.confirm_action("Proceed?")
        assert result is True

    @pytest.mark.anyio()
    async def test_cancel_button(self) -> None:
        from content_farm.telegram.approval import ApprovalGate

        bot = MagicMock()
        bot.send_inline_keyboard = AsyncMock(return_value=1)
        bot.answer_callback_query = AsyncMock()

        queue: __import__("asyncio").Queue = __import__("asyncio").Queue()
        gate = ApprovalGate(bot=bot, update_queue=queue)

        await queue.put({"callback_query": {"id": "cb2", "data": "cancel"}})

        result = await gate.confirm_action("Proceed?")
        assert result is False
