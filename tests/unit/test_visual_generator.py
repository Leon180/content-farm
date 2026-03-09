"""Tests for the VisualGenerator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from content_farm.config import Settings
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.visual.generator import VisualGenerator, _build_search_query, _pick_best_match
from content_farm.visual.schemas import VideoResult


@pytest.fixture
def sample_script() -> Script:
    return Script(
        video_title="測試影片",
        description="測試用影片",
        language="zh-TW",
        scenes=(
            Scene(
                scene_number=1,
                title="開場",
                narration="歡迎來到本期影片。",
                visual_hint=VisualHint(
                    description="city skyline at sunset",
                    keywords=("skyline", "sunset", "urban"),
                ),
                duration_seconds=15,
            ),
            Scene(
                scene_number=2,
                title="主體",
                narration="讓我們深入探討這個話題。",
                visual_hint=VisualHint(description="technology concept"),
                duration_seconds=30,
            ),
        ),
        total_duration_seconds=45,
    )


def _make_video_result(
    provider_id: str = "pexels:100",
    duration: int = 15,
    width: int = 1920,
    height: int = 1080,
) -> VideoResult:
    return VideoResult(
        provider_id=provider_id,
        url=f"https://example.com/{provider_id}.mp4",
        duration_seconds=duration,
        width=width,
        height=height,
    )


@pytest.fixture
def visual_generator(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> tuple[VisualGenerator, AsyncMock]:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]

    mock_stock = AsyncMock()
    mock_stock.search_videos.return_value = (
        _make_video_result("pexels:100", duration=15),
        _make_video_result("pexels:200", duration=20),
    )
    mock_stock.download_video.return_value = 500_000

    gen = VisualGenerator(
        stock=mock_stock,
        settings=settings,
        output_dir=tmp_path / "visual",
    )
    return gen, mock_stock


class TestBuildSearchQuery:
    def test_description_only(self) -> None:
        hint = VisualHint(description="ocean waves")
        assert _build_search_query(hint) == "ocean waves"

    def test_with_keywords(self) -> None:
        hint = VisualHint(
            description="ocean waves",
            keywords=("sea", "beach", "surf", "coast"),
        )
        query = _build_search_query(hint)
        # When keywords exist, uses first 4 keywords (no description)
        assert "sea" in query
        assert "beach" in query
        assert "surf" in query
        assert "coast" in query


class TestPickBestMatch:
    def test_picks_closest_duration(self) -> None:
        results = (
            _make_video_result(duration=5),
            _make_video_result(duration=14),
            _make_video_result(duration=25),
        )
        best = _pick_best_match(results, target_duration=15)
        assert best.duration_seconds == 14

    def test_exact_match(self) -> None:
        results = (
            _make_video_result(duration=10),
            _make_video_result(duration=15),
        )
        best = _pick_best_match(results, target_duration=15)
        assert best.duration_seconds == 15


@pytest.mark.asyncio
async def test_generate_creates_assets(
    visual_generator: tuple[VisualGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, _ = visual_generator
    artifact = await gen.generate(sample_script)

    assert len(artifact.assets) == 2
    assert artifact.stage == "visual_generation"
    assert artifact.total_duration_seconds > 0


@pytest.mark.asyncio
async def test_generate_calls_search_per_scene(
    visual_generator: tuple[VisualGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, mock_stock = visual_generator
    await gen.generate(sample_script)

    assert mock_stock.search_videos.call_count == 2
    assert mock_stock.download_video.call_count == 2


@pytest.mark.asyncio
async def test_generate_output_paths(
    visual_generator: tuple[VisualGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, _ = visual_generator
    artifact = await gen.generate(sample_script)

    assert "scene_001" in artifact.assets[0].file_path
    assert "scene_002" in artifact.assets[1].file_path


@pytest.mark.asyncio
async def test_generate_no_results_returns_empty_asset(
    visual_generator: tuple[VisualGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, mock_stock = visual_generator
    mock_stock.search_videos.return_value = ()

    artifact = await gen.generate(sample_script)

    assert len(artifact.assets) == 2
    assert artifact.assets[0].source == "none"
    assert artifact.assets[0].file_path == ""


@pytest.mark.asyncio
async def test_generate_fallback_retry(
    visual_generator: tuple[VisualGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, mock_stock = visual_generator
    # First call returns empty, second (fallback) returns results
    mock_stock.search_videos.side_effect = [
        (),
        (_make_video_result(),),
        (_make_video_result(),),
        (_make_video_result(),),
    ]

    artifact = await gen.generate(sample_script)

    # First scene: initial search failed, fallback succeeded
    assert artifact.assets[0].source == "pexels"
    # search_videos called at least 3 times (2 for scene 1, 1 for scene 2)
    assert mock_stock.search_videos.call_count >= 3
