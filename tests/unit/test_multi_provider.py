"""Tests for MultiStockProvider — fallback across multiple stock providers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from content_farm.visual.multi_provider import MultiStockProvider
from content_farm.visual.schemas import VideoResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(provider: str, vid_id: int = 1) -> VideoResult:
    return VideoResult(
        provider_id=f"{provider}:{vid_id}",
        url=f"http://{provider}/{vid_id}.mp4",
        duration_seconds=10,
        width=1080,
        height=1920,
    )


def _make_provider(
    name: str,
    results: tuple[VideoResult, ...] = (),
    *,
    raise_on_search: bool = False,
) -> AsyncMock:
    provider = AsyncMock()
    if raise_on_search:
        provider.search_videos = AsyncMock(side_effect=RuntimeError("API error"))
    else:
        provider.search_videos = AsyncMock(return_value=results)
    provider.download_video = AsyncMock(return_value=1024)
    return provider


# ---------------------------------------------------------------------------
# search_videos
# ---------------------------------------------------------------------------

class TestMultiSearch:
    @pytest.mark.anyio()
    async def test_returns_first_provider_results(self) -> None:
        r1 = (_make_result("pexels"),)
        r2 = (_make_result("pixabay"),)
        p1 = _make_provider("pexels", r1)
        p2 = _make_provider("pixabay", r2)
        multi = MultiStockProvider(providers=(p1, p2), provider_names=("pexels", "pixabay"))

        results = await multi.search_videos("ocean")
        assert len(results) == 1
        assert results[0].provider_id == "pexels:1"
        # Second provider not called
        p2.search_videos.assert_not_called()

    @pytest.mark.anyio()
    async def test_falls_back_on_empty(self) -> None:
        p1 = _make_provider("pexels", ())
        r2 = (_make_result("pixabay"),)
        p2 = _make_provider("pixabay", r2)
        multi = MultiStockProvider(providers=(p1, p2), provider_names=("pexels", "pixabay"))

        results = await multi.search_videos("ocean")
        assert len(results) == 1
        assert results[0].provider_id == "pixabay:1"

    @pytest.mark.anyio()
    async def test_falls_back_on_error(self) -> None:
        p1 = _make_provider("pexels", raise_on_search=True)
        r2 = (_make_result("pixabay"),)
        p2 = _make_provider("pixabay", r2)
        multi = MultiStockProvider(providers=(p1, p2), provider_names=("pexels", "pixabay"))

        results = await multi.search_videos("ocean")
        assert len(results) == 1
        assert results[0].provider_id == "pixabay:1"

    @pytest.mark.anyio()
    async def test_all_empty_returns_empty(self) -> None:
        p1 = _make_provider("pexels", ())
        p2 = _make_provider("pixabay", ())
        multi = MultiStockProvider(providers=(p1, p2), provider_names=("pexels", "pixabay"))

        results = await multi.search_videos("nothing")
        assert results == ()

    @pytest.mark.anyio()
    async def test_passes_kwargs(self) -> None:
        p1 = _make_provider("pexels", (_make_result("pexels"),))
        multi = MultiStockProvider(providers=(p1,), provider_names=("pexels",))

        await multi.search_videos(
            "test", min_duration=3, max_duration=60, orientation="portrait", per_page=20,
        )
        p1.search_videos.assert_called_once_with(
            "test", min_duration=3, max_duration=60, orientation="portrait", per_page=20,
        )


# ---------------------------------------------------------------------------
# download_video
# ---------------------------------------------------------------------------

class TestMultiDownload:
    @pytest.mark.anyio()
    async def test_dispatches_to_correct_provider(self) -> None:
        p1 = _make_provider("pexels")
        p2 = _make_provider("pixabay")
        multi = MultiStockProvider(providers=(p1, p2), provider_names=("pexels", "pixabay"))

        video = _make_result("pixabay", 42)
        out = Path("/tmp/test.mp4")
        await multi.download_video(video, output_path=out)

        p2.download_video.assert_called_once_with(video, output_path=out, quality="hd")
        p1.download_video.assert_not_called()

    @pytest.mark.anyio()
    async def test_unknown_prefix_raises(self) -> None:
        p1 = _make_provider("pexels")
        multi = MultiStockProvider(providers=(p1,), provider_names=("pexels",))

        video = _make_result("unknown", 1)
        with pytest.raises(ValueError, match="No provider found"):
            await multi.download_video(video, output_path=Path("/tmp/x.mp4"))
