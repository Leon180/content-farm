"""Visual generation pipeline stage."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from content_farm.config import Settings
from content_farm.script_gen.schemas import Script, VisualHint
from content_farm.visual.protocol import StockProvider
from content_farm.visual.schemas import VideoResult, VisualArtifact, VisualAsset

logger = logging.getLogger(__name__)


class VisualGenerator:
    """Sources visual assets for each scene in a script.

    Accepts any StockProvider implementation (Pexels, Pixabay, Kling, etc.).
    """

    def __init__(
        self,
        stock: StockProvider,
        settings: Settings,
        output_dir: Path | None = None,
    ) -> None:
        self._stock = stock
        self._settings = settings
        self._output_dir = output_dir or Path("output/visual")
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_scenes)

    async def generate(self, script: Script) -> VisualArtifact:
        """Source visual assets for all scenes in the script."""
        tasks = [
            self._source_scene_visual(scene.scene_number, scene.visual_hint, scene.duration_seconds)
            for scene in script.scenes
        ]

        assets = await asyncio.gather(*tasks)

        total_duration = sum(a.duration_seconds for a in assets)

        return VisualArtifact(
            assets=tuple(assets),
            total_duration_seconds=total_duration,
            output_dir=str(self._output_dir),
        )

    async def _source_scene_visual(
        self,
        scene_number: int,
        hint: VisualHint,
        target_duration: int,
    ) -> VisualAsset:
        """Search and download a visual asset for a single scene."""
        async with self._semaphore:
            query = _build_search_query(hint)
            output_path = self._output_dir / f"scene_{scene_number:03d}.mp4"

            results = await self._stock.search_videos(
                query,
                min_duration=max(3, target_duration // 2),
                max_duration=target_duration * 2,
            )

            if not results:
                # Retry with simpler query (description only)
                results = await self._stock.search_videos(
                    hint.description,
                    min_duration=3,
                    max_duration=120,
                )

            if not results:
                logger.warning("No video found for scene %d: '%s'", scene_number, query)
                return VisualAsset(
                    scene_number=scene_number,
                    file_path="",
                    source="none",
                    duration_seconds=0.0,
                    query_used=query,
                )

            best = _pick_best_match(results, target_duration)

            await self._stock.download_video(best, output_path=output_path)

            return VisualAsset(
                scene_number=scene_number,
                file_path=str(output_path),
                source=best.provider_id.split(":")[0],
                duration_seconds=float(best.duration_seconds),
                query_used=query,
            )


def _build_search_query(hint: VisualHint) -> str:
    """Build a search query from a VisualHint."""
    parts = [hint.description]
    if hint.keywords:
        parts.extend(hint.keywords[:3])
    return " ".join(parts)


def _pick_best_match(results: tuple[VideoResult, ...], target_duration: int) -> VideoResult:
    """Pick the video closest to the target duration."""
    return min(results, key=lambda r: abs(r.duration_seconds - target_duration))
