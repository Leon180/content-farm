"""Visual generation pipeline stage — stock footage + AI image mixed strategy."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from content_farm.config import Settings
from content_farm.script_gen.schemas import Script, VisualHint
from content_farm.visual.image_protocol import ImageProvider
from content_farm.visual.protocol import StockProvider
from content_farm.visual.schemas import VideoResult, VisualArtifact, VisualAsset

logger = logging.getLogger(__name__)


class VisualGenerator:
    """Sources visual assets for each scene in a script.

    Supports mixed strategy: routes to AI image generation or stock footage
    based on each scene's VisualHint.source_preference.

    If image_provider is None, falls back to stock-only mode.
    """

    def __init__(
        self,
        stock: StockProvider,
        settings: Settings,
        output_dir: Path | None = None,
        *,
        image_provider: ImageProvider | None = None,
    ) -> None:
        self._stock = stock
        self._image_provider = image_provider
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
        """Route to AI image generation or stock footage based on source_preference."""
        async with self._semaphore:
            query = _build_search_query(hint)
            output_path = self._output_dir / f"scene_{scene_number:03d}.mp4"

            # Skip API call if file already exists (I-1: file-exists guard)
            if output_path.exists() and output_path.stat().st_size > 0:
                logger.info("Reusing existing visual: %s", output_path)
                return VisualAsset(
                    scene_number=scene_number,
                    file_path=str(output_path),
                    source="cached",
                    duration_seconds=float(target_duration),
                    query_used=query,
                )

            use_ai = _should_use_ai(hint, self._image_provider is not None)

            if use_ai:
                asset = await self._generate_ai_visual(
                    scene_number, hint, target_duration, output_path,
                )
                if asset is not None:
                    return asset
                # AI failed — fall through to stock footage
                logger.info("AI generation failed for scene %d, falling back to stock", scene_number)

            return await self._source_stock_visual(
                scene_number, hint, target_duration, output_path, query,
            )

    async def _generate_ai_visual(
        self,
        scene_number: int,
        hint: VisualHint,
        target_duration: int,
        output_path: Path,
    ) -> VisualAsset | None:
        """Generate an AI image and convert to video clip."""
        if self._image_provider is None:
            return None

        prompt = _build_image_prompt(hint)
        image_path = output_path.with_suffix(".png")

        try:
            image_path = await self._image_provider.generate_image(
                prompt,
                output_path=image_path,
                aspect_ratio="16:9",
            )
        except Exception:
            logger.warning(
                "Image generation failed for scene %d", scene_number, exc_info=True,
            )
            return None

        # Convert still image → video with Ken Burns effect
        try:
            from content_farm.visual.image_to_video import image_to_video

            await image_to_video(
                image_path,
                output_path,
                duration=float(target_duration),
                ffmpeg_path=self._settings.ffmpeg_path,
            )
        except Exception:
            logger.warning(
                "Image→video conversion failed for scene %d", scene_number, exc_info=True,
            )
            return None

        return VisualAsset(
            scene_number=scene_number,
            file_path=str(output_path),
            source="ai_gemini",
            duration_seconds=float(target_duration),
            query_used=prompt,
            format="mp4",
        )

    async def _source_stock_visual(
        self,
        scene_number: int,
        hint: VisualHint,
        target_duration: int,
        output_path: Path,
        query: str,
    ) -> VisualAsset:
        """Search and download stock footage for a scene."""
        results = await self._stock.search_videos(
            query,
            min_duration=max(3, target_duration // 2),
            max_duration=target_duration * 2,
        )

        if not results:
            # Retry with simpler query (first 2 keywords or truncated description)
            fallback = " ".join(hint.keywords[:2]) if hint.keywords else hint.description[:50]
            results = await self._stock.search_videos(
                fallback,
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


def _should_use_ai(hint: VisualHint, has_image_provider: bool) -> bool:
    """Decide whether to use AI image generation for this scene."""
    pref = hint.source_preference

    if pref == "ai":
        return has_image_provider
    if pref == "stock":
        return False
    # "auto" — use AI if available and the style suggests it
    if not has_image_provider:
        return False
    return hint.style in ("ai_image", "illustration", "concept_art", "diagram")


def _build_search_query(hint: VisualHint) -> str:
    """Build a concise search query from a VisualHint.

    Stock providers like Pexels work best with short English keyword queries.
    Use keywords first (they're designed for search), fall back to truncated description.
    """
    if hint.keywords:
        return " ".join(hint.keywords[:4])
    # Truncate description to avoid overly long queries
    return hint.description[:80]


def _build_image_prompt(hint: VisualHint) -> str:
    """Build an image generation prompt from a VisualHint.

    AI image generators work best with detailed, descriptive English prompts.
    """
    parts = [hint.description]
    if hint.keywords:
        parts.append(", ".join(hint.keywords[:4]))
    parts.append("cinematic, high quality, 4K, photorealistic")
    return ". ".join(parts)


def _pick_best_match(results: tuple[VideoResult, ...], target_duration: int) -> VideoResult:
    """Pick the video closest to the target duration."""
    return min(results, key=lambda r: abs(r.duration_seconds - target_duration))
