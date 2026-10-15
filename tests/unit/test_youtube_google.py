"""Tests for GoogleProvider — YouTube upload via Data API v3."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from content_farm.youtube.google_provider import GoogleProvider
from content_farm.youtube.schemas import UploadSettings


@pytest.fixture
def provider() -> GoogleProvider:
    return GoogleProvider(
        client_id="test-client-id",
        client_secret="test-client-secret",
        refresh_token="test-refresh-token",
    )


@pytest.fixture
def mock_service() -> MagicMock:
    """Create a mock YouTube API service."""
    service = MagicMock()

    # Mock videos().insert().next_chunk()
    insert_request = MagicMock()
    insert_request.next_chunk.return_value = (None, {"id": "video123"})
    service.videos.return_value.insert.return_value = insert_request

    # Mock thumbnails().set().execute()
    service.thumbnails.return_value.set.return_value.execute.return_value = {}

    # Mock captions().insert().execute()
    service.captions.return_value.insert.return_value.execute.return_value = {
        "id": "caption456",
    }

    return service


class TestUploadVideo:
    @pytest.mark.asyncio
    async def test_upload_calls_insert(
        self, provider: GoogleProvider, mock_service: MagicMock, tmp_path: Path,
    ) -> None:
        provider._service = mock_service

        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video data")

        video_id = await provider.upload_video(
            video_path=video,
            title="Test Title",
            description="Test Description",
            tags=("tag1", "tag2"),
        )

        assert video_id == "video123"
        mock_service.videos.return_value.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_passes_metadata(
        self, provider: GoogleProvider, mock_service: MagicMock, tmp_path: Path,
    ) -> None:
        provider._service = mock_service

        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video data")

        settings = UploadSettings(privacy_status="unlisted", category_id="20")
        await provider.upload_video(
            video_path=video,
            title="我的影片",
            description="描述",
            tags=("教學",),
            settings=settings,
        )

        call_kwargs = mock_service.videos.return_value.insert.call_args.kwargs
        body = call_kwargs["body"]
        assert body["snippet"]["title"] == "我的影片"
        assert body["snippet"]["tags"] == ["教學"]
        assert body["snippet"]["categoryId"] == "20"
        assert body["status"]["privacyStatus"] == "unlisted"
        assert "publishAt" not in body["status"]
        assert "containsSyntheticMedia" not in body["status"]

    @pytest.mark.asyncio
    async def test_upload_schedules_and_discloses(
        self, provider: GoogleProvider, mock_service: MagicMock, tmp_path: Path,
    ) -> None:
        provider._service = mock_service
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video data")

        settings = UploadSettings(privacy_status="public", publish_at="2026-10-22T19:00:00+08:00",
                                  contains_synthetic_media=True)
        await provider.upload_video(video_path=video, title="t", description="d", settings=settings)

        status = mock_service.videos.return_value.insert.call_args.kwargs["body"]["status"]
        assert status["privacyStatus"] == "private"
        assert status["publishAt"] == "2026-10-22T19:00:00+08:00"
        assert status["containsSyntheticMedia"] is True

    @pytest.mark.asyncio
    async def test_upload_with_progress(
        self, provider: GoogleProvider, mock_service: MagicMock, tmp_path: Path,
    ) -> None:
        """Test resumable upload with progress reporting."""
        provider._service = mock_service

        # Simulate multi-chunk upload: first chunk returns status, second returns response
        progress_status = MagicMock()
        progress_status.progress.return_value = 0.5

        insert_request = mock_service.videos.return_value.insert.return_value
        insert_request.next_chunk.side_effect = [
            (progress_status, None),
            (None, {"id": "video789"}),
        ]

        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video data")

        video_id = await provider.upload_video(
            video_path=video, title="Progress Test", description="test",
        )

        assert video_id == "video789"
        assert insert_request.next_chunk.call_count == 2


class TestSetThumbnail:
    @pytest.mark.asyncio
    async def test_set_thumbnail_calls_api(
        self, provider: GoogleProvider, mock_service: MagicMock, tmp_path: Path,
    ) -> None:
        provider._service = mock_service

        thumb = tmp_path / "thumb.jpg"
        thumb.write_bytes(b"fake jpeg data")

        await provider.set_thumbnail(video_id="video123", thumbnail_path=thumb)

        mock_service.thumbnails.return_value.set.assert_called_once()
        call_kwargs = mock_service.thumbnails.return_value.set.call_args.kwargs
        assert call_kwargs["videoId"] == "video123"


class TestSetCaptions:
    @pytest.mark.asyncio
    async def test_set_captions_calls_api(
        self, provider: GoogleProvider, mock_service: MagicMock, tmp_path: Path,
    ) -> None:
        provider._service = mock_service

        srt = tmp_path / "subs.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:05,000\nHello\n")

        await provider.set_captions(
            video_id="video123", caption_path=srt, language="zh-TW",
        )

        mock_service.captions.return_value.insert.assert_called_once()
        call_kwargs = mock_service.captions.return_value.insert.call_args.kwargs
        body = call_kwargs["body"]
        assert body["snippet"]["videoId"] == "video123"
        assert body["snippet"]["language"] == "zh-TW"

    @pytest.mark.asyncio
    async def test_set_captions_default_language(
        self, provider: GoogleProvider, mock_service: MagicMock, tmp_path: Path,
    ) -> None:
        provider._service = mock_service

        srt = tmp_path / "subs.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:05,000\nHello\n")

        await provider.set_captions(video_id="video123", caption_path=srt)

        call_kwargs = mock_service.captions.return_value.insert.call_args.kwargs
        assert call_kwargs["body"]["snippet"]["language"] == "zh-TW"


class TestCredentials:
    def test_build_credentials(self, provider: GoogleProvider) -> None:
        with patch("content_farm.youtube.google_provider.Request"), \
             patch("content_farm.youtube.google_provider.Credentials") as mock_creds:
            mock_creds.return_value = MagicMock()
            creds = provider._build_credentials()
            mock_creds.assert_called_once()
            call_kwargs = mock_creds.call_args.kwargs
            assert call_kwargs["client_id"] == "test-client-id"
            assert call_kwargs["client_secret"] == "test-client-secret"
            assert call_kwargs["refresh_token"] == "test-refresh-token"

    def test_ensure_service_lazy_init(self, provider: GoogleProvider) -> None:
        assert provider._service is None
        with patch.object(provider, "_build_credentials") as mock_build, \
             patch("content_farm.youtube.google_provider.build") as mock_build_svc:
            mock_build.return_value = MagicMock()
            mock_build_svc.return_value = MagicMock()
            service = provider._ensure_service()
            assert service is not None
            mock_build_svc.assert_called_once_with(
                "youtube", "v3", credentials=mock_build.return_value,
            )

    def test_ensure_service_reuses(self, provider: GoogleProvider) -> None:
        fake_service = MagicMock()
        provider._service = fake_service
        assert provider._ensure_service() is fake_service
