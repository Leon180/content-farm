"""Tests for the VideoAssembler."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from content_farm.assembly.assembler import (
    AssemblyStage,
    VideoAssembler,
    _find_asset,
    _find_segment,
    _safe_filename,
)
from content_farm.assembly.schemas import AssemblyInput
from content_farm.config import Settings
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.visual.schemas import VisualArtifact, VisualAsset
from content_farm.voice.schemas import AudioSegment, VoiceArtifact


def _make_assembly_input() -> AssemblyInput:
    script = Script(
        video_title="測試影片",
        description="測試用",
        language="zh-TW",
        scenes=(
            Scene(
                scene_number=1,
                title="開場",
                narration="歡迎",
                visual_hint=VisualHint(description="title"),
                duration_seconds=10,
            ),
            Scene(
                scene_number=2,
                title="主體",
                narration="內容",
                visual_hint=VisualHint(description="content"),
                duration_seconds=20,
                transition="cut",
            ),
        ),
        total_duration_seconds=30,
    )
    voice = VoiceArtifact(
        segments=(
            AudioSegment(
                scene_number=1,
                file_path="/tmp/audio/s1.mp3",
                duration_seconds=10.5,
                character_count=2,
            ),
            AudioSegment(
                scene_number=2,
                file_path="/tmp/audio/s2.mp3",
                duration_seconds=20.3,
                character_count=2,
            ),
        ),
        total_duration_seconds=30.8,
    )
    visual = VisualArtifact(
        assets=(
            VisualAsset(
                scene_number=1,
                file_path="/tmp/visual/s1.mp4",
                source="pexels",
                duration_seconds=12.0,
                query_used="title",
            ),
            VisualAsset(
                scene_number=2,
                file_path="/tmp/visual/s2.mp4",
                source="pexels",
                duration_seconds=25.0,
                query_used="content",
            ),
        ),
        total_duration_seconds=37.0,
    )
    return AssemblyInput(script=script, voice=voice, visual=visual)


@pytest.fixture
def assembler(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> tuple[VideoAssembler, AsyncMock]:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    settings = Settings()  # type: ignore[call-arg]

    mock_composer = AsyncMock()
    mock_composer.compose_scene.return_value = tmp_path / "scene.mp4"
    mock_composer.concatenate.return_value = tmp_path / "concat.mp4"
    mock_composer.final_render.return_value = tmp_path / "final.mp4"

    gen = VideoAssembler(
        composer=mock_composer,
        settings=settings,
        output_dir=tmp_path / "assembly",
    )
    return gen, mock_composer


@pytest.mark.asyncio
async def test_generate_composes_all_scenes(
    assembler: tuple[VideoAssembler, AsyncMock],
) -> None:
    gen, mock = assembler
    inp = _make_assembly_input()
    await gen.generate(inp)
    assert mock.compose_scene.call_count == 2


@pytest.mark.asyncio
async def test_generate_concatenates_scenes(
    assembler: tuple[VideoAssembler, AsyncMock],
) -> None:
    gen, mock = assembler
    inp = _make_assembly_input()
    await gen.generate(inp)
    assert mock.concatenate.call_count == 1

    call_kwargs = mock.concatenate.call_args.kwargs
    assert len(call_kwargs["scene_paths"]) == 2


@pytest.mark.asyncio
async def test_generate_calls_final_render(
    assembler: tuple[VideoAssembler, AsyncMock],
) -> None:
    gen, mock = assembler
    inp = _make_assembly_input()
    await gen.generate(inp)
    assert mock.final_render.call_count == 1


@pytest.mark.asyncio
async def test_generate_returns_artifact(
    assembler: tuple[VideoAssembler, AsyncMock],
) -> None:
    gen, _ = assembler
    inp = _make_assembly_input()
    artifact = await gen.generate(inp)

    assert artifact.stage == "video_assembly"
    assert len(artifact.scenes) == 2
    assert artifact.total_duration_seconds > 0


@pytest.mark.asyncio
async def test_generate_with_background_music(
    assembler: tuple[VideoAssembler, AsyncMock],
) -> None:
    gen, mock = assembler
    inp = AssemblyInput(
        script=_make_assembly_input().script,
        voice=_make_assembly_input().voice,
        visual=_make_assembly_input().visual,
        background_music_path="/tmp/music.mp3",
    )
    await gen.generate(inp)

    render_kwargs = mock.final_render.call_args.kwargs
    assert render_kwargs["background_music_path"] is not None


class TestAssemblyStage:
    @pytest.mark.asyncio
    async def test_validate_empty_segments_raises(self) -> None:
        stage = AssemblyStage(assembler=AsyncMock())  # type: ignore[arg-type]
        inp = AssemblyInput(
            script=_make_assembly_input().script,
            voice=VoiceArtifact(),
            visual=_make_assembly_input().visual,
        )
        with pytest.raises(ValueError, match="no segments"):
            await stage.validate_input(inp)

    @pytest.mark.asyncio
    async def test_validate_scene_mismatch_raises(self) -> None:
        stage = AssemblyStage(assembler=AsyncMock())  # type: ignore[arg-type]
        # Voice has scene 1 only, script has scenes 1 and 2
        inp = AssemblyInput(
            script=_make_assembly_input().script,
            voice=VoiceArtifact(
                segments=(
                    AudioSegment(
                        scene_number=1,
                        file_path="/tmp/s1.mp3",
                        duration_seconds=10.0,
                        character_count=2,
                    ),
                ),
            ),
            visual=_make_assembly_input().visual,
        )
        with pytest.raises(ValueError, match="scene mismatch"):
            await stage.validate_input(inp)


class TestHelpers:
    def test_find_segment_found(self) -> None:
        inp = _make_assembly_input()
        seg = _find_segment(inp, 1)
        assert seg.scene_number == 1

    def test_find_segment_missing(self) -> None:
        inp = _make_assembly_input()
        with pytest.raises(ValueError, match="No audio segment for scene 99"):
            _find_segment(inp, 99)

    def test_find_asset_found(self) -> None:
        inp = _make_assembly_input()
        asset = _find_asset(inp, 2)
        assert asset.scene_number == 2

    def test_find_asset_missing(self) -> None:
        inp = _make_assembly_input()
        with pytest.raises(ValueError, match="No visual asset for scene 99"):
            _find_asset(inp, 99)

    def test_safe_filename_cjk(self) -> None:
        assert _safe_filename("測試影片") == "測試影片"

    def test_safe_filename_special_chars(self) -> None:
        result = _safe_filename("Hello! @World#")
        assert "@" not in result
        assert "#" not in result
        assert "!" not in result

    def test_safe_filename_long(self) -> None:
        result = _safe_filename("a" * 200)
        assert len(result) <= 100

    def test_safe_filename_empty(self) -> None:
        assert _safe_filename("") == "untitled"
