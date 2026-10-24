"""Bake the Wan key-shot clips of one or more run dirs ahead of rendering (the nightly batch).

For every ``ai_image`` slide with ``motion: wan`` whose still exists: skip it when the cache
already holds a clip for the same image + prompt + parameters, else generate it — one clip at a
time, each after ``gate`` says the machine is free. More than :data:`wan.MAX_WAN_PER_VIDEO`
in a deck is refused before anything loads.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from content_farm.explainer import shot_language, wan
from content_farm.explainer.ai_images import AI_IMAGE_DIR, find_image
from content_farm.explainer.deck import Deck, MediaKind, Motion
from content_farm.explainer.illustrate import load_record
from content_farm.explainer.motion_cache import MotionPaths


@dataclass(frozen=True)
class WanShot:
    run_dir: Path
    slide_id: str
    request: wan.WanRequest | None   # None: the still is not there yet
    cached: bool


def wan_shots(deck: Deck, run_dir: Path) -> list[WanShot]:
    slides = [slide for slide in deck.slides if slide.media_kind == MediaKind.AI_IMAGE
              and slide.media is not None and slide.media.motion_kind == Motion.WAN]
    if len(slides) > wan.MAX_WAN_PER_VIDEO:
        raise ValueError(f"{run_dir.name}: {len(slides)} slides ask for motion: wan "
                         f"(max {wan.MAX_WAN_PER_VIDEO}): {', '.join(s.id for s in slides)}")
    shots = []
    policy = wan.policy_for(run_dir) if slides else None
    for slide in slides:
        image = find_image(run_dir / AI_IMAGE_DIR, slide.id)
        if image is None:
            shots.append(WanShot(run_dir, slide.id, None, False))
            continue
        request = wan.request_for(slide.id, image, load_record(image), shot_language.motion_prompt_for(slide.media),
                                  slide.media.prompt, policy)
        shots.append(WanShot(run_dir, slide.id, request, wan.cached(run_dir, request) is not None))
    return shots


Generate = Callable[[MotionPaths, Path, wan.WanRequest, Callable[[], float]], dict]


def bake(shots: list[WanShot], paths: MotionPaths, gate: Callable[[], float],
         log: Callable[[str], None] = print, generate: Generate = wan.generate) -> list[dict]:
    """Generate every shot that has a still and no cached clip; returns the new records."""
    records = []
    for shot in shots:
        label = f"{shot.run_dir.name}/{shot.slide_id}"
        if shot.request is None:
            log(f"- {label}: no still yet (run illustrate first); skipped")
        elif shot.cached:
            log(f"- {label}: cached")
        else:
            log(f"- {label}: generating (~{wan.ESTIMATED_MINUTES_PER_CLIP} min)")
            record = generate(paths, shot.run_dir, shot.request, gate)
            log(f"  {label}: {record['seconds']}s, waited {record['gate_wait_seconds']}s, "
                f"peak {record['reported_peak_gb']} GB")
            records.append(record)
    return records
