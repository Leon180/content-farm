"""Script generation orchestrator. Two-phase: outline then expand."""

from __future__ import annotations

import asyncio
import logging

from content_farm.config import Settings
from content_farm.llm.cache import ResponseCache
from content_farm.llm.client import LLMClient
from content_farm.script_gen.prompts import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_LONG,
    build_chapter_outline_prompt,
    build_chapter_scene_breakdown_prompt,
    build_outline_prompt,
    build_scene_narration_prompt,
)
from content_farm.types import VideoLength
from content_farm.script_gen.schemas import (
    ChapterOutline,
    ChapterOutlineList,
    ExpandedScene,
    Scene,
    SceneOutline,
    SceneOutlineList,
    Script,
    ScriptRequest,
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
        """Full script generation pipeline. Dispatches short vs long-form."""
        if request.video_length == VideoLength.SHORT:
            return await self._generate_short(request)
        return await self._generate_long(request)

    async def _generate_short(self, request: ScriptRequest) -> Script:
        """Short-form path: flat outline → per-scene expansion."""
        outline = await self._generate_outline(request)
        scenes = await self._expand_scenes(request, outline)
        return self._assemble_script(request, outline, scenes)

    async def _generate_long(self, request: ScriptRequest) -> Script:
        """Long-form path: chapter outline → per-chapter scene breakdown → expand."""
        chapters = await self.generate_chapter_outline_only(request)
        return await self.generate_from_approved_chapters(request, chapters)

    async def generate_chapter_outline_only(
        self, request: ScriptRequest
    ) -> ChapterOutlineList:
        """Produce chapter-level outline only — used by the prescript gate.

        Normalizes chapter 1's start_timestamp to 0.0 and recomputes subsequent
        timestamps from durations (defends against model drift).
        """
        prompt = build_chapter_outline_prompt(request)
        cache_key = ResponseCache.make_key("chapter_outline", prompt)

        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.info("Chapter outline cache hit for topic=%s", request.topic)
            return self._normalize_chapter_timestamps(
                ChapterOutlineList.model_validate(cached)
            )

        result = await self._llm.generate_structured(
            system=SYSTEM_PROMPT_LONG,
            user_prompt=prompt,
            output_schema=ChapterOutlineList,
            model=self._settings.llm_cheap_model,
        )

        normalized = self._normalize_chapter_timestamps(result)
        await self._cache.set(cache_key, normalized.model_dump())
        return normalized

    async def generate_from_approved_chapters(
        self,
        request: ScriptRequest,
        chapters: ChapterOutlineList,
    ) -> Script:
        """Expand an approved chapter outline into a full Script.

        Used by both the automated long-form path and the --from-prescript flow.
        """
        scene_groups = await self._breakdown_chapters_into_scenes(request, chapters)
        expanded = await self._expand_long_form_scenes(
            request=request,
            chapters=chapters.chapters,
            scene_groups=scene_groups,
        )
        return self._assemble_long_form_script(request, chapters, expanded)

    async def _breakdown_chapters_into_scenes(
        self,
        request: ScriptRequest,
        chapters: ChapterOutlineList,
    ) -> list[tuple[SceneOutline, ...]]:
        """For each chapter, produce a tuple of scene outlines."""
        total = len(chapters.chapters)
        tasks = [
            self._breakdown_single_chapter(request, ch, total)
            for ch in chapters.chapters
        ]
        return list(await asyncio.gather(*tasks))

    async def _breakdown_single_chapter(
        self,
        request: ScriptRequest,
        chapter: ChapterOutline,
        total_chapters: int,
    ) -> tuple[SceneOutline, ...]:
        async with self._semaphore:
            prompt = build_chapter_scene_breakdown_prompt(
                request=request,
                chapter=chapter,
                total_chapters=total_chapters,
            )
            cache_key = ResponseCache.make_key("chapter_breakdown", prompt)

            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.info("Chapter breakdown cache hit: ch %d", chapter.chapter_number)
                return tuple(
                    SceneOutlineList.model_validate(cached).scenes
                )

            result = await self._llm.generate_structured(
                system=SYSTEM_PROMPT_LONG,
                user_prompt=prompt,
                output_schema=SceneOutlineList,
                model=self._settings.llm_cheap_model,
            )
            await self._cache.set(cache_key, result.model_dump())
            return tuple(result.scenes)

    async def _expand_long_form_scenes(
        self,
        *,
        request: ScriptRequest,
        chapters: tuple[ChapterOutline, ...],
        scene_groups: list[tuple[SceneOutline, ...]],
    ) -> tuple[Scene, ...]:
        """Expand every scene across all chapters with globally renumbered IDs."""
        total_scenes = sum(len(g) for g in scene_groups)
        tasks: list[asyncio.Future[Scene]] = []
        global_scene_index = 0

        for chapter, scenes in zip(chapters, scene_groups, strict=True):
            chapter_scene_count = len(scenes)
            for local_index, scene in enumerate(scenes):
                global_scene_index += 1
                tasks.append(
                    self._expand_single_long_scene(
                        request=request,
                        chapter=chapter,
                        scene=scene,
                        global_scene_number=global_scene_index,
                        total_scenes=total_scenes,
                        is_chapter_opener=(local_index == 0),
                        is_chapter_closer=(local_index == chapter_scene_count - 1),
                    )
                )

        expanded = await asyncio.gather(*tasks)
        return tuple(expanded)

    async def _expand_single_long_scene(
        self,
        *,
        request: ScriptRequest,
        chapter: ChapterOutline,
        scene: SceneOutline,
        global_scene_number: int,
        total_scenes: int,
        is_chapter_opener: bool,
        is_chapter_closer: bool,
    ) -> Scene:
        """Expand one long-form scene into full narration."""
        async with self._semaphore:
            prompt = build_scene_narration_prompt(
                topic=request.topic,
                tone=request.tone.value,
                language=request.language,
                scene_title=scene.title,
                scene_summary=scene.summary,
                scene_number=global_scene_number,
                total_scenes=total_scenes,
                duration_seconds=int(scene.duration_seconds),
                is_short_form=False,
                is_long_form=True,
                genre=request.genre,
                chapter_number=chapter.chapter_number,
                chapter_title=chapter.title,
                is_chapter_opener=is_chapter_opener,
                is_chapter_closer=is_chapter_closer,
            )
            cache_key = ResponseCache.make_key("scene_long", prompt)

            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.info("Long scene cache hit: %d", global_scene_number)
                return Scene.model_validate(cached)

            expanded = await self._llm.generate_structured(
                system=SYSTEM_PROMPT_LONG,
                user_prompt=prompt,
                output_schema=ExpandedScene,
                model=self._settings.llm_expensive_model,
            )

            built = Scene(
                scene_number=global_scene_number,
                title=expanded.title,
                narration=expanded.narration,
                visual_hint=expanded.visual_hint,
                duration_seconds=expanded.duration_seconds,
                transition=expanded.transition,
                chapter_number=chapter.chapter_number,
                b_roll_keywords=tuple(expanded.visual_hint.keywords),
            )
            await self._cache.set(cache_key, built.model_dump())
            return built

    @staticmethod
    def _normalize_chapter_timestamps(
        chapters: ChapterOutlineList,
    ) -> ChapterOutlineList:
        """Force chapter 1 to start at 0.0 and recompute subsequent timestamps."""
        if not chapters.chapters:
            return chapters
        rebuilt: list[ChapterOutline] = []
        cursor = 0.0
        for ch in chapters.chapters:
            rebuilt.append(
                ChapterOutline(
                    chapter_number=ch.chapter_number,
                    title=ch.title,
                    summary=ch.summary,
                    duration_seconds=ch.duration_seconds,
                    key_points=ch.key_points,
                    hook=ch.hook,
                    payoff=ch.payoff,
                    start_timestamp=cursor,
                )
            )
            cursor += ch.duration_seconds
        return ChapterOutlineList(
            video_title=chapters.video_title,
            description=chapters.description,
            chapters=tuple(rebuilt),
            tags=chapters.tags,
            sources=chapters.sources,
        )

    def _assemble_long_form_script(
        self,
        request: ScriptRequest,
        chapters: ChapterOutlineList,
        scenes: tuple[Scene, ...],
    ) -> Script:
        total_duration = sum(s.duration_seconds for s in scenes)
        return Script(
            video_title=chapters.video_title,
            description=chapters.description,
            scenes=scenes,
            target_length=request.video_length,
            tone=request.tone,
            language=request.language,
            total_duration_seconds=total_duration,
            tags=tuple(chapters.tags) + tuple(request.keywords),
            sources=tuple(chapters.sources),
            ai_disclosure=True,
            orientation=request.orientation,
            genre=request.genre,
            chapters=chapters.chapters,
        )

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
                is_short_form=request.video_length == VideoLength.SHORT,
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
            sources=tuple(outline.sources),
            ai_disclosure=True,
        )
