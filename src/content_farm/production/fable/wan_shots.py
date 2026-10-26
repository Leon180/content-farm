"""Wan clips for the few fable shots marked ``wan`` (Leon 2026-10-25: ~4 per video, 2 chained segments, faceless scenes).

``fable_images`` has already drawn every picture; this step turns each ``wan`` shot's picture into a Wan2.2 clip
(portrait 480×832 for a Short, landscape 832×480 for the mid-length video; ``wan.generate`` caches every segment, so an
interrupted bake resumes). It runs inside the machine-wide heavy queue (one exclusive-GPU ticket), so the gate here
does not wait again. ``assets/fable/wan.json`` maps the picture id to the joined clip; the render prefers it over
the parallax clip.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path

from content_farm.explainer import wan
from content_farm.explainer.ai_images import AI_IMAGE_DIR, find_image
from content_farm.explainer.illustrate import load_record
from content_farm.explainer.motion_cache import MotionPaths, motion_env
from content_farm.production.fable.model import Fable

MANIFEST = Path("assets") / "fable" / "wan.json"
WAN_SIZE = {"short": (480, 832), "mid": (832, 480)}      # multiples of 32, same aspect as the frame


def wan_shots(fable: Fable) -> list[tuple[str, object]]:
    """``(image id, WanSpec)`` of every drawn shot that asks for Wan."""
    return [(f"{b.id}_{n}", s.wan) for b in fable.beats for n, s in enumerate(b.shots, 1) if s.wan and s.image_prompt.strip()]


def has_wan(run_dir: Path) -> bool:
    try:
        data = json.loads((run_dir / "fable.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any(isinstance(s, dict) and s.get("wan") for b in data.get("beats", []) for s in b.get("shots", []))


def requests_for(run_dir: Path, fable: Fable, policy=None) -> list[wan.WanRequest]:
    width, height = WAN_SIZE[fable.format]
    out = []
    for image_id, spec in wan_shots(fable):
        image = find_image(run_dir / AI_IMAGE_DIR, image_id)
        if image is None:
            raise FileNotFoundError(f"picture {image_id} was not drawn (run fable_images first)")
        request = wan.request_for(image_id, image, load_record(image), spec.motion, "", policy, chain=tuple(spec.chain))
        out.append(dataclasses.replace(request, params=dataclasses.replace(request.params, width=width, height=height)))
    return out


def bake(run_dir: Path, fable: Fable, env_file: Path | None, generate: Callable = wan.generate,
         log: Callable[[str], None] = print) -> dict[str, dict]:
    """Make every missing Wan clip, one at a time; returns ``{image_id: {"clip", "fps", "segments", "credit"}}``."""
    requests = requests_for(run_dir, fable, wan.policy_for(run_dir))
    paths = MotionPaths.from_env(motion_env(env_file)) if requests else None
    if requests and paths is None:
        raise RuntimeError("Wan tools not configured (CF_MLX_VIDEO_HOME): refusing to ship a parallax clip as Wan")
    out: dict[str, dict] = {}
    for request in requests:
        found = wan.cached(run_dir, request)
        if found is None:
            log(f"- {request.slide_id}: generating {request.segments} segment(s) (~{wan.ESTIMATED_MINUTES_PER_CLIP * request.segments} min)")
            generate(paths, run_dir, request, lambda: 0.0)
            found = wan.cached(run_dir, request)
        if found is None:
            raise RuntimeError(f"{request.slide_id}: Wan finished but no clip is cached")
        clip, record = found
        out[request.slide_id] = {"clip": clip.relative_to(run_dir).as_posix(), "fps": request.params.fps,
                                 "segments": request.segments, "credit": wan.credit(record)}
    return out


def write_manifest(run_dir: Path, clips: dict[str, dict]) -> Path:
    path = run_dir / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "clips": clips}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_manifest(run_dir: Path) -> dict[str, dict]:
    """``{image_id: entry}``; empty when the video has no Wan shots (or the step has not run)."""
    path = run_dir / MANIFEST
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("clips", {})


