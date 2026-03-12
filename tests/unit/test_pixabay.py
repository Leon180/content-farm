"""Tests for PixabayProvider — stock video search and download."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from content_farm.visual.pixabay import PixabayProvider, _pick_best_file
from content_farm.visual.schemas import VideoResult


# ---------------------------------------------------------------------------
# _pick_best_file
# ---------------------------------------------------------------------------

class TestPickBestFile:
    def test_portrait_prefers_vertical(self) -> None:
        videos = {
            "large": {"url": "http://lg", "width": 1920, "height": 1080},
            "medium": {"url": "http://md", "width": 720, "height": 1280},
        }
        result = _pick_best_file(videos, "portrait")
        assert result is not None
        assert result["url"] == "http://md"

    def test_landscape_accepts_horizontal(self) -> None:
        videos = {
            "large": {"url": "http://lg", "width": 1920, "height": 1080},
        }
        result = _pick_best_file(videos, "landscape")
        assert result is not None
        assert result["url"] == "http://lg"

    def test_portrait_fallback_to_landscape(self) -> None:
        """If no portrait file, fall back to any available file."""
        videos = {
            "large": {"url": "http://lg", "width": 1920, "height": 1080},
        }
        result = _pick_best_file(videos, "portrait")
        assert result is not None
        assert result["url"] == "http://lg"

    def test_empty_videos(self) -> None:
        assert _pick_best_file({}, "portrait") is None

    def test_skips_entries_without_url(self) -> None:
        videos = {
            "large": {"width": 1920, "height": 1080},
            "medium": {"url": "http://md", "width": 720, "height": 1280},
        }
        result = _pick_best_file(videos, "portrait")
        assert result is not None
        assert result["url"] == "http://md"

    def test_quality_order(self) -> None:
        """Prefers large > medium > small."""
        videos = {
            "small": {"url": "http://sm", "width": 540, "height": 960},
            "large": {"url": "http://lg", "width": 1080, "height": 1920},
        }
        result = _pick_best_file(videos, "portrait")
        assert result is not None
        assert result["url"] == "http://lg"


# ---------------------------------------------------------------------------
# PixabayProvider.search_videos
# ---------------------------------------------------------------------------

def _make_pixabay_response(
    hits: list[dict] | None = None,
) -> dict:
    if hits is None:
        hits = [
            {
                "id": 101,
                "duration": 12,
                "videos": {
                    "large": {"url": "http://vid-lg", "width": 1080, "height": 1920},
                    "medium": {"url": "http://vid-md", "width": 720, "height": 1280},
                    "tiny": {"url": "http://vid-tn", "width": 320, "height": 180, "thumbnail": "http://thumb"},
                },
            },
        ]
    return {"total": len(hits), "totalHits": len(hits), "hits": hits}


class TestPixabaySearch:
    @pytest.mark.anyio()
    async def test_search_returns_results(self) -> None:
        provider = PixabayProvider(api_key="fake")
        mock_response = MagicMock()
        mock_response.json.return_value = _make_pixabay_response()
        mock_response.raise_for_status = MagicMock()
        provider._client.get = AsyncMock(return_value=mock_response)

        results = await provider.search_videos("ocean", min_duration=5, max_duration=30)
        assert len(results) == 1
        assert results[0].provider_id == "pixabay:101"
        assert results[0].duration_seconds == 12

    @pytest.mark.anyio()
    async def test_filters_by_duration(self) -> None:
        provider = PixabayProvider(api_key="fake")
        hits = [
            {"id": 1, "duration": 2, "videos": {"large": {"url": "http://a", "width": 1080, "height": 1920}}},
            {"id": 2, "duration": 15, "videos": {"large": {"url": "http://b", "width": 1080, "height": 1920}}},
            {"id": 3, "duration": 60, "videos": {"large": {"url": "http://c", "width": 1080, "height": 1920}}},
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = _make_pixabay_response(hits)
        mock_response.raise_for_status = MagicMock()
        provider._client.get = AsyncMock(return_value=mock_response)

        results = await provider.search_videos("test", min_duration=5, max_duration=30)
        assert len(results) == 1
        assert results[0].provider_id == "pixabay:2"

    @pytest.mark.anyio()
    async def test_empty_hits(self) -> None:
        provider = PixabayProvider(api_key="fake")
        mock_response = MagicMock()
        mock_response.json.return_value = _make_pixabay_response([])
        mock_response.raise_for_status = MagicMock()
        provider._client.get = AsyncMock(return_value=mock_response)

        results = await provider.search_videos("nothing")
        assert results == ()


# ---------------------------------------------------------------------------
# PixabayProvider.download_video
# ---------------------------------------------------------------------------

class TestPixabayDownload:
    @pytest.mark.anyio()
    async def test_download_writes_file(self, tmp_path: Path) -> None:
        provider = PixabayProvider(api_key="fake")
        video = VideoResult(
            provider_id="pixabay:101",
            url="http://video.mp4",
            duration_seconds=10,
            width=1080,
            height=1920,
        )

        # Mock streaming response
        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)
        mock_stream.raise_for_status = MagicMock()

        async def fake_iter_bytes(chunk_size: int = 65536):
            yield b"fake-video-data"

        mock_stream.aiter_bytes = fake_iter_bytes
        provider._client.stream = MagicMock(return_value=mock_stream)

        out = tmp_path / "test.mp4"
        byte_count = await provider.download_video(video, output_path=out)
        assert byte_count == len(b"fake-video-data")
        assert out.exists()
        assert out.read_bytes() == b"fake-video-data"
