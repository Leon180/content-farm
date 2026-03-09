"""Tests for AI image generation integration in VisualGenerator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from content_farm.config import Settings
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.visual.generator import (
    VisualGenerator,
    _build_image_prompt,
    _should_use_ai,
)
from content_farm.visual.schemas import VideoResult


def _make_video_result(duration: int = 15) -> VideoResult:
    return VideoResult(
        provider_id="pexels:100",
        url="https://example.com/pexels100.mp4",
        duration_seconds=duration,
        width=1920,
        height=1080,
    )


def _make_script(source_preference: str = "auto", style: str = "stock_footage") -> Script:
    return Script(
        video_title="測試",
        description="測試",
        language="zh-TW",
        scenes=(
            Scene(
                scene_number=1,
                title="場景1",
                narration="旁白",
                visual_hint=VisualHint(
                    description="a futuristic city",
                    keywords=("city", "future"),
                    source_preference=source_preference,
                    style=style,
                ),
                duration_seconds=10,
            ),
        ),
    )


# ---------------------------------------------------------------------------
# _should_use_ai
# ---------------------------------------------------------------------------


class TestShouldUseAi:
    def test_ai_preference_with_provider(self) -> None:
        hint = VisualHint(description="x", source_preference="ai")
        assert _should_use_ai(hint, has_image_provider=True) is True

    def test_ai_preference_without_provider(self) -> None:
        hint = VisualHint(description="x", source_preference="ai")
        assert _should_use_ai(hint, has_image_provider=False) is False

    def test_stock_preference(self) -> None:
        hint = VisualHint(description="x", source_preference="stock")
        assert _should_use_ai(hint, has_image_provider=True) is False

    def test_auto_with_ai_style(self) -> None:
        hint = VisualHint(description="x", source_preference="auto", style="ai_image")
        assert _should_use_ai(hint, has_image_provider=True) is True

    def test_auto_with_stock_style(self) -> None:
        hint = VisualHint(description="x", source_preference="auto", style="stock_footage")
        assert _should_use_ai(hint, has_image_provider=True) is False

    def test_auto_without_provider(self) -> None:
        hint = VisualHint(description="x", source_preference="auto", style="ai_image")
        assert _should_use_ai(hint, has_image_provider=False) is False


# ---------------------------------------------------------------------------
# _build_image_prompt
# ---------------------------------------------------------------------------


class TestBuildImagePrompt:
    def test_includes_description(self) -> None:
        hint = VisualHint(description="a futuristic city")
        prompt = _build_image_prompt(hint)
        assert "futuristic city" in prompt
        assert "cinematic" in prompt

    def test_includes_keywords(self) -> None:
        hint = VisualHint(description="city", keywords=("neon", "night"))
        prompt = _build_image_prompt(hint)
        assert "neon" in prompt
        assert "night" in prompt


# ---------------------------------------------------------------------------
# VisualGenerator — AI path
# ---------------------------------------------------------------------------


@pytest.fixture
def ai_generator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> tuple[VisualGenerator, AsyncMock, AsyncMock]:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]

    mock_stock = AsyncMock()
    mock_stock.search_videos.return_value = (_make_video_result(),)
    mock_stock.download_video.return_value = 500_000

    mock_image = AsyncMock()
    mock_image.generate_image.return_value = tmp_path / "scene_001.png"

    gen = VisualGenerator(
        stock=mock_stock,
        settings=settings,
        output_dir=tmp_path / "visual",
        image_provider=mock_image,
    )
    return gen, mock_stock, mock_image


@pytest.mark.asyncio
async def test_ai_preference_uses_image_provider(
    ai_generator: tuple[VisualGenerator, AsyncMock, AsyncMock],
    tmp_path: Path,
) -> None:
    gen, mock_stock, mock_image = ai_generator
    script = _make_script(source_preference="ai")

    async def _fake_i2v(image_path, output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-video")
        return output_path

    with patch("content_farm.visual.image_to_video.image_to_video", side_effect=_fake_i2v):
        artifact = await gen.generate(script)

    assert len(artifact.assets) == 1
    assert artifact.assets[0].source == "ai_gemini"
    mock_image.generate_image.assert_called_once()
    mock_stock.search_videos.assert_not_called()


@pytest.mark.asyncio
async def test_stock_preference_skips_image_provider(
    ai_generator: tuple[VisualGenerator, AsyncMock, AsyncMock],
) -> None:
    gen, mock_stock, mock_image = ai_generator
    script = _make_script(source_preference="stock")

    artifact = await gen.generate(script)

    assert artifact.assets[0].source == "pexels"
    mock_image.generate_image.assert_not_called()
    mock_stock.search_videos.assert_called_once()


@pytest.mark.asyncio
async def test_ai_fallback_to_stock_on_failure(
    ai_generator: tuple[VisualGenerator, AsyncMock, AsyncMock],
) -> None:
    gen, mock_stock, mock_image = ai_generator
    script = _make_script(source_preference="ai")

    # Image generation fails
    mock_image.generate_image.side_effect = RuntimeError("API error")

    artifact = await gen.generate(script)

    # Should fall back to stock
    assert artifact.assets[0].source == "pexels"
    mock_image.generate_image.assert_called_once()
    mock_stock.search_videos.assert_called_once()


@pytest.mark.asyncio
async def test_auto_preference_with_ai_style(
    ai_generator: tuple[VisualGenerator, AsyncMock, AsyncMock],
    tmp_path: Path,
) -> None:
    gen, mock_stock, mock_image = ai_generator
    script = _make_script(source_preference="auto", style="ai_image")

    async def _fake_i2v(image_path, output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-video")
        return output_path

    with patch("content_farm.visual.image_to_video.image_to_video", side_effect=_fake_i2v):
        artifact = await gen.generate(script)

    assert artifact.assets[0].source == "ai_gemini"


@pytest.mark.asyncio
async def test_auto_preference_with_stock_style(
    ai_generator: tuple[VisualGenerator, AsyncMock, AsyncMock],
) -> None:
    gen, mock_stock, mock_image = ai_generator
    script = _make_script(source_preference="auto", style="stock_footage")

    artifact = await gen.generate(script)

    # auto + stock_footage style → use stock
    assert artifact.assets[0].source == "pexels"
    mock_image.generate_image.assert_not_called()


@pytest.mark.asyncio
async def test_no_image_provider_always_stock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]

    mock_stock = AsyncMock()
    mock_stock.search_videos.return_value = (_make_video_result(),)
    mock_stock.download_video.return_value = 500_000

    gen = VisualGenerator(
        stock=mock_stock,
        settings=settings,
        output_dir=tmp_path / "visual",
        image_provider=None,
    )
    script = _make_script(source_preference="ai")

    artifact = await gen.generate(script)

    # No image provider — should use stock even with ai preference
    assert artifact.assets[0].source == "pexels"
