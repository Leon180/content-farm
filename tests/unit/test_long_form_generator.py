"""Smoke tests for the long-form script generation path."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from content_farm.config import Settings
from content_farm.llm.cache import NullCache
from content_farm.script_gen.generator import ScriptGenerator
from content_farm.script_gen.schemas import (
    ChapterOutline,
    ChapterOutlineList,
    ExpandedScene,
    SceneOutline,
    SceneOutlineList,
    ScriptRequest,
    VisualHint,
)
from content_farm.types import GenreTemplate, Orientation, Tone, VideoLength


@pytest.fixture
def long_form_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ScriptGenerator, AsyncMock]:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]
    mock_llm = AsyncMock()
    gen = ScriptGenerator(llm=mock_llm, cache=NullCache(), settings=settings)
    return gen, mock_llm


def _make_chapter(num: int, dur: float, start: float = 0.0) -> ChapterOutline:
    return ChapterOutline(
        chapter_number=num,
        title=f"Chapter {num}",
        summary=f"Summary {num}",
        duration_seconds=dur,
        key_points=(f"point_a_{num}", f"point_b_{num}"),
        hook=f"Hook {num}",
        payoff=f"Payoff {num}",
        start_timestamp=start,
    )


def _make_scene_outline(num: int, dur: float = 30) -> SceneOutline:
    return SceneOutline(
        scene_number=num,
        title=f"Scene {num}",
        summary=f"Summary {num}",
        duration_seconds=dur,
    )


def _make_expanded_scene(num: int, dur: float = 30) -> ExpandedScene:
    return ExpandedScene(
        scene_number=num,
        title=f"Scene {num}",
        narration=f"Narration for scene {num}",
        visual_hint=VisualHint(
            description=f"Visual for scene {num}",
            style="stock_footage",
            keywords=(f"keyword_a_{num}", f"keyword_b_{num}"),
        ),
        duration_seconds=dur,
    )


@pytest.mark.asyncio
async def test_generate_long_chapter_to_scenes_to_narration(
    long_form_generator: tuple[ScriptGenerator, AsyncMock],
) -> None:
    gen, mock_llm = long_form_generator

    chapters = ChapterOutlineList(
        video_title="Long-form Test",
        description="Long-form description",
        chapters=(
            _make_chapter(1, 120, start=0.0),
            _make_chapter(2, 180, start=120.0),
        ),
        tags=("test",),
    )
    chapter_1_scenes = SceneOutlineList(
        video_title="Chapter 1",
        description="",
        scenes=(_make_scene_outline(1, 60), _make_scene_outline(2, 60)),
    )
    chapter_2_scenes = SceneOutlineList(
        video_title="Chapter 2",
        description="",
        scenes=(_make_scene_outline(1, 90), _make_scene_outline(2, 90)),
    )

    # Sequence: chapter outline → ch1 breakdown → ch2 breakdown → 4 scene expansions
    mock_llm.generate_structured.side_effect = [
        chapters,
        chapter_1_scenes,
        chapter_2_scenes,
        _make_expanded_scene(1, 60),
        _make_expanded_scene(2, 60),
        _make_expanded_scene(3, 90),
        _make_expanded_scene(4, 90),
    ]

    request = ScriptRequest(
        topic="Test Long-form Topic",
        video_length=VideoLength.LONG,
        orientation=Orientation.LANDSCAPE,
        genre=GenreTemplate.KNOWLEDGE,
    )
    script = await gen.generate(request)

    assert len(script.chapters) == 2
    assert script.chapters[0].start_timestamp == 0.0
    assert script.chapters[1].start_timestamp == 120.0
    assert len(script.scenes) == 4
    assert script.scenes[0].chapter_number == 1
    assert script.scenes[3].chapter_number == 2
    # Globally renumbered
    assert [s.scene_number for s in script.scenes] == [1, 2, 3, 4]
    # b_roll_keywords propagated from visual_hint.keywords
    assert script.scenes[0].b_roll_keywords == ("keyword_a_1", "keyword_b_1")
    assert script.orientation == Orientation.LANDSCAPE
    assert script.genre == GenreTemplate.KNOWLEDGE


@pytest.mark.asyncio
async def test_chapter_timestamps_are_normalized(
    long_form_generator: tuple[ScriptGenerator, AsyncMock],
) -> None:
    """Even if the model returns wrong timestamps, they get normalized."""
    gen, mock_llm = long_form_generator

    drifted = ChapterOutlineList(
        video_title="Drift Test",
        description="",
        chapters=(
            # Model claims chapter 1 starts at 5.0 — invalid for YouTube
            _make_chapter(1, 60, start=5.0),
            _make_chapter(2, 90, start=200.0),
        ),
    )
    mock_llm.generate_structured.return_value = drifted

    request = ScriptRequest(
        topic="Drift Test",
        video_length=VideoLength.LONG,
        orientation=Orientation.LANDSCAPE,
    )
    result = await gen.generate_chapter_outline_only(request)

    assert result.chapters[0].start_timestamp == 0.0
    assert result.chapters[1].start_timestamp == 60.0


@pytest.mark.asyncio
async def test_short_form_bypasses_chapter_path(
    long_form_generator: tuple[ScriptGenerator, AsyncMock],
) -> None:
    """SHORT video_length must NOT go through the chapter outline path."""
    gen, mock_llm = long_form_generator

    mock_llm.generate_structured.side_effect = [
        SceneOutlineList(
            video_title="Short",
            description="",
            scenes=(_make_scene_outline(1, 25), _make_scene_outline(2, 25)),
        ),
        _make_expanded_scene(1, 25),
        _make_expanded_scene(2, 25),
    ]

    request = ScriptRequest(
        topic="Short-form topic",
        video_length=VideoLength.SHORT,
        tone=Tone.EDUCATIONAL,
    )
    script = await gen.generate(request)

    # 1 outline call + 2 scene expansions = 3 total. No chapter calls.
    assert mock_llm.generate_structured.call_count == 3
    assert len(script.chapters) == 0
    assert len(script.scenes) == 2
