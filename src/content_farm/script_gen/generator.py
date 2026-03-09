"""Script generation orchestrator. Two-phase: outline then expand."""

from __future__ import annotations

import asyncio
import logging

from content_farm.config import Settings
from content_farm.llm.cache import ResponseCache
from content_farm.llm.client import LLMClient
from content_farm.script_gen.prompts import (
    SYSTEM_PROMPT,
    build_outline_prompt,
    build_scene_narration_prompt,
)
from content_farm.script_gen.schemas import (
    ExpandedScene,
    Scene,
    SceneOutlineList,
    Script,
    ScriptRequest,
    VisualHint,
)

logger = logging.getLogger(__name__)


class ScriptGenerator:
    """Generates video scripts using a two-phase LLM approach.

    Phase 1 (cheap model): Generate scene outline.
    Phase 2 (expensive model): Expand each scene with full narration.
    """

    def __init__(
        self,
        llm: LLMClient,
        cache: ResponseCache,
        settings: Settings,
    ) -> None:
        self._llm = llm
        self._cache = cache
        self._settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_scenes)

    async def generate(self, request: ScriptRequest) -> Script:
        """Full script generation pipeline."""
        outline = await self._generate_outline(request)
        scenes = await self._expand_scenes(request, outline)
        return self._assemble_script(request, outline, scenes)

    async def _generate_outline(self, request: ScriptRequest) -> SceneOutlineList:
        """Phase 1: Generate scene outline using the cheap model."""
        prompt = build_outline_prompt(request)
        cache_key = ResponseCache.make_key("outline", prompt)

        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.info("Outline cache hit for topic=%s", request.topic)
            return SceneOutlineList.model_validate(cached)

        result = await self._llm.generate_structured(
            system=SYSTEM_PROMPT,
            user_prompt=prompt,
            output_schema=SceneOutlineList,
            model=self._settings.llm_cheap_model,
        )

        await self._cache.set(cache_key, result.model_dump())
        return result

    async def _expand_scenes(
        self, request: ScriptRequest, outline: SceneOutlineList
    ) -> tuple[Scene, ...]:
        """Phase 2: Expand each scene with full narration. Runs concurrently."""
        total = len(outline.scenes)
        tasks = [
            self._expand_single_scene(
                request=request,
                scene_title=scene.title,
                scene_summary=scene.summary,
                scene_number=scene.scene_number,
                duration_seconds=scene.duration_seconds,
                total_scenes=total,
            )
            for scene in outline.scenes
        ]
        expanded = await asyncio.gather(*tasks)
        return tuple(expanded)

    async def _expand_single_scene(
        self,
        *,
        request: ScriptRequest,
        scene_title: str,
        scene_summary: str,
        scene_number: int,
        duration_seconds: int,
        total_scenes: int,
    ) -> Scene:
        """Expand one scene into full narration + visual hint."""
        async with self._semaphore:
            prompt = build_scene_narration_prompt(
                topic=request.topic,
                tone=request.tone.value,
                language=request.language,
                scene_title=scene_title,
                scene_summary=scene_summary,
                scene_number=scene_number,
                total_scenes=total_scenes,
                duration_seconds=duration_seconds,
            )
            cache_key = ResponseCache.make_key("scene", prompt)

            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.info("Scene cache hit: scene %d", scene_number)
                return Scene.model_validate(cached)

            expanded = await self._llm.generate_structured(
                system=SYSTEM_PROMPT,
                user_prompt=prompt,
                output_schema=ExpandedScene,
                model=self._settings.llm_expensive_model,
            )

            scene = Scene(
                scene_number=expanded.scene_number,
                title=expanded.title,
                narration=expanded.narration,
                visual_hint=expanded.visual_hint,
                duration_seconds=expanded.duration_seconds,
                transition=expanded.transition,
            )
            await self._cache.set(cache_key, scene.model_dump())
            return scene

    @staticmethod
    def _assemble_script(
        request: ScriptRequest,
        outline: SceneOutlineList,
        scenes: tuple[Scene, ...],
    ) -> Script:
        """Assemble final Script from expanded scenes."""
        total_duration = sum(s.duration_seconds for s in scenes)
        return Script(
            video_title=outline.video_title,
            description=outline.description,
            scenes=scenes,
            target_length=request.video_length,
            tone=request.tone,
            language=request.language,
            total_duration_seconds=total_duration,
            tags=tuple(outline.tags) + tuple(request.keywords),
            ai_disclosure=True,
        )
