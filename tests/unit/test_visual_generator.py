"""Tests for the VisualGenerator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from content_farm.config import Settings
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.visual.generator import VisualGenerator, _build_search_query, _pick_best_match
from content_farm.visual.schemas import ClipInfo, ClipsManifest, VideoResult


async def _fake_concat(clip_paths, output_path, ffmpeg_path="ffmpeg"):
    """Stub concat that just copies the first clip."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(clip_paths[0], output_path)


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

    async def _fake_download(video, *, output_path, **kw):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-video")
        return 500_000

    mock_stock.download_video.side_effect = _fake_download

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
@patch("content_farm.visual.generator.concat_clips", side_effect=_fake_concat)
async def test_generate_creates_assets(
    _mock_concat,
    visual_generator: tuple[VisualGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, _ = visual_generator
    artifact = await gen.generate(sample_script)

    assert len(artifact.assets) == 2
    assert artifact.stage == "visual_generation"
    assert artifact.total_duration_seconds > 0


@pytest.mark.asyncio
@patch("content_farm.visual.generator.concat_clips", side_effect=_fake_concat)
async def test_generate_calls_search_per_scene(
    _mock_concat,
    visual_generator: tuple[VisualGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, mock_stock = visual_generator
    await gen.generate(sample_script)

    # Scene 1 has 3 keywords → 3 searches; scene 2 has description only → 1 search
    assert mock_stock.search_videos.call_count == 4
    # Downloads: scene 1 gets 2 unique clips, scene 2 gets 1
    assert mock_stock.download_video.call_count == 3


@pytest.mark.asyncio
@patch("content_farm.visual.generator.concat_clips", side_effect=_fake_concat)
async def test_generate_output_paths(
    _mock_concat,
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
@patch("content_farm.visual.generator.concat_clips", side_effect=_fake_concat)
async def test_generate_fallback_retry(
    _mock_concat,
    visual_generator: tuple[VisualGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, mock_stock = visual_generator
    # Return empty for some keyword searches, results for others
    mock_stock.search_videos.side_effect = [
        (),
        (_make_video_result(),),
        (_make_video_result(),),
        (_make_video_result(),),
    ]

    artifact = await gen.generate(sample_script)

    # First scene: some keyword searches failed, others succeeded
    assert artifact.assets[0].source == "stock_multi"
    # Multiple searches per scene (per keyword)
    assert mock_stock.search_videos.call_count >= 3


# ------------------------------------------------------------------
# download_clips tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_clips_returns_manifest(
    visual_generator: tuple[VisualGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, mock_stock = visual_generator
    # 2 results per search, 3 clips_per_keyword (default), but only 2 available
    mock_stock.search_videos.return_value = (
        _make_video_result("pexels:100", duration=10),
        _make_video_result("pexels:200", duration=15),
    )

    manifest = await gen.download_clips(sample_script)

    assert isinstance(manifest, ClipsManifest)
    assert len(manifest.clips) > 0
    # All clips default to not selected
    assert all(c.selected is False for c in manifest.clips)


@pytest.mark.asyncio
async def test_download_clips_multiple_per_keyword(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
    sample_script: Script,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]

    mock_stock = AsyncMock()
    # Each search call returns unique IDs so cross-scene dedup doesn't starve scene 2
    call_counter = {"n": 0}

    async def _varied_search(*args, **kwargs):
        base = call_counter["n"] * 10
        call_counter["n"] += 1
        return tuple(
            _make_video_result(f"pexels:{base + i}", duration=10 + i)
            for i in range(5)
        )

    mock_stock.search_videos.side_effect = _varied_search

    async def _fake_download(video, *, output_path, **kw):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-video")
        return 500_000

    mock_stock.download_video.side_effect = _fake_download

    gen = VisualGenerator(
        stock=mock_stock,
        settings=settings,
        output_dir=tmp_path / "visual",
        clips_per_keyword=3,
    )

    manifest = await gen.download_clips(sample_script)

    # Scene 1 has 3 keywords → 3 searches × up to 3 clips = up to 9
    # Scene 2 has 1 keyword → 1 search × up to 3 clips = up to 3
    # But dedup across scenes means scene 2 gets fewer
    scene_1_clips = [c for c in manifest.clips if c.scene_number == 1]
    scene_2_clips = [c for c in manifest.clips if c.scene_number == 2]
    assert len(scene_1_clips) >= 3
    assert len(scene_2_clips) >= 1


@pytest.mark.asyncio
async def test_download_clips_cross_scene_dedup(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
    sample_script: Script,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]

    mock_stock = AsyncMock()
    # Same results for every search — dedup should prevent reuse
    mock_stock.search_videos.return_value = (
        _make_video_result("pexels:999", duration=10),
    )

    async def _fake_download(video, *, output_path, **kw):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-video")
        return 500_000

    mock_stock.download_video.side_effect = _fake_download

    gen = VisualGenerator(
        stock=mock_stock,
        settings=settings,
        output_dir=tmp_path / "visual",
    )

    manifest = await gen.download_clips(sample_script)

    # pexels:999 should only appear once across all scenes
    provider_ids = [c.provider_id for c in manifest.clips]
    assert provider_ids.count("pexels:999") == 1


@pytest.mark.asyncio
async def test_download_clips_file_naming(
    visual_generator: tuple[VisualGenerator, AsyncMock],
    sample_script: Script,
) -> None:
    gen, _ = visual_generator

    manifest = await gen.download_clips(sample_script)

    for clip in manifest.clips:
        assert clip.file_name.startswith(f"scene_{clip.scene_number:03d}_")
        assert clip.file_name.endswith(".mp4")
        assert clip.clip_index >= 1
