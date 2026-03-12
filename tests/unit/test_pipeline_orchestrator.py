"""Tests for ContentPipeline orchestrator — all providers mocked via ServiceContainer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from content_farm.assembly.schemas import AssemblyArtifact, ComposedScene
from content_farm.pipeline.container import ServiceContainer
from content_farm.pipeline.orchestrator import ContentPipeline, PipelineResult
from content_farm.script_gen.schemas import Scene, Script, ScriptRequest, VisualHint
from content_farm.subtitle.schemas import SubtitleArtifact, SubtitleSegment
from content_farm.thumbnail.schemas import ThumbnailArtifact
from content_farm.types import Tone, VideoLength
from content_farm.visual.schemas import VisualArtifact, VisualAsset
from content_farm.voice.schemas import AudioSegment, VoiceArtifact
from content_farm.youtube.schemas import UploadArtifact


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

def _make_script() -> Script:
    return Script(
        video_title="測試影片",
        description="測試描述",
        language="zh-TW",
        scenes=(
            Scene(
                scene_number=1,
                title="開場",
                narration="歡迎觀看",
                visual_hint=VisualHint(description="title"),
                duration_seconds=10,
            ),
        ),
    )


def _make_voice() -> VoiceArtifact:
    return VoiceArtifact(
        segments=(
            AudioSegment(
                scene_number=1,
                file_path="/tmp/audio/scene_1.mp3",
                duration_seconds=10.0,
                character_count=4,
            ),
        ),
        total_duration_seconds=10.0,
        total_characters=4,
        output_dir="/tmp/audio",
    )


def _make_visual() -> VisualArtifact:
    return VisualArtifact(
        assets=(
            VisualAsset(
                scene_number=1,
                file_path="/tmp/visual/scene_1.mp4",
                source="pexels",
                duration_seconds=10.0,
                query_used="title",
            ),
        ),
        total_duration_seconds=10.0,
        output_dir="/tmp/visual",
    )


def _make_subtitle() -> SubtitleArtifact:
    return SubtitleArtifact(
        file_path="/tmp/subtitles/subtitles.srt",
        segments=(
            SubtitleSegment(
                index=1,
                start_seconds=0.0,
                end_seconds=5.0,
                text="歡迎觀看",
                scene_number=1,
            ),
        ),
        total_segments=1,
        total_duration_seconds=10.0,
        output_dir="/tmp/subtitles",
    )


def _make_thumbnail() -> ThumbnailArtifact:
    return ThumbnailArtifact(
        file_path="/tmp/thumbnails/thumbnail.jpg",
        file_size_bytes=50000,
        output_dir="/tmp/thumbnails",
    )


def _make_assembly() -> AssemblyArtifact:
    return AssemblyArtifact(
        file_path="/tmp/assembly/final.mp4",
        scenes=(
            ComposedScene(
                scene_number=1,
                file_path="/tmp/assembly/scene_1.mp4",
                duration_seconds=10.0,
                video_source="pexels",
                audio_source="scene_1.mp3",
            ),
        ),
        total_duration_seconds=10.0,
        file_size_bytes=1000000,
        output_dir="/tmp/assembly",
    )


def _make_upload() -> UploadArtifact:
    return UploadArtifact(
        video_id="abc123",
        url="https://youtu.be/abc123",
        thumbnail_set=True,
        captions_set=True,
    )


def _make_request() -> ScriptRequest:
    return ScriptRequest(topic="量子計算入門")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def settings() -> MagicMock:
    """Mock Settings with all required attributes."""
    s = MagicMock()
    s.anthropic_api_key.get_secret_value.return_value = "fake-key"
    s.telegram_bot_token.get_secret_value.return_value = ""
    s.telegram_chat_id = ""
    s.youtube_client_id.get_secret_value.return_value = ""
    s.youtube_client_secret.get_secret_value.return_value = ""
    s.youtube_refresh_token.get_secret_value.return_value = ""
    s.cache_dir = Path(".cache/test")
    s.max_concurrent_scenes = 5
    s.log_level = "INFO"
    s.default_language = "zh-TW"
    s.tts_provider = "elevenlabs"
    s.stock_provider = "pexels"
    s.subtitle_provider = "estimation"
    s.thumbnail_provider = "pillow"
    s.ffmpeg_path = "ffmpeg"
    s.drive_credentials_path = ""
    s.drive_folder_id = ""
    return s


@pytest.fixture()
def mock_container() -> MagicMock:
    """Mock ServiceContainer with all factory methods returning test data."""
    container = MagicMock(spec=ServiceContainer)
    container.settings = MagicMock()
    container.settings.ffmpeg_path = "ffmpeg"

    # Script generator
    script_gen = MagicMock()
    script_gen.generate = AsyncMock(return_value=_make_script())
    container.create_script_generator.return_value = script_gen

    # Voice generator
    voice_gen = MagicMock()
    voice_gen.generate = AsyncMock(return_value=_make_voice())
    container.create_voice_generator.return_value = voice_gen

    # Visual generator
    visual_gen = MagicMock()
    visual_gen.generate = AsyncMock(return_value=_make_visual())
    container.create_visual_generator.return_value = visual_gen

    # Subtitle generator
    subtitle_gen = MagicMock()
    subtitle_gen.generate = AsyncMock(return_value=_make_subtitle())
    container.create_subtitle_generator.return_value = subtitle_gen

    # Thumbnail generator
    thumb_gen = MagicMock()
    thumb_gen.generate = AsyncMock(return_value=_make_thumbnail())
    container.create_thumbnail_generator.return_value = thumb_gen

    # Video assembler
    assembler = MagicMock()
    assembler.generate = AsyncMock(return_value=_make_assembly())
    container.create_video_assembler.return_value = assembler

    # Upload generator
    upload_gen = MagicMock()
    upload_gen.generate = AsyncMock(return_value=_make_upload())
    container.create_upload_generator.return_value = upload_gen

    # Drive uploader
    container.create_drive_uploader.return_value = None

    # Capability checks
    container.has_youtube_credentials.return_value = False
    container.has_drive_credentials.return_value = False

    # Lifecycle
    container.close = AsyncMock()

    return container


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestContentPipeline:
    @pytest.mark.anyio()
    async def test_full_pipeline(
        self, settings: MagicMock, mock_container: MagicMock, tmp_path: Path,
    ) -> None:
        pipeline = ContentPipeline(
            settings=settings, output_dir=tmp_path,
            skip_upload=True, container=mock_container,
        )
        result = await pipeline.run(_make_request())

        assert isinstance(result, PipelineResult)
        assert result.script.video_title == "測試影片"
        assert len(result.voice.segments) == 1
        assert len(result.visual.assets) == 1
        assert result.subtitle.file_path == "/tmp/subtitles/subtitles.srt"
        assert result.thumbnail.file_path == "/tmp/thumbnails/thumbnail.jpg"
        assert result.assembly.file_path == "/tmp/assembly/final.mp4"
        assert result.upload is None  # skip_upload=True

    @pytest.mark.anyio()
    async def test_voice_visual_parallel(
        self, settings: MagicMock, mock_container: MagicMock, tmp_path: Path,
    ) -> None:
        """Verify voice and visual generators are both called."""
        pipeline = ContentPipeline(
            settings=settings, output_dir=tmp_path,
            skip_upload=True, container=mock_container,
        )
        await pipeline.run(_make_request())

        mock_container.create_voice_generator.assert_called_once()
        mock_container.create_visual_generator.assert_called_once()

    @pytest.mark.anyio()
    async def test_telegram_auto_approve(
        self, settings: MagicMock, mock_container: MagicMock, tmp_path: Path,
    ) -> None:
        """When no Telegram credentials, approval is automatic."""
        settings.telegram_bot_token.get_secret_value.return_value = ""
        settings.telegram_chat_id = ""
        pipeline = ContentPipeline(
            settings=settings, output_dir=tmp_path,
            skip_upload=True, container=mock_container,
        )
        result = await pipeline.run(_make_request())
        assert result.script.video_title == "測試影片"

    @pytest.mark.anyio()
    async def test_skip_upload_when_no_credentials(
        self, settings: MagicMock, mock_container: MagicMock, tmp_path: Path,
    ) -> None:
        mock_container.has_youtube_credentials.return_value = False
        pipeline = ContentPipeline(
            settings=settings, output_dir=tmp_path, container=mock_container,
        )
        result = await pipeline.run(_make_request())
        assert result.upload is None
        mock_container.create_upload_generator.assert_not_called()

    @pytest.mark.anyio()
    async def test_upload_when_credentials_present(
        self, settings: MagicMock, mock_container: MagicMock, tmp_path: Path,
    ) -> None:
        mock_container.has_youtube_credentials.return_value = True
        pipeline = ContentPipeline(
            settings=settings, output_dir=tmp_path, container=mock_container,
        )
        result = await pipeline.run(_make_request())
        assert result.upload is not None
        assert result.upload.video_id == "abc123"

    @pytest.mark.anyio()
    async def test_output_dir_created(
        self, settings: MagicMock, mock_container: MagicMock, tmp_path: Path,
    ) -> None:
        pipeline = ContentPipeline(
            settings=settings, output_dir=tmp_path,
            skip_upload=True, container=mock_container,
        )
        result = await pipeline.run(_make_request())
        assert Path(result.output_dir).exists()

    @pytest.mark.anyio()
    async def test_error_in_stage_propagates(
        self, settings: MagicMock, mock_container: MagicMock, tmp_path: Path,
    ) -> None:
        voice_gen = MagicMock()
        voice_gen.generate = AsyncMock(side_effect=RuntimeError("TTS failed"))
        mock_container.create_voice_generator.return_value = voice_gen

        pipeline = ContentPipeline(
            settings=settings, output_dir=tmp_path,
            skip_upload=True, container=mock_container,
        )
        with pytest.raises(RuntimeError, match="TTS failed"):
            await pipeline.run(_make_request())

    @pytest.mark.anyio()
    async def test_container_closed_on_error(
        self, settings: MagicMock, mock_container: MagicMock, tmp_path: Path,
    ) -> None:
        script_gen = MagicMock()
        script_gen.generate = AsyncMock(side_effect=RuntimeError("LLM error"))
        mock_container.create_script_generator.return_value = script_gen

        pipeline = ContentPipeline(
            settings=settings, output_dir=tmp_path,
            skip_upload=True, container=mock_container,
        )
        with pytest.raises(RuntimeError):
            await pipeline.run(_make_request())
        mock_container.close.assert_called_once()


class TestPipelineResult:
    def test_frozen(self) -> None:
        result = PipelineResult(
            script=_make_script(),
            voice=_make_voice(),
            visual=_make_visual(),
            subtitle=_make_subtitle(),
            thumbnail=_make_thumbnail(),
            assembly=_make_assembly(),
            output_dir="/tmp/output",
        )
        with pytest.raises(Exception):
            result.output_dir = "/other"  # type: ignore[misc]

    def test_upload_optional(self) -> None:
        result = PipelineResult(
            script=_make_script(),
            voice=_make_voice(),
            visual=_make_visual(),
            subtitle=_make_subtitle(),
            thumbnail=_make_thumbnail(),
            assembly=_make_assembly(),
            output_dir="/tmp/output",
        )
        assert result.upload is None