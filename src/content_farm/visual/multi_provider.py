"""Multi-provider fallback for stock footage search."""

from __future__ import annotations

import logging
from pathlib import Path

from content_farm.visual.schemas import PhotoResult, VideoResult

logger = logging.getLogger(__name__)


class MultiStockProvider:
    """Tries multiple stock providers in order until results are found."""

    def __init__(self, providers: tuple, provider_names: tuple[str, ...]) -> None:
        self._providers = providers
        self._names = provider_names

    async def search_videos(
        self,
        query: str,
        *,
        min_duration: int = 5,
        max_duration: int = 30,
        orientation: str = "landscape",
        per_page: int = 15,
    ) -> tuple[VideoResult, ...]:
        """Search all providers and merge results for maximum variety."""
        all_results: list[VideoResult] = []
        for provider, name in zip(self._providers, self._names):
            try:
                results = await provider.search_videos(
                    query,
                    min_duration=min_duration,
                    max_duration=max_duration,
                    orientation=orientation,
                    per_page=per_page,
                )
                if results:
                    all_results.extend(results)
            except Exception:
                logger.warning("Provider %s failed for query '%s'", name, query, exc_info=True)
        return tuple(all_results)

    async def search_photos(
        self,
        query: str,
        *,
        orientation: str = "landscape",
        per_page: int = 5,
    ) -> tuple[PhotoResult, ...]:
        """Search all providers and merge photo results."""
        all_results: list[PhotoResult] = []
        for provider, name in zip(self._providers, self._names):
            try:
                results = await provider.search_photos(
                    query, orientation=orientation, per_page=per_page,
                )
                if results:
                    all_results.extend(results)
            except Exception:
                logger.warning(
                    "Provider %s photo search failed for '%s'",
                    name, query, exc_info=True,
                )
        return tuple(all_results)

    async def download_video(
        self,
        video: VideoResult,
        *,
        output_path: Path,
        quality: str = "hd",
    ) -> int:
        """Download from the correct provider based on provider_id prefix."""
        prefix = video.provider_id.split(":")[0]
        for provider, name in zip(self._providers, self._names):
            if name == prefix:
                return await provider.download_video(
                    video, output_path=output_path, quality=quality,
                )
        raise ValueError(f"No provider found for {video.provider_id}")

    async def download_photo(
        self,
        photo: PhotoResult,
        *,
        output_path: Path,
    ) -> int:
        """Download from the correct provider based on provider_id prefix."""
        prefix = photo.provider_id.split(":")[0]
        for provider, name in zip(self._providers, self._names):
            if name == prefix:
                return await provider.download_photo(
                    photo, output_path=output_path,
                )
        raise ValueError(f"No provider found for {photo.provider_id}")
