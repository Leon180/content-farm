"""Run-directory orchestration: draft.mp4 + cues + audio → final.mp4.

The cat is drawn one scene (slide) at a time and each scene's alpha clip is cached under
``assembly/mascot_cache/<identity>/`` (see ``mascot.scenes``): a re-run only draws the
scenes whose pose, bubble, audio or length changed, then joins all scene clips into
``assembly/mascot.mov`` (stream copy) and overlays it on the draft.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from content_farm.explainer.mascot import lipsync
from content_farm.explainer.mascot.cues import SceneCue, cues_from_run
from content_farm.explainer.mascot.motion import Frame, SceneSpan
from content_farm.explainer.mascot.overlay import FRAME_H, FRAME_W, overlay
from content_farm.explainer.mascot.render import RenderStats, _concat, render_scene_parts, render_settings
from content_farm.explainer.mascot.scenes import renderer_digest, scene_frames, scene_identity, spans
from content_farm.explainer.scene_cache import SceneCache

logger = logging.getLogger(__name__)

CACHE_DIR = "mascot_cache"
GENERATIONS = 3


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
    rendered_frames: int          # frames in the output
    timings: dict[str, float]
    render: RenderStats           # what was actually drawn this run
    scenes: int = 0
    reused_scenes: int = 0


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
    """Whole-video envelope (PNGtuber hosts): per-scene audio at slide starts; else full.mp3."""
    audio = run_dir / "audio"
    scene_files = [audio / f"scene_{c.index:03d}.mp3" for c in cues]
    if all(p.is_file() for p in scene_files):
        return lipsync.envelope_for_scenes(
            [(p, c.start) for p, c in zip(scene_files, cues)], fps, n_frames)
    if (audio / "full.mp3").is_file():
        return lipsync.envelope_for_track(audio / "full.mp3", fps, n_frames)
    logger.warning("no voice audio in %s; mouth stays closed", audio)
    return np.zeros(n_frames)


def _slide_keys(run_dir: Path, count: int) -> list[str]:
    """Stable per-scene seed keys: deck slide ids when there is a deck, else scene numbers."""
    deck = run_dir / "deck.json"
    if deck.is_file():
        data = json.loads(deck.read_text(encoding="utf-8"))
        ids = [s["id"] for section in data.get("sections", []) for s in section.get("slides", [])]
        if len(ids) == count:
            return ids
    return [str(i) for i in range(1, count + 1)]


def scene_plan(run_dir: Path, info: VideoInfo, seed: int) -> list[tuple[SceneSpan, Path | None]]:
    cues = cues_from_run(run_dir)
    plan = spans(cues, info.fps, info.frames, seed, _slide_keys(run_dir, len(cues)))
    audio = run_dir / "audio"
    # A scene shorter than half a frame owns no frame: nothing to draw for it.
    return [(span, audio / f"scene_{span.cue.index:03d}.mp3") for span in plan if span.used > 0]


def frames_for_run(run_dir: Path, info: VideoInfo, seed: int, limit: int | None = None) -> tuple[Frame, ...]:
    """Every frame of the video (stills, parameter dumps); the same frames the overlay draws."""
    frames: list[Frame] = []
    for span, audio in scene_plan(run_dir, info, seed):
        if limit is not None and span.first >= limit:
            break
        frames.extend(scene_frames(span, audio, info.fps)[:span.used])
    return tuple(frames[:limit] if limit else frames)


def _remember(cache: SceneCache, keys: list[str]) -> None:
    log = cache.root / "generations.json"
    try:
        history = json.loads(log.read_text(encoding="utf-8")) if log.is_file() else []
    except json.JSONDecodeError:
        history = []
    history = [*history, sorted(set(keys))][-GENERATIONS:]
    log.write_text(json.dumps(history), encoding="utf-8")
    cache.prune({k for generation in history for k in generation})


def render_scenes(run_dir: Path, info: VideoInfo, *, seed: int, workers: int,
                  use_cache: bool = True) -> tuple[list[tuple[Path, int]], RenderStats, int]:
    """Alpha clip per scene (cached by identity); returns ((clip, frames used) in order, stats, reused)."""
    plan = scene_plan(run_dir, info, seed)
    cache = SceneCache(run_dir / "assembly" / CACHE_DIR)
    code, settings = renderer_digest(), render_settings()
    keys = [scene_identity(span, audio, info.fps, render=settings, code=code) for span, audio in plan]
    missing = [i for i, key in enumerate(keys) if not use_cache or cache.get(key) is None]
    incoming = cache.root / ".incoming"
    jobs = [(scene_frames(plan[i][0], plan[i][1], info.fps), incoming / f"{keys[i]}.mov") for i in missing]
    stats = render_scene_parts(jobs, info.fps, workers=workers)
    for i, (_frames, part) in zip(missing, jobs):
        span = plan[i][0]
        cache.put(keys[i], {"alpha.mov": part}, {"identity": keys[i], "scene": span.cue.index,
                                                 "frames": span.count, "pose": span.cue.pose}, move=True)
    _remember(cache, keys)
    clips = [(cache.path(key, "alpha.mov"), span.used) for key, (span, _audio) in zip(keys, plan)]
    return clips, stats, len(plan) - len(missing)


def _preview_alpha(run_dir: Path, info: VideoInfo, seed: int, workers: int, limit: int, out: Path) -> RenderStats:
    """First ``limit`` frames, uncached (``--seconds`` previews)."""
    frames = frames_for_run(run_dir, info, seed, limit)
    with tempfile.TemporaryDirectory(prefix="mascot_preview_", dir=out.parent) as tmp:
        part = Path(tmp) / "preview.mov"
        stats = render_scene_parts([(frames, part)], info.fps, workers=workers)
        _concat([part], out)
    return stats


def run_overlay(
    run_dir: Path, *, workers: int = 3, seed: int = 7, seconds: float | None = None,
    out: Path | None = None, use_cache: bool = True,
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
    alpha = run_dir / "assembly" / "mascot.mov"
    if seconds:
        limit = int(round(seconds * info.fps))
        stats, scenes, reused = _preview_alpha(run_dir, info, seed, workers, limit, alpha), 0, 0
        total = limit
    else:
        clips, stats, reused = render_scenes(run_dir, info, seed=seed, workers=workers, use_cache=use_cache)
        t_join = time.monotonic()
        _concat_copy(clips, alpha, info.fps)
        timings["join"] = time.monotonic() - t_join
        scenes, total = len(clips), info.frames
    timings["render"] = stats.seconds
    final = out or run_dir / "assembly" / "final.mp4"
    t1 = time.monotonic()
    overlay(draft, alpha, final, duration=seconds)
    timings["overlay"] = time.monotonic() - t1
    timings["total"] = time.monotonic() - t0
    timings["params"] = timings["total"] - timings["render"] - timings["overlay"] - timings.get("join", 0.0)
    return OverlayResult(final, alpha, info, total, timings, stats, scenes, reused)


def _concat_copy(clips: list[tuple[Path, int]], out: Path, fps: float) -> None:
    """Join scene clips without re-encoding (all ProRes 4444, intra-only), each cut to the frames
    its slot uses (a scene renders one spare frame; see scenes.render_count)."""
    listing = out.parent / f".{out.stem}_scenes.txt"
    listing.write_text("".join(f"file '{p.resolve()}'\noutpoint {(used - 0.5) / fps:.6f}\n"
                               for p, used in clips), encoding="utf-8")
    try:
        result = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                                 "-c", "copy", str(out)], capture_output=True, text=True, timeout=900)
    finally:
        listing.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"joining mascot scenes failed: {result.stderr[-400:]}")
