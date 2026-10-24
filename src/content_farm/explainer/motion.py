"""Pick the motion clip for one ``ai_image`` slide (decision 2bacb8a2b8b0).

``media.motion`` (default ``parallax``):
- ``wan``: the baked Wan clip from the cache, else parallax (never generated during a render);
- ``parallax``: cached or built now (~3–5 s), else Ken Burns;
- ``ken_burns``: the flat push-in, no clip.

The returned :class:`MotionPlan` says which clip to loop over the slot (None = Ken Burns), why
a fallback happened, and the ``motion`` block that goes into the slide's credit entry. The
「AI 示意圖」 badge is on the slide overlay, so it stays on every variant.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from content_farm.explainer import parallax, wan
from content_farm.explainer.deck import Motion, Slide
from content_farm.explainer.motion_cache import MotionPaths

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MotionPlan:
    used: Motion
    clip: Path | None = None          # None = Ken Burns on the still
    retime_fps: int | None = None     # Wan clips are 24 fps
    note: str = ""
    credit: dict = field(default_factory=dict)
    problems: tuple[str, ...] = ()


def plan_motion(paths: MotionPaths | None, run_dir: Path, slide: Slide, slide_index: int, image: Path,
                image_record: dict | None) -> MotionPlan:
    requested = slide.media.motion_kind if slide.media else Motion.PARALLAX
    reasons: list[str] = []
    if requested == Motion.KEN_BURNS:
        return _ken_burns(requested, reasons)
    if requested == Motion.WAN:
        found = _baked_wan(run_dir, slide, image, image_record, reasons)
        if found is not None:
            return found
    if paths is None:
        reasons.append("motion tools not configured (CF_MLX_VIDEO_HOME)")
        return _ken_burns(requested, reasons)
    missing = paths.problems()
    if missing:
        reasons.extend(missing)
        return _ken_burns(requested, reasons)
    try:
        clip, record = parallax.ensure_clip(paths, run_dir, slide.id, image, parallax.params_for(slide_index))
    except (RuntimeError, ValueError, OSError) as exc:
        reasons.append(f"parallax failed: {exc}")
        return _ken_burns(requested, reasons)
    stats = record.get("stats", {})
    cache = "cache" if record.get("from_cache") else f"built {stats.get('build_seconds', '?')}s"
    note = (f"parallax {stats.get('seconds', '?')}s ping-pong ({cache}, strength "
            f"{stats.get('depth_strength', '?')}, thin {stats.get('thin_share', '?')})")
    return MotionPlan(Motion.PARALLAX, clip, note=_with_fallback(requested, Motion.PARALLAX, reasons, note),
                      credit={**parallax.credit(record), **_requested(requested, reasons)},
                      problems=tuple(reasons))


def _baked_wan(run_dir: Path, slide: Slide, image: Path, image_record: dict | None,
               reasons: list[str]) -> MotionPlan | None:
    media = slide.media
    try:
        request = wan.request_for(slide.id, image, image_record, media.motion_prompt if media else "",
                                  media.prompt if media else "", wan.policy_for(run_dir))
        found = wan.cached(run_dir, request)
    except (ValueError, OSError) as exc:
        reasons.append(f"wan: {exc}")
        return None
    if found is None:
        reasons.append("wan clip not baked yet (run scripts/ai_motion.py bake)")
        return None
    clip, record = found
    return MotionPlan(Motion.WAN, clip, retime_fps=request.params.fps,
                      note=f"wan {request.params.num_frames}f@{request.params.fps} ping-pong (baked)",
                      credit=wan.credit(record))


def _ken_burns(requested: Motion, reasons: list[str]) -> MotionPlan:
    note = _with_fallback(requested, Motion.KEN_BURNS, reasons, "ken burns")
    if reasons:
        logger.warning("%s", note)
    return MotionPlan(Motion.KEN_BURNS, None, note=note,
                      credit={"kind": Motion.KEN_BURNS.value, **_requested(requested, reasons)},
                      problems=tuple(reasons))


def _requested(requested: Motion, reasons: list[str]) -> dict:
    return {"requested": requested.value, "fallback_reason": "; ".join(reasons)} if reasons else {}


def _with_fallback(requested: Motion, used: Motion, reasons: list[str], note: str) -> str:
    if requested == used or not reasons:
        return note
    return f"FALLBACK {requested.value}→{used.value}: {'; '.join(reasons)} | {note}"
