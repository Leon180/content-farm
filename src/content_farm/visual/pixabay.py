"""Pixabay stock footage provider."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from content_farm.visual.schemas import PhotoResult, VideoResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://pixabay.com/api/videos/"


class PixabayProvider:
    """Async client for the Pixabay Video API (free, 100 req/min)."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=30.0)

    async def search_videos(
        self,
        query: str,
        *,
        min_duration: int = 5,
        max_duration: int = 30,
        orientation: str = "portrait",
        per_page: int = 15,
    ) -> tuple[VideoResult, ...]:
        """Search Pixabay for stock videos matching the query."""
        params: dict[str, object] = {
            "key": self._api_key,
            "q": query,
            "per_page": min(per_page, 200),
            "video_type": "film",
            "safesearch": "true",
        }

        response = await self._client.get(_BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

        results: list[VideoResult] = []
        for hit in data.get("hits", []):
            duration = hit.get("duration", 0)
            if duration < min_duration or duration > max_duration:
                continue

            video_file = _pick_best_file(hit.get("videos", {}), orientation)
            if video_file is None:
                continue

            results.append(
                VideoResult(
                    provider_id=f"pixabay:{hit['id']}",
                    url=video_file["url"],
                    duration_seconds=duration,
                    width=video_file.get("width", 0),
                    height=video_file.get("height", 0),
                    thumbnail_url=hit.get("videos", {}).get("tiny", {}).get("thumbnail", ""),
                )
            )

        logger.info("Pixabay search '%s': %d results", query, len(results))
        return tuple(results)

    async def search_photos(
        self,
        query: str,
        *,
        orientation: str = "horizontal",
        per_page: int = 5,
    ) -> tuple[PhotoResult, ...]:
        """Search Pixabay for stock photos matching the query."""
        params: dict[str, object] = {
            "key": self._api_key,
            "q": query,
            "per_page": min(per_page, 200),
            "image_type": "photo",
            "orientation": orientation,
            "safesearch": "true",
        }

        response = await self._client.get(
            "https://pixabay.com/api/", params=params,
        )
        response.raise_for_status()
        data = response.json()

        results: list[PhotoResult] = []
        for hit in data.get("hits", []):
            url = hit.get("largeImageURL") or hit.get("webformatURL", "")
            if not url:
                continue

            results.append(
                PhotoResult(
                    provider_id=f"pixabay:{hit['id']}",
                    url=url,
                    width=hit.get("imageWidth", 0),
                    height=hit.get("imageHeight", 0),
                )
            )

        logger.info("Pixabay photo search '%s': %d results", query, len(results))
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

        logger.info("Pixabay download: %d bytes -> %s", byte_count, output_path)
        return byte_count


def _pick_best_file(
    videos: dict[str, dict], orientation: str,
) -> dict | None:
    """Pick the best video file from Pixabay response.

    Pixabay provides: large (1920), medium (1280), small (960), tiny (640).
    For portrait content, prefer files where height > width.
    """
    # Preferred quality order
    for quality in ("large", "medium", "small"):
        entry = videos.get(quality)
        if not entry or not entry.get("url"):
            continue

        w = entry.get("width", 0)
        h = entry.get("height", 0)

        # If requesting portrait, skip landscape videos
        if orientation == "portrait" and w > h:
            continue

        return entry

    # Fallback: any available file (ignore orientation)
    for quality in ("large", "medium", "small", "tiny"):
        entry = videos.get(quality)
        if entry and entry.get("url"):
            return entry

    return None
