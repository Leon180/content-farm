"""Concatenation utilities for visual clips."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from pathlib import Path

from content_farm.visual.schemas import (
    ClipInfo,
    ClipsManifest,
    VisualArtifact,
    VisualAsset,
)

logger = logging.getLogger(__name__)


async def concat_selected_clips(
    manifest_path: Path,
    output_dir: Path,
    ffmpeg_path: str = "ffmpeg",
) -> VisualArtifact:
    """Read manifest, concat selected clips per scene into scene_XXX.mp4."""
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = ClipsManifest.model_validate(raw)

    by_scene: dict[int, list[ClipInfo]] = defaultdict(list)
    for clip in manifest.clips:
        if clip.selected:
            by_scene[clip.scene_number].append(clip)

    all_scenes = sorted({c.scene_number for c in manifest.clips})
    assets: list[VisualAsset] = []

    for sn in all_scenes:
        selected = sorted(by_scene.get(sn, []), key=lambda c: c.clip_index)
        output_path = output_dir / f"scene_{sn:03d}.mp4"

        if not selected:
            logger.warning("No clips selected for scene %d", sn)
            assets.append(VisualAsset(
                scene_number=sn,
                file_path="",
                source="none",
                duration_seconds=0.0,
                query_used="",
            ))
            continue

        clip_paths = [output_dir / c.file_name for c in selected]
        missing = [p for p in clip_paths if not p.exists()]
        if missing:
            raise FileNotFoundError(
                f"Scene {sn}: clip files missing: {[str(m) for m in missing]}"
            )

        if len(clip_paths) == 1:
            # Single clip — copy (not rename, keep original)
            import shutil
            shutil.copy2(clip_paths[0], output_path)
        else:
            await concat_clips(clip_paths, output_path, ffmpeg_path)

        total_dur = sum(c.duration_seconds for c in selected)
        assets.append(VisualAsset(
            scene_number=sn,
            file_path=str(output_path),
            source="stock_multi",
            duration_seconds=total_dur,
            query_used=", ".join(c.keyword for c in selected),
        ))

    return VisualArtifact(
        assets=tuple(assets),
        total_duration_seconds=sum(a.duration_seconds for a in assets),
        output_dir=str(output_dir),
    )


async def concat_clips(
    clip_paths: list[Path],
    output_path: Path,
    ffmpeg_path: str = "ffmpeg",
) -> None:
    """Concatenate multiple video clips using the concat filter (re-encode).

    Re-encoding is necessary because clips from different stock providers
    may have different codecs, resolutions, and frame rates.
    """
    n = len(clip_paths)
    inputs: list[str] = []
    for cp in clip_paths:
        inputs.extend(["-i", str(cp.resolve())])

    filter_parts = []
    for i in range(n):
        filter_parts.append(
            f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1[v{i}]"
        )
    stream_labels = "".join(f"[v{i}]" for i in range(n))
    filter_parts.append(f"{stream_labels}concat=n={n}:v=1:a=0[outv]")
    filter_graph = ";".join(filter_parts)

    cmd = [
        ffmpeg_path, "-y",
        *inputs,
        "-filter_complex", filter_graph,
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-movflags", "+faststart",
        str(output_path),
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        detail = stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"FFmpeg concat failed: {detail}")
