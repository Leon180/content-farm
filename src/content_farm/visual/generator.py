"""Visual generation pipeline stage — stock footage + AI image mixed strategy."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from content_farm.config import Settings
from content_farm.script_gen.schemas import Script, VisualHint
from content_farm.visual.image_protocol import ImageProvider
from content_farm.visual.protocol import StockProvider
from content_farm.visual.concat import concat_clips

if TYPE_CHECKING:
    from content_farm.visual.timeline import TimelineBlock
from content_farm.visual.schemas import (
    ClipInfo,
    ClipsManifest,
    VideoResult,
    VisualArtifact,
    VisualAsset,
)

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
        clips_per_keyword: int = 3,
    ) -> None:
        self._stock = stock
        self._image_provider = image_provider
        self._settings = settings
        self._output_dir = output_dir or Path("output/visual")
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_scenes)
        self._clips_per_keyword = clips_per_keyword
        self._global_seen_ids: set[str] = set()

    async def generate(
        self,
        script: Script,
        duration_overrides: dict[int, float] | None = None,
    ) -> VisualArtifact:
        """Source visual assets for all scenes in the script.

        Args:
            duration_overrides: map of scene_number → actual audio duration
                in seconds. When provided, uses audio length instead of the
                script's estimated duration.
        """
        overrides = duration_overrides or {}
        tasks = []
        for scene in script.scenes:
            dur = overrides[scene.scene_number] if scene.scene_number in overrides else float(scene.duration_seconds)
            tasks.append(self._source_scene_visual(scene.scene_number, scene.visual_hint, dur))


        assets = await asyncio.gather(*tasks)

        total_duration = sum(a.duration_seconds for a in assets)

        return VisualArtifact(
            assets=tuple(assets),
            total_duration_seconds=total_duration,
            output_dir=str(self._output_dir),
        )

    async def download_timeline_clips(
        self,
        blocks: list[TimelineBlock],
    ) -> ClipsManifest:
        """Download candidate clips for each timeline block.

        Clips are named ``MM:SS~MM:SS_NN.mp4`` (with index) so the user
        can review, pick the best one, and rename it without the index.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        tasks = [self._download_block_clips(b) for b in blocks]
        results = await asyncio.gather(*tasks)

        all_clips: list[ClipInfo] = []
        for clip_list in results:
            all_clips.extend(clip_list)

        return ClipsManifest(
            clips=all_clips,
            output_dir=str(self._output_dir),
        )

    async def _download_block_clips(
        self,
        block: TimelineBlock,
    ) -> list[ClipInfo]:
        """Download candidate clips for a single timeline block."""
        async with self._semaphore:
            keywords = block.keywords[:4] if block.keywords else ["stock footage"]
            clip_target = max(3.0, block.duration / max(len(keywords), 1))

            clips: list[ClipInfo] = []
            clip_idx = 1

            for term in keywords:
                results = await self._stock.search_videos(
                    term,
                    min_duration=3,
                    max_duration=clip_target * 3,
                )
                unique = [
                    r for r in results if r.provider_id not in self._global_seen_ids
                ]
                if not unique:
                    continue

                sorted_results = sorted(
                    unique, key=lambda r: abs(r.duration_seconds - clip_target)
                )
                to_download = sorted_results[: self._clips_per_keyword]

                for result in to_download:
                    file_name = f"{block.label}_{clip_idx:02d}.mp4"
                    clip_path = self._output_dir / file_name

                    try:
                        await self._stock.download_video(result, output_path=clip_path)
                    except Exception:
                        logger.warning(
                            "Failed to download %s for %s",
                            result.provider_id, block.label,
                            exc_info=True,
                        )
                        continue

                    self._global_seen_ids.add(result.provider_id)
                    clips.append(
                        ClipInfo(
                            scene_number=block.scene_number,
                            clip_index=clip_idx,
                            file_name=file_name,
                            keyword=term,
                            provider_id=result.provider_id,
                            duration_seconds=float(result.duration_seconds),
                            width=result.width,
                            height=result.height,
                            thumbnail_url=result.thumbnail_url,
                        )
                    )
                    clip_idx += 1

            if not clips:
                logger.warning("No clips found for block %s", block.label)

            return clips

    async def download_clips(
        self,
        script: Script,
        duration_overrides: dict[int, float] | None = None,
    ) -> ClipsManifest:
        """Download multiple candidate clips per scene without concatenating.

        Returns a ClipsManifest for user review. Each keyword yields up to
        ``clips_per_keyword`` clips. Cross-scene deduplication is enforced.
        """
        overrides = duration_overrides or {}
        self._output_dir.mkdir(parents=True, exist_ok=True)

        tasks = []
        for scene in script.scenes:
            dur = (
                overrides[scene.scene_number]
                if scene.scene_number in overrides
                else float(scene.duration_seconds)
            )
            tasks.append(
                self._download_scene_clips(scene.scene_number, scene.visual_hint, dur)
            )

        results = await asyncio.gather(*tasks)
        all_clips: list[ClipInfo] = []
        for clip_list in results:
            all_clips.extend(clip_list)

        return ClipsManifest(
            clips=all_clips,
            output_dir=str(self._output_dir),
        )

    async def _download_scene_clips(
        self,
        scene_number: int,
        hint: VisualHint,
        target_duration: float,
    ) -> list[ClipInfo]:
        """Download multiple candidate clips for a single scene."""
        async with self._semaphore:
            keywords = hint.keywords or [hint.description[:50]]
            search_terms = keywords[:4]
            clip_target = max(3.0, target_duration / len(search_terms))

            clips: list[ClipInfo] = []
            clip_idx = 1

            for term in search_terms:
                results = await self._stock.search_videos(
                    term,
                    min_duration=3,
                    max_duration=clip_target * 3,
                )
                unique = [
                    r for r in results if r.provider_id not in self._global_seen_ids
                ]
                if not unique:
                    continue

                # Sort by duration proximity, take top N
                sorted_results = sorted(
                    unique, key=lambda r: abs(r.duration_seconds - clip_target)
                )
                to_download = sorted_results[: self._clips_per_keyword]

                for result in to_download:
                    file_name = f"scene_{scene_number:03d}_{clip_idx:02d}.mp4"
                    clip_path = self._output_dir / file_name

                    try:
                        await self._stock.download_video(result, output_path=clip_path)
                    except Exception:
                        logger.warning(
                            "Failed to download %s for scene %d",
                            result.provider_id,
                            scene_number,
                            exc_info=True,
                        )
                        continue

                    self._global_seen_ids.add(result.provider_id)
                    clips.append(
                        ClipInfo(
                            scene_number=scene_number,
                            clip_index=clip_idx,
                            file_name=file_name,
                            keyword=term,
                            provider_id=result.provider_id,
                            duration_seconds=float(result.duration_seconds),
                            width=result.width,
                            height=result.height,
                            thumbnail_url=result.thumbnail_url,
                        )
                    )
                    clip_idx += 1

            if not clips:
                logger.warning("No clips found for scene %d", scene_number)

            return clips

    async def _source_scene_visual(
        self,
        scene_number: int,
        hint: VisualHint,
        target_duration: float,
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
        target_duration: float,
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
                aspect_ratio="9:16",
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
        target_duration: float,
        output_path: Path,
        query: str,
    ) -> VisualAsset:
        """Search and download multiple stock clips for a scene, then concat.

        Downloads one clip per keyword (up to 4) to provide visual variety,
        then concatenates them into a single scene file.
        """
        keywords = hint.keywords or [hint.description[:50]]
        # Use individual keywords for separate searches (more visual variety)
        search_terms = keywords[:4]
        clip_target = max(3.0, target_duration / len(search_terms))

        clip_paths: list[Path] = []
        seen_ids: set[str] = set()

        for i, term in enumerate(search_terms):
            results = await self._stock.search_videos(
                term,
                min_duration=3,
                max_duration=clip_target * 3,
            )
            # Filter out duplicates across searches
            unique = tuple(r for r in results if r.provider_id not in seen_ids)
            if not unique:
                continue

            best = _pick_best_match(unique, clip_target)
            seen_ids.add(best.provider_id)

            clip_path = output_path.parent / f"scene_{scene_number:03d}_clip{i:02d}.mp4"
            await self._stock.download_video(best, output_path=clip_path)
            clip_paths.append(clip_path)

        if not clip_paths:
            logger.warning("No video found for scene %d: '%s'", scene_number, query)
            return VisualAsset(
                scene_number=scene_number,
                file_path="",
                source="none",
                duration_seconds=0.0,
                query_used=query,
            )

        # Single clip — just rename
        if len(clip_paths) == 1:
            clip_paths[0].rename(output_path)
        else:
            await concat_clips(
                clip_paths, output_path, self._settings.ffmpeg_path,
            )
            # Clean up individual clips
            for cp in clip_paths:
                cp.unlink(missing_ok=True)

        return VisualAsset(
            scene_number=scene_number,
            file_path=str(output_path),
            source="stock_multi",
            duration_seconds=float(target_duration),
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


def _pick_best_match(results: tuple[VideoResult, ...], target_duration: float) -> VideoResult:
    """Pick the video closest to the target duration."""
    return min(results, key=lambda r: abs(r.duration_seconds - target_duration))




