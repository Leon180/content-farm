"""Scene cues: when each slide is on screen and what the cat does during it.

Timing comes from the same place the draft was built from — the timeline
names in ``visual/`` — falling back to measured ``audio/scene_NNN.mp3``
lengths. Poses come from ``deck.json`` (``slide.mascot``), else from an
optional ``mascot`` key on each ``script.json`` scene, else ``idle``.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from content_farm.assembly.timeline_assembly import scan_timeline_clips
from content_farm.explainer.mascot.params import POSES
from content_farm.explainer.timeline import TimelineError, durations_from_audio

logger = logging.getLogger(__name__)


class CueError(ValueError):
    """Run directory cannot be turned into mascot cues."""


@dataclass(frozen=True)
class SlideMascot:
    """What a slide asks of the cat (resolved, validated)."""

    pose: str = "idle"
    say: str | None = None
    position: str = "right"


@dataclass(frozen=True)
class SceneCue:
    index: int  # 1-based slide number
    start: float
    end: float
    pose: str
    say: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start


def resolve_slide(mascot: dict | None, beat: str | None) -> SlideMascot:
    """Normalise one slide's ``mascot`` block. Jokes without a pose get ``deadpan``."""
    if not mascot:
        return SlideMascot(pose="deadpan" if beat == "joke" else "idle")
    pose = mascot.get("pose") or "idle"
    if pose not in POSES:
        logger.warning("unknown mascot pose %r; using idle", pose)
        pose = "idle"
    position = mascot.get("position") or "right"
    if position != "right":
        # Bottom-left would sit on the meta row (x 120–1520, y 832–872); see REPORT.
        logger.warning("mascot position %r not supported by the overlay yet; using right", position)
        position = "right"
    say = (mascot.get("say") or "").strip() or None
    return SlideMascot(pose=pose, say=say, position=position)


def slides_from_run(run_dir: Path) -> list[SlideMascot]:
    """Per-slide mascot requests from deck.json (preferred) or script.json."""
    deck_path, script_path = run_dir / "deck.json", run_dir / "script.json"
    if deck_path.is_file():
        from content_farm.explainer.deck import load_deck

        deck = load_deck(deck_path)
        return [
            resolve_slide(s.mascot.model_dump() if s.mascot else None, s.beat) for s in deck.slides
        ]
    if script_path.is_file():
        data = json.loads(script_path.read_text(encoding="utf-8"))
        scenes = sorted(data.get("scenes", []), key=lambda s: s.get("scene_number", 0))
        return [resolve_slide(s.get("mascot"), s.get("beat")) for s in scenes]
    raise CueError(f"{run_dir} has neither deck.json nor script.json")


def slide_times(run_dir: Path, count: int) -> list[tuple[float, float]]:
    """(start, end) seconds per slide, from visual/ names or scene audio lengths."""
    visual = run_dir / "visual"
    clips = scan_timeline_clips(visual) if visual.is_dir() else []
    if len(clips) == count:
        return [(c.start_seconds, c.end_seconds) for c in clips]
    if clips:
        logger.warning("visual/ has %d timeline clips for %d slides; using audio lengths",
                       len(clips), count)
    try:
        durations = durations_from_audio(run_dir / "audio", count)
    except TimelineError as exc:
        raise CueError(f"no slide timing: {exc}") from exc
    bounds = [math.fsum(durations[:i]) for i in range(count + 1)]
    return list(zip(bounds[:-1], bounds[1:]))


def build_cues(slides: Sequence[SlideMascot], times: Sequence[tuple[float, float]]) -> tuple[SceneCue, ...]:
    if len(slides) != len(times):
        raise CueError(f"{len(slides)} slides but {len(times)} timed scenes")
    return tuple(
        SceneCue(index=i, start=start, end=end, pose=slide.pose, say=slide.say)
        for i, (slide, (start, end)) in enumerate(zip(slides, times), start=1)
    )


def cues_from_run(run_dir: Path) -> tuple[SceneCue, ...]:
    slides = slides_from_run(run_dir)
    return build_cues(slides, slide_times(run_dir, len(slides)))
