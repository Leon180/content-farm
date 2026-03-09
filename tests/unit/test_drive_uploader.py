"""Tests for DriveUploader — Google Drive upload pipeline outputs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from content_farm.drive.uploader import DriveUploader, _guess_mime_type, create_drive_uploader


# ---------------------------------------------------------------------------
# TestGuessType
# ---------------------------------------------------------------------------


class TestGuessType:
    def test_mp4(self) -> None:
        assert _guess_mime_type(Path("video.mp4")) == "video/mp4"

    def test_mp3(self) -> None:
        assert _guess_mime_type(Path("audio.mp3")) == "audio/mpeg"

    def test_srt(self) -> None:
        assert _guess_mime_type(Path("subtitles.srt")) == "text/plain"

    def test_json(self) -> None:
        assert _guess_mime_type(Path("data.json")) == "application/json"

    def test_unknown_extension(self) -> None:
        assert _guess_mime_type(Path("file.xyz")) == "application/octet-stream"


# ---------------------------------------------------------------------------
# TestCreateDriveUploader
# ---------------------------------------------------------------------------


class TestCreateDriveUploader:
    def test_returns_none_when_no_credentials(self) -> None:
        result = create_drive_uploader("", "folder123")
        assert result is None

    def test_returns_none_when_no_folder_id(self) -> None:
        result = create_drive_uploader("/path/to/creds.json", "")
        assert result is None

    def test_returns_uploader_when_configured(self) -> None:
        result = create_drive_uploader("/path/to/creds.json", "folder123")
        assert isinstance(result, DriveUploader)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_service(folder_id: str = "folder123", link: str = "https://drive.google.com/folder123") -> MagicMock:
    """Return a mock Drive service with sensible defaults for chained calls."""
    mock_service = MagicMock()
    mock_service.files().create().execute.return_value = {"id": folder_id, "webViewLink": link}
    mock_service.permissions().create().execute.return_value = {}
    return mock_service


@pytest.fixture
def uploader() -> DriveUploader:
    return DriveUploader(credentials_path="/fake/creds.json", folder_id="parent123")


# ---------------------------------------------------------------------------
# TestDriveUploader
# ---------------------------------------------------------------------------


class TestDriveUploader:
    def test_upload_folder_creates_subfolder(self, uploader: DriveUploader, tmp_path: Path) -> None:
        mock_service = _make_mock_service()
        with patch.object(uploader, "_get_service", return_value=mock_service):
            uploader._upload_folder_sync(tmp_path, "my-folder")

        create_calls = mock_service.files().create.call_args_list
        folder_call = next(
            c for c in create_calls if c.kwargs.get("body", {}).get("mimeType") == "application/vnd.google-apps.folder"
        )
        body = folder_call.kwargs["body"]
        assert body["name"] == "my-folder"
        assert "parent123" in body["parents"]

    def test_upload_folder_sets_permissions(self, uploader: DriveUploader, tmp_path: Path) -> None:
        mock_service = _make_mock_service()
        with patch.object(uploader, "_get_service", return_value=mock_service):
            uploader._upload_folder_sync(tmp_path, "my-folder")

        perm_calls = mock_service.permissions().create.call_args_list
        assert any(
            c.kwargs.get("fileId") == "folder123"
            and c.kwargs.get("body") == {"type": "anyone", "role": "reader"}
            for c in perm_calls
        )

    def test_upload_folder_returns_link(self, uploader: DriveUploader, tmp_path: Path) -> None:
        expected_link = "https://drive.google.com/folder123"
        mock_service = _make_mock_service(link=expected_link)
        with patch.object(uploader, "_get_service", return_value=mock_service):
            result = uploader._upload_folder_sync(tmp_path, "my-folder")

        assert result == expected_link

    def test_upload_files_in_directory(self, uploader: DriveUploader, tmp_path: Path) -> None:
        (tmp_path / "clip.mp4").write_bytes(b"fake-video")
        (tmp_path / "audio.mp3").write_bytes(b"fake-audio")

        mock_service = _make_mock_service()
        with patch.object(uploader, "_get_service", return_value=mock_service):
            with patch("googleapiclient.http.MediaFileUpload") as mock_media:
                uploader._upload_folder_sync(tmp_path, "my-folder")

        assert mock_media.call_count == 2
        uploaded_names = {call.args[0] for call in mock_media.call_args_list}
        assert any("clip.mp4" in name for name in uploaded_names)
        assert any("audio.mp3" in name for name in uploaded_names)

    def test_upload_subdirectory(self, uploader: DriveUploader, tmp_path: Path) -> None:
        subdir = tmp_path / "assets"
        subdir.mkdir()
        (subdir / "thumb.png").write_bytes(b"fake-png")
        (subdir / "cover.jpg").write_bytes(b"fake-jpg")

        mock_service = _make_mock_service()
        with patch.object(uploader, "_get_service", return_value=mock_service):
            with patch("googleapiclient.http.MediaFileUpload"):
                uploader._upload_folder_sync(tmp_path, "my-folder")

        folder_create_calls = [
            c for c in mock_service.files().create.call_args_list
            if c.kwargs.get("body", {}).get("mimeType") == "application/vnd.google-apps.folder"
        ]
        subdir_call = next(
            (c for c in folder_create_calls if c.kwargs.get("body", {}).get("name") == "assets"),
            None,
        )
        assert subdir_call is not None, "Expected a folder create call for 'assets' subdir"

    @pytest.mark.anyio
    async def test_upload_folder_async_delegates_to_sync(self, uploader: DriveUploader, tmp_path: Path) -> None:
        with patch.object(uploader, "_upload_folder_sync", return_value="https://link") as mock_sync:
            result = await uploader.upload_folder(tmp_path, "my-folder")

        mock_sync.assert_called_once_with(tmp_path, "my-folder")
        assert result == "https://link"
