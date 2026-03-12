"""Pexels stock footage provider."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from content_farm.visual.schemas import PhotoResult, VideoResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.pexels.com"


class PexelsProvider:
    """Async client for the Pexels Video API (free, 200 req/hr)."""

    def __init__(self, api_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"Authorization": api_key},
            timeout=30.0,
        )

    async def search_videos(
        self,
        query: str,
        *,
        min_duration: int = 5,
        max_duration: int = 30,
        orientation: str = "portrait",
        per_page: int = 15,
    ) -> tuple[VideoResult, ...]:
        """Search Pexels for stock videos matching the query."""
        params: dict[str, object] = {
            "query": query,
            "orientation": orientation,
            "per_page": per_page,
            "size": "medium",
        }

        response = await self._client.get("/videos/search", params=params)
        response.raise_for_status()
        data = response.json()

        results: list[VideoResult] = []
        for video in data.get("videos", []):
            duration = video.get("duration", 0)
            if duration < min_duration or duration > max_duration:
                continue

            # Pick the best HD video file
            video_file = _pick_best_file(video.get("video_files", []))
            if video_file is None:
                continue

            results.append(
                VideoResult(
                    provider_id=f"pexels:{video['id']}",
                    url=video_file["link"],
                    duration_seconds=duration,
                    width=video_file.get("width", 0),
                    height=video_file.get("height", 0),
                    thumbnail_url=video.get("image", ""),
                )
            )

        logger.info("Pexels search '%s': %d results", query, len(results))
        return tuple(results)

    async def search_photos(
        self,
        query: str,
        *,
        orientation: str = "landscape",
        per_page: int = 5,
    ) -> tuple[PhotoResult, ...]:
        """Search Pexels for stock photos matching the query."""
        params: dict[str, object] = {
            "query": query,
            "orientation": orientation,
            "per_page": per_page,
        }

        response = await self._client.get("/v1/search", params=params)
        response.raise_for_status()
        data = response.json()

        results: list[PhotoResult] = []
        for photo in data.get("photos", []):
            src = photo.get("src", {})
            url = src.get("large2x") or src.get("large") or src.get("original", "")
            if not url:
                continue

            results.append(
                PhotoResult(
                    provider_id=f"pexels:{photo['id']}",
                    url=url,
                    width=photo.get("width", 0),
                    height=photo.get("height", 0),
                )
            )

        logger.info("Pexels photo search '%s': %d results", query, len(results))
        return tuple(results)

    async def download_photo(
        self,
        photo: PhotoResult,
        *,
        output_path: Path,
    ) -> int:
        """Download a photo file via streaming."""
        return await self._download(photo.url, output_path)

    async def download_video(
        self,
        video: VideoResult,
        *,
        output_path: Path,
        quality: str = "hd",
    ) -> int:
        """Download a video file via streaming."""
        return await self._download(video.url, output_path)

    async def _download(self, url: str, output_path: Path) -> int:
        """Stream-download a file from *url* to *output_path*."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        async with self._client.stream("GET", url) as response:
            response.raise_for_status()
            byte_count = 0
            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
                    byte_count += len(chunk)

        logger.info("Pexels download: %d bytes -> %s", byte_count, output_path)
        return byte_count


def _pick_best_file(video_files: list[dict]) -> dict | None:
    """Pick the best HD video file from Pexels response."""
    hd_files = [
        f for f in video_files
        if f.get("quality") == "hd" and f.get("width", 0) >= 1280
    ]
    if hd_files:
        return max(hd_files, key=lambda f: f.get("width", 0))

    # Fallback to any available file
    if video_files:
        return max(video_files, key=lambda f: f.get("width", 0))

    return None
