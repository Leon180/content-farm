"""Tests for ThumbnailGenerator, ThumbnailStage, and factory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from content_farm.config import Settings
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.thumbnail.factory import create_thumbnail_provider
from content_farm.thumbnail.generator import (
    ThumbnailGenerator,
    ThumbnailStage,
)
from content_farm.thumbnail.schemas import ThumbnailInput


def _make_script(title: str = "測試影片標題") -> Script:
    return Script(
        video_title=title,
        description="測試",
        language="zh-TW",
        scenes=(
            Scene(
                scene_number=1,
                title="開場",
                narration="歡迎",
                visual_hint=VisualHint(description="title"),
                duration_seconds=10,
            ),
        ),
    )


@pytest.fixture
def mock_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.render.return_value = 50_000  # 50KB
    return provider


@pytest.mark.asyncio
async def test_generate_calls_render(
    monkeypatch: pytest.MonkeyPatch,
    mock_provider: AsyncMock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]
    gen = ThumbnailGenerator(mock_provider, settings, output_dir=tmp_path)

    inp = ThumbnailInput(script=_make_script())
    artifact = await gen.generate(inp)

    assert mock_provider.render.call_count == 1
    assert artifact.stage == "thumbnail_generation"
    assert artifact.file_size_bytes == 50_000
    assert artifact.used_keyframe is False


@pytest.mark.asyncio
async def test_generate_passes_video_path(
    monkeypatch: pytest.MonkeyPatch,
    mock_provider: AsyncMock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]
    gen = ThumbnailGenerator(mock_provider, settings, output_dir=tmp_path)

    video = tmp_path / "video.mp4"
    video.touch()

    inp = ThumbnailInput(script=_make_script(), video_path=str(video))
    artifact = await gen.generate(inp)

    render_kwargs = mock_provider.render.call_args.kwargs
    assert render_kwargs["video_path"] == video
    assert artifact.used_keyframe is True


@pytest.mark.asyncio
async def test_generate_passes_title(
    monkeypatch: pytest.MonkeyPatch,
    mock_provider: AsyncMock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]
    gen = ThumbnailGenerator(mock_provider, settings, output_dir=tmp_path)

    inp = ThumbnailInput(script=_make_script("我的標題"))
    await gen.generate(inp)

    render_kwargs = mock_provider.render.call_args.kwargs
    assert render_kwargs["title"] == "我的標題"


@pytest.mark.asyncio
async def test_generate_creates_output_dir(
    monkeypatch: pytest.MonkeyPatch,
    mock_provider: AsyncMock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]
    out_dir = tmp_path / "new" / "subdir"
    gen = ThumbnailGenerator(mock_provider, settings, output_dir=out_dir)

    inp = ThumbnailInput(script=_make_script())
    await gen.generate(inp)

    assert out_dir.exists()


class TestThumbnailStage:
    @pytest.mark.asyncio
    async def test_validate_empty_title_raises(self) -> None:
        stage = ThumbnailStage(generator=AsyncMock())  # type: ignore[arg-type]
        inp = ThumbnailInput(
            script=Script(
                video_title="",
                description="d",
                language="zh-TW",
                scenes=(),
            ),
        )
        with pytest.raises(ValueError, match="no video_title"):
            await stage.validate_input(inp)

    @pytest.mark.asyncio
    async def test_validate_whitespace_title_raises(self) -> None:
        stage = ThumbnailStage(generator=AsyncMock())  # type: ignore[arg-type]
        inp = ThumbnailInput(
            script=Script(
                video_title="   ",
                description="d",
                language="zh-TW",
                scenes=(),
            ),
        )
        with pytest.raises(ValueError, match="no video_title"):
            await stage.validate_input(inp)

    @pytest.mark.asyncio
    async def test_validate_valid_input_passes(self) -> None:
        stage = ThumbnailStage(generator=AsyncMock())  # type: ignore[arg-type]
        inp = ThumbnailInput(script=_make_script())
        await stage.validate_input(inp)  # should not raise

    @pytest.mark.asyncio
    async def test_execute_delegates_to_generator(self) -> None:
        mock_gen = AsyncMock()
        stage = ThumbnailStage(generator=mock_gen)
        inp = ThumbnailInput(script=_make_script())
        await stage.execute(inp)
        assert mock_gen.generate.call_count == 1


class TestFactory:
    def test_creates_pillow_provider(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        settings = Settings()  # type: ignore[call-arg]
        provider = create_thumbnail_provider(settings)
        assert type(provider).__name__ == "PillowProvider"

    def test_unknown_provider_raises(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("CF_THUMBNAIL_PROVIDER", "unknown")
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="Unknown thumbnail provider"):
            create_thumbnail_provider(settings)

    def test_default_provider_is_pillow(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.thumbnail_provider == "pillow"

    def test_font_path_default_empty(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.thumbnail_font_path == ""
