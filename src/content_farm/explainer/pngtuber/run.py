"""Run-directory orchestration for a PNGtuber host: draft.mp4 + cues + voice → final.mp4.

Same inputs as the rig (explainer.mascot.run): deck.json / script.json mascot poses, slide timing,
per-scene or full voice audio. Landscape drafts get the bottom-right placement, 9:16 drafts the
bottom-left Shorts placement (pngtuber.render).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from content_farm.explainer.mascot.cues import SceneCue, cues_from_run
from content_farm.explainer.mascot.overlay import overlay
from content_farm.explainer.mascot.run import VideoInfo, mouth_for_run, probe_video
from content_farm.explainer.pngtuber.motion import HostFrame, host_frames
from content_farm.explainer.pngtuber.pack import load_pack
from content_farm.explainer.pngtuber.render import PLACEMENTS, Composer, Placement, RenderStats, render_alpha_video


@dataclass(frozen=True)
class HostResult:
    final: Path
    alpha_video: Path
    info: VideoInfo
    placement: str
    render: RenderStats
    timings: dict[str, float]


def placement_for(info: VideoInfo) -> Placement:
    try:
        return PLACEMENTS[(info.width, info.height)]
    except KeyError:
        raise ValueError(f"draft is {info.width}x{info.height}; PNGtuber placements exist for "
                         f"{', '.join(f'{w}x{h}' for w, h in PLACEMENTS)}") from None


def frames_for_run(run_dir: Path, info: VideoInfo, pack_ref: str, seed: int,
                   limit: int | None = None, cues: tuple[SceneCue, ...] | None = None) -> tuple[HostFrame, ...]:
    cues = cues if cues is not None else cues_from_run(run_dir)
    envelope = mouth_for_run(run_dir, cues, info.fps, info.frames)
    frames = host_frames(cues, np.asarray(envelope), info.fps, info.frames, load_pack(pack_ref), seed=seed)
    return frames[:limit] if limit else frames


def run_host_overlay(run_dir: Path, pack_ref: str, *, seed: int = 7, seconds: float | None = None,
                     out: Path | None = None, cues: tuple[SceneCue, ...] | None = None) -> HostResult:
    """Render the PNGtuber for ``assembly/draft.mp4`` and write ``assembly/final.mp4``.
    ``cues`` overrides the deck/script cues (scripted Shorts pass their beat poses)."""
    draft = run_dir / "assembly" / "draft.mp4"
    if not draft.is_file():
        raise FileNotFoundError(f"missing {draft}")
    info = probe_video(draft)
    placement = placement_for(info)
    timings: dict[str, float] = {}
    t0 = time.monotonic()
    limit = int(round(seconds * info.fps)) if seconds else None
    frames = frames_for_run(run_dir, info, pack_ref, seed, limit, cues)
    timings["params"] = time.monotonic() - t0
    alpha = run_dir / "assembly" / "host.mov"
    stats = render_alpha_video(Composer(load_pack(pack_ref), placement), frames, info.fps, alpha)
    timings["render"] = stats.seconds
    final = out or run_dir / "assembly" / "final.mp4"
    t1 = time.monotonic()
    overlay(draft, alpha, final, duration=seconds, origin=placement.origin)
    timings["overlay"] = time.monotonic() - t1
    timings["total"] = time.monotonic() - t0
    return HostResult(final, alpha, info, placement.name, stats, timings)


def still(pack_ref: str, frame: HostFrame, placement: Placement, out: Path) -> Path:
    """One posed canvas as a transparent PNG (thumbnails, reviews)."""
    img: Image.Image = Composer(load_pack(pack_ref), placement).canvas(frame)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out
