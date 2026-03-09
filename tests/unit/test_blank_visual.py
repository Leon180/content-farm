from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.visual.blank import generate_blank_visuals


def _make_script(scene_count: int = 2, duration: int = 10) -> Script:
    scenes = tuple(
        Scene(
            scene_number=i + 1,
            title=f"S{i + 1}",
            narration="N",
            visual_hint=VisualHint(description="x"),
            duration_seconds=duration,
        )
        for i in range(scene_count)
    )
    return Script(video_title="T", description="D", language="zh-TW", scenes=scenes)


@pytest.mark.anyio()
async def test_generates_assets_per_scene(tmp_path):
    script = _make_script(scene_count=2, duration=10)
    with patch("content_farm.visual.blank._create_black_clip", new_callable=AsyncMock):
        artifact = await generate_blank_visuals(script, tmp_path)
    assert len(artifact.assets) == 2
    for asset, scene in zip(artifact.assets, script.scenes):
        assert asset.scene_number == scene.scene_number
        assert asset.source == "blank"
        assert asset.duration_seconds == float(scene.duration_seconds)


@pytest.mark.anyio()
async def test_creates_output_dir(tmp_path):
    output_dir = tmp_path / "deep" / "nested" / "dir"
    script = _make_script(scene_count=1)
    with patch("content_farm.visual.blank._create_black_clip", new_callable=AsyncMock):
        await generate_blank_visuals(script, output_dir)
    assert output_dir.is_dir()


@pytest.mark.anyio()
async def test_total_duration_summed(tmp_path):
    scenes = (
        Scene(scene_number=1, title="S1", narration="N",
              visual_hint=VisualHint(description="x"), duration_seconds=10),
        Scene(scene_number=2, title="S2", narration="N",
              visual_hint=VisualHint(description="x"), duration_seconds=15),
    )
    script = Script(video_title="T", description="D", language="zh-TW", scenes=scenes)
    with patch("content_farm.visual.blank._create_black_clip", new_callable=AsyncMock):
        artifact = await generate_blank_visuals(script, tmp_path)
    assert artifact.total_duration_seconds == 25.0


@pytest.mark.anyio()
async def test_reuses_existing_file(tmp_path):
    script = _make_script(scene_count=2, duration=10)
    existing = tmp_path / "scene_001.mp4"
    existing.write_bytes(b"\x00" * 16)
    with patch(
        "content_farm.visual.blank._create_black_clip", new_callable=AsyncMock
    ) as mock_create:
        await generate_blank_visuals(script, tmp_path)
    called_paths = [call.args[0] for call in mock_create.call_args_list]
    assert existing not in called_paths
    assert any(p.name == "scene_002.mp4" for p in called_paths)


@pytest.mark.anyio()
async def test_ffmpeg_failure_raises(tmp_path):
    script = _make_script(scene_count=1, duration=5)
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"ffmpeg error output"))
    with patch(
        "asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc
    ):
        with pytest.raises(RuntimeError, match="ffmpeg failed creating blank clip"):
            await generate_blank_visuals(script, tmp_path)


@pytest.mark.anyio()
async def test_asset_file_paths(tmp_path):
    script = _make_script(scene_count=2, duration=10)
    with patch("content_farm.visual.blank._create_black_clip", new_callable=AsyncMock):
        artifact = await generate_blank_visuals(script, tmp_path)
    names = [Path(a.file_path).name for a in artifact.assets]
    assert names == ["scene_001.mp4", "scene_002.mp4"]


@pytest.mark.anyio()
async def test_source_is_blank(tmp_path):
    script = _make_script(scene_count=3, duration=8)
    with patch("content_farm.visual.blank._create_black_clip", new_callable=AsyncMock):
        artifact = await generate_blank_visuals(script, tmp_path)
    assert all(a.source == "blank" for a in artifact.assets)
