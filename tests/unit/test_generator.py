"""Tests for the ScriptGenerator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from content_farm.config import Settings
from content_farm.llm.cache import NullCache
from content_farm.script_gen.generator import ScriptGenerator
from content_farm.script_gen.schemas import (
    ExpandedScene,
    SceneOutline,
    SceneOutlineList,
    ScriptRequest,
    VisualHint,
)
from content_farm.types import Tone, VideoLength


@pytest.fixture
def sample_outline() -> SceneOutlineList:
    return SceneOutlineList(
        video_title="How Bitcoin Works",
        description="A deep dive into Bitcoin",
        scenes=[
            SceneOutline(
                scene_number=1,
                title="Introduction",
                summary="Hook the viewer with a surprising Bitcoin fact",
                duration_seconds=30,
            ),
            SceneOutline(
                scene_number=2,
                title="What is Bitcoin?",
                summary="Explain the basics of Bitcoin",
                duration_seconds=60,
            ),
        ],
        tags=["bitcoin", "crypto"],
    )


@pytest.fixture
def sample_expanded_scene() -> ExpandedScene:
    return ExpandedScene(
        scene_number=1,
        title="Introduction",
        narration="Did you know that Bitcoin processes over 300,000 transactions daily?",
        visual_hint=VisualHint(
            description="Bitcoin logo animation",
            style="animation",
            keywords=["bitcoin", "crypto"],
        ),
        duration_seconds=30,
        transition="cut",
    )


@pytest.fixture
def generator(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ScriptGenerator, AsyncMock]:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]
    mock_llm = AsyncMock()
    cache = NullCache()
    gen = ScriptGenerator(llm=mock_llm, cache=cache, settings=settings)
    return gen, mock_llm


@pytest.mark.asyncio
async def test_generate_calls_outline_then_expand(
    generator: tuple[ScriptGenerator, AsyncMock],
    sample_outline: SceneOutlineList,
    sample_expanded_scene: ExpandedScene,
) -> None:
    gen, mock_llm = generator

    # Phase 1 returns outline, Phase 2 returns expanded scenes
    mock_llm.generate_structured.side_effect = [
        sample_outline,
        sample_expanded_scene,
        ExpandedScene(
            scene_number=2,
            title="What is Bitcoin?",
            narration="Bitcoin is a decentralized digital currency...",
            visual_hint=VisualHint(description="Blockchain diagram"),
            duration_seconds=60,
        ),
    ]

    request = ScriptRequest(
        topic="How Bitcoin Works",
        keywords=["bitcoin"],
        video_length=VideoLength.MEDIUM,
        tone=Tone.EDUCATIONAL,
    )
    script = await gen.generate(request)

    assert script.video_title == "How Bitcoin Works"
    assert len(script.scenes) == 2
    assert script.total_duration_seconds == 90
    assert script.ai_disclosure is True
    assert mock_llm.generate_structured.call_count == 3  # 1 outline + 2 scenes


@pytest.mark.asyncio
async def test_generate_uses_cache(
    monkeypatch: pytest.MonkeyPatch,
    sample_outline: SceneOutlineList,
    sample_expanded_scene: ExpandedScene,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]
    mock_llm = AsyncMock()
    mock_cache = AsyncMock()

    # Cache returns the outline on first call, None for scene expansions
    mock_cache.get.side_effect = [
        sample_outline.model_dump(),  # outline cache hit
        None,  # scene 1 cache miss
        None,  # scene 2 cache miss
    ]

    mock_llm.generate_structured.side_effect = [
        sample_expanded_scene,
        ExpandedScene(
            scene_number=2,
            title="Body",
            narration="Content here",
            visual_hint=VisualHint(description="Visual"),
            duration_seconds=60,
        ),
    ]

    gen = ScriptGenerator(llm=mock_llm, cache=mock_cache, settings=settings)
    request = ScriptRequest(topic="Bitcoin Test")

    script = await gen.generate(request)

    # Outline was cached, so only 2 LLM calls (for scenes)
    assert mock_llm.generate_structured.call_count == 2
    assert len(script.scenes) == 2


@pytest.mark.asyncio
async def test_script_tags_merge(
    generator: tuple[ScriptGenerator, AsyncMock],
    sample_outline: SceneOutlineList,
    sample_expanded_scene: ExpandedScene,
) -> None:
    gen, mock_llm = generator

    mock_llm.generate_structured.side_effect = [
        sample_outline,
        sample_expanded_scene,
        ExpandedScene(
            scene_number=2,
            title="Body",
            narration="Content",
            visual_hint=VisualHint(description="Visual"),
            duration_seconds=60,
        ),
    ]

    request = ScriptRequest(
        topic="Bitcoin",
        keywords=["blockchain", "mining"],
    )
    script = await gen.generate(request)

    # Tags should include both outline tags and request keywords
    assert "bitcoin" in script.tags
    assert "crypto" in script.tags
    assert "blockchain" in script.tags
    assert "mining" in script.tags
