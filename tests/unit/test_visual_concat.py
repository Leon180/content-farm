"""Tests for visual clip concatenation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from content_farm.visual.concat import concat_selected_clips
from content_farm.visual.schemas import ClipInfo, ClipsManifest


def _write_manifest(output_dir: Path, clips: list[ClipInfo]) -> Path:
    manifest = ClipsManifest(clips=clips, output_dir=str(output_dir))
    manifest_path = output_dir / "clips_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest_path


def _make_clip(
    scene: int,
    index: int,
    *,
    selected: bool = False,
    keyword: str = "test",
) -> ClipInfo:
    return ClipInfo(
        scene_number=scene,
        clip_index=index,
        file_name=f"scene_{scene:03d}_{index:02d}.mp4",
        keyword=keyword,
        provider_id=f"pexels:{scene * 100 + index}",
        duration_seconds=5.0,
        width=1920,
        height=1080,
        selected=selected,
    )


def _create_fake_clip(output_dir: Path, clip: ClipInfo) -> None:
    path = output_dir / clip.file_name
    path.write_bytes(b"fake-video-data")


@pytest.mark.asyncio
@patch("content_farm.visual.concat.concat_clips", new_callable=AsyncMock)
async def test_concat_selected_clips_merges_selected(
    mock_concat: AsyncMock,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "visual"
    output_dir.mkdir()

    clips = [
        _make_clip(1, 1, selected=True, keyword="otter"),
        _make_clip(1, 2, selected=False, keyword="otter"),
        _make_clip(1, 3, selected=True, keyword="ocean"),
    ]
    for c in clips:
        _create_fake_clip(output_dir, c)
    manifest_path = _write_manifest(output_dir, clips)

    artifact = await concat_selected_clips(manifest_path, output_dir)

    assert len(artifact.assets) == 1
    assert artifact.assets[0].scene_number == 1
    assert artifact.assets[0].source == "stock_multi"
    # Should have called concat with 2 selected clips
    mock_concat.assert_called_once()
    call_paths = mock_concat.call_args[0][0]
    assert len(call_paths) == 2


@pytest.mark.asyncio
async def test_concat_no_selected_returns_none_source(tmp_path: Path) -> None:
    output_dir = tmp_path / "visual"
    output_dir.mkdir()

    clips = [
        _make_clip(1, 1, selected=False),
        _make_clip(1, 2, selected=False),
    ]
    for c in clips:
        _create_fake_clip(output_dir, c)
    manifest_path = _write_manifest(output_dir, clips)

    artifact = await concat_selected_clips(manifest_path, output_dir)

    assert len(artifact.assets) == 1
    assert artifact.assets[0].source == "none"
    assert artifact.assets[0].file_path == ""


@pytest.mark.asyncio
async def test_concat_single_clip_copies(tmp_path: Path) -> None:
    output_dir = tmp_path / "visual"
    output_dir.mkdir()

    clips = [_make_clip(1, 1, selected=True)]
    _create_fake_clip(output_dir, clips[0])
    manifest_path = _write_manifest(output_dir, clips)

    artifact = await concat_selected_clips(manifest_path, output_dir)

    assert artifact.assets[0].source == "stock_multi"
    output_file = output_dir / "scene_001.mp4"
    assert output_file.exists()


@pytest.mark.asyncio
@patch("content_farm.visual.concat.concat_clips", new_callable=AsyncMock)
async def test_concat_multiple_scenes(
    mock_concat: AsyncMock,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "visual"
    output_dir.mkdir()

    clips = [
        _make_clip(1, 1, selected=True),
        _make_clip(1, 2, selected=True),
        _make_clip(2, 1, selected=True),
        _make_clip(2, 2, selected=False),
    ]
    for c in clips:
        _create_fake_clip(output_dir, c)
    manifest_path = _write_manifest(output_dir, clips)

    artifact = await concat_selected_clips(manifest_path, output_dir)

    assert len(artifact.assets) == 2
    scene_nums = [a.scene_number for a in artifact.assets]
    assert scene_nums == [1, 2]


@pytest.mark.asyncio
async def test_concat_missing_clip_file_raises(tmp_path: Path) -> None:
    output_dir = tmp_path / "visual"
    output_dir.mkdir()

    clips = [_make_clip(1, 1, selected=True)]
    # Don't create the file on disk
    manifest_path = _write_manifest(output_dir, clips)

    with pytest.raises(FileNotFoundError, match="clip files missing"):
        await concat_selected_clips(manifest_path, output_dir)
