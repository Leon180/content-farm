"""Tests for UploadGenerator, UploadStage, and factory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from content_farm.config import Settings
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.youtube.factory import create_youtube_uploader
from content_farm.youtube.generator import UploadGenerator, UploadStage
from content_farm.youtube.schemas import UploadInput


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
def mock_uploader() -> AsyncMock:
    uploader = AsyncMock()
    uploader.upload_video.return_value = "video123"
    return uploader


@pytest.mark.asyncio
async def test_generate_uploads_video(
    monkeypatch: pytest.MonkeyPatch,
    mock_uploader: AsyncMock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]

    video = tmp_path / "video.mp4"
    video.touch()

    gen = UploadGenerator(mock_uploader, settings)
    inp = UploadInput(script=_make_script(), video_path=str(video))
    artifact = await gen.generate(inp)

    assert mock_uploader.upload_video.call_count == 1
    assert artifact.stage == "youtube_upload"
    assert artifact.video_id == "video123"
    assert artifact.url == "https://youtu.be/video123"


@pytest.mark.asyncio
async def test_generate_sets_thumbnail(
    monkeypatch: pytest.MonkeyPatch,
    mock_uploader: AsyncMock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]

    video = tmp_path / "video.mp4"
    video.touch()
    thumb = tmp_path / "thumb.jpg"
    thumb.touch()

    gen = UploadGenerator(mock_uploader, settings)
    inp = UploadInput(
        script=_make_script(),
        video_path=str(video),
        thumbnail_path=str(thumb),
    )
    artifact = await gen.generate(inp)

    assert mock_uploader.set_thumbnail.call_count == 1
    assert artifact.thumbnail_set is True


@pytest.mark.asyncio
async def test_generate_sets_captions(
    monkeypatch: pytest.MonkeyPatch,
    mock_uploader: AsyncMock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]

    video = tmp_path / "video.mp4"
    video.touch()
    srt = tmp_path / "subs.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:05,000\nHello\n")

    gen = UploadGenerator(mock_uploader, settings)
    inp = UploadInput(
        script=_make_script(),
        video_path=str(video),
        subtitle_path=str(srt),
    )
    artifact = await gen.generate(inp)

    assert mock_uploader.set_captions.call_count == 1
    assert artifact.captions_set is True


@pytest.mark.asyncio
async def test_generate_skips_thumbnail_when_no_path(
    monkeypatch: pytest.MonkeyPatch,
    mock_uploader: AsyncMock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]

    video = tmp_path / "video.mp4"
    video.touch()

    gen = UploadGenerator(mock_uploader, settings)
    inp = UploadInput(script=_make_script(), video_path=str(video))
    artifact = await gen.generate(inp)

    mock_uploader.set_thumbnail.assert_not_called()
    assert artifact.thumbnail_set is False


@pytest.mark.asyncio
async def test_generate_skips_captions_when_no_path(
    monkeypatch: pytest.MonkeyPatch,
    mock_uploader: AsyncMock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]

    video = tmp_path / "video.mp4"
    video.touch()

    gen = UploadGenerator(mock_uploader, settings)
    inp = UploadInput(script=_make_script(), video_path=str(video))
    artifact = await gen.generate(inp)

    mock_uploader.set_captions.assert_not_called()
    assert artifact.captions_set is False


@pytest.mark.asyncio
async def test_generate_passes_language_to_captions(
    monkeypatch: pytest.MonkeyPatch,
    mock_uploader: AsyncMock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]

    video = tmp_path / "video.mp4"
    video.touch()
    srt = tmp_path / "subs.srt"
    srt.touch()

    gen = UploadGenerator(mock_uploader, settings)
    inp = UploadInput(
        script=_make_script(),
        video_path=str(video),
        subtitle_path=str(srt),
    )
    await gen.generate(inp)

    call_kwargs = mock_uploader.set_captions.call_args.kwargs
    assert call_kwargs["language"] == "zh-TW"


class TestUploadStage:
    @pytest.mark.asyncio
    async def test_validate_empty_title_raises(self) -> None:
        stage = UploadStage(generator=AsyncMock())  # type: ignore[arg-type]
        inp = UploadInput(
            script=Script(
                video_title="",
                description="d",
                language="zh-TW",
                scenes=(),
            ),
            video_path="/tmp/video.mp4",
        )
        with pytest.raises(ValueError, match="no video_title"):
            await stage.validate_input(inp)

    @pytest.mark.asyncio
    async def test_validate_missing_video_raises(self, tmp_path: Path) -> None:
        stage = UploadStage(generator=AsyncMock())  # type: ignore[arg-type]
        inp = UploadInput(
            script=_make_script(),
            video_path=str(tmp_path / "nonexistent.mp4"),
        )
        with pytest.raises(FileNotFoundError):
            await stage.validate_input(inp)

    @pytest.mark.asyncio
    async def test_validate_valid_input_passes(self, tmp_path: Path) -> None:
        stage = UploadStage(generator=AsyncMock())  # type: ignore[arg-type]
        video = tmp_path / "video.mp4"
        video.touch()
        inp = UploadInput(script=_make_script(), video_path=str(video))
        await stage.validate_input(inp)  # should not raise

    @pytest.mark.asyncio
    async def test_execute_delegates_to_generator(self) -> None:
        mock_gen = AsyncMock()
        stage = UploadStage(generator=mock_gen)
        inp = UploadInput(script=_make_script(), video_path="/tmp/video.mp4")
        await stage.execute(inp)
        assert mock_gen.generate.call_count == 1


class TestFactory:
    def test_creates_google_provider(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("CF_YOUTUBE_CLIENT_ID", "cid")
        monkeypatch.setenv("CF_YOUTUBE_CLIENT_SECRET", "csecret")
        monkeypatch.setenv("CF_YOUTUBE_REFRESH_TOKEN", "rtoken")
        settings = Settings()  # type: ignore[call-arg]
        uploader = create_youtube_uploader(settings)
        assert type(uploader).__name__ == "GoogleProvider"

    def test_unknown_provider_raises(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("CF_YOUTUBE_PROVIDER", "unknown")
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="Unknown YouTube provider"):
            create_youtube_uploader(settings)

    def test_missing_client_id_raises(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="CF_YOUTUBE_CLIENT_ID"):
            create_youtube_uploader(settings)

    def test_missing_client_secret_raises(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("CF_YOUTUBE_CLIENT_ID", "cid")
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="CF_YOUTUBE_CLIENT_SECRET"):
            create_youtube_uploader(settings)

    def test_missing_refresh_token_raises(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("CF_YOUTUBE_CLIENT_ID", "cid")
        monkeypatch.setenv("CF_YOUTUBE_CLIENT_SECRET", "csecret")
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="CF_YOUTUBE_REFRESH_TOKEN"):
            create_youtube_uploader(settings)

    def test_default_provider_is_google(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.youtube_provider == "google"
