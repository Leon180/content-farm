"""Run-directory orchestration: draft.mp4 + cues + audio → final.mp4."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from content_farm.explainer.mascot import lipsync
from content_farm.explainer.mascot.cues import SceneCue, cues_from_run
from content_farm.explainer.mascot.motion import Frame, compose_frames
from content_farm.explainer.mascot.overlay import FRAME_H, FRAME_W, overlay
from content_farm.explainer.mascot.render import RenderStats, render_alpha_video

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VideoInfo:
    fps: float
    frames: int
    width: int
    height: int


@dataclass(frozen=True)
class OverlayResult:
    final: Path
    alpha_video: Path
    info: VideoInfo
    rendered_frames: int
    timings: dict[str, float]
    render: RenderStats


def probe_video(path: Path) -> VideoInfo:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    fps = float(Fraction(stream["r_frame_rate"]))
    frames = int(stream.get("nb_frames") or 0) or round(float(data["format"]["duration"]) * fps)
    return VideoInfo(fps=fps, frames=frames, width=int(stream["width"]), height=int(stream["height"]))


def mouth_for_run(run_dir: Path, cues: tuple[SceneCue, ...], fps: float, n_frames: int) -> np.ndarray:
    """Per-scene audio placed at slide starts; else full.mp3; else a closed mouth."""
    audio = run_dir / "audio"
    scene_files = [audio / f"scene_{c.index:03d}.mp3" for c in cues]
    if all(p.is_file() for p in scene_files):
        return lipsync.envelope_for_scenes(
            [(p, c.start) for p, c in zip(scene_files, cues)], fps, n_frames)
    if (audio / "full.mp3").is_file():
        return lipsync.envelope_for_track(audio / "full.mp3", fps, n_frames)
    logger.warning("no voice audio in %s; mouth stays closed", audio)
    return np.zeros(n_frames)


def frames_for_run(run_dir: Path, info: VideoInfo, seed: int, limit: int | None = None) -> tuple[Frame, ...]:
    cues = cues_from_run(run_dir)
    mouth = mouth_for_run(run_dir, cues, info.fps, info.frames)
    frames = compose_frames(cues, mouth, info.fps, info.frames, seed=seed)
    return frames[:limit] if limit else frames


def run_overlay(
    run_dir: Path, *, workers: int = 4, seed: int = 7, seconds: float | None = None,
    out: Path | None = None,
) -> OverlayResult:
    """Render the cat for ``assembly/draft.mp4`` and write ``assembly/final.mp4``."""
    draft = run_dir / "assembly" / "draft.mp4"
    if not draft.is_file():
        raise FileNotFoundError(f"missing {draft}")
    info = probe_video(draft)
    if (info.width, info.height) != (FRAME_W, FRAME_H):
        raise ValueError(f"draft is {info.width}x{info.height}; overlay layout expects 1920x1080")
    timings: dict[str, float] = {}
    t0 = time.monotonic()
    limit = int(round(seconds * info.fps)) if seconds else None
    frames = frames_for_run(run_dir, info, seed, limit)
    timings["params"] = time.monotonic() - t0

    alpha = run_dir / "assembly" / "mascot.mov"
    stats = render_alpha_video(frames, info.fps, alpha, workers=workers)
    timings["render"] = stats.seconds

    final = out or run_dir / "assembly" / "final.mp4"
    t1 = time.monotonic()
    overlay(draft, alpha, final, duration=seconds)
    timings["overlay"] = time.monotonic() - t1
    timings["total"] = time.monotonic() - t0
    return OverlayResult(final, alpha, info, len(frames), timings, stats)
