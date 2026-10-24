"""Pick 3–8 s segments of a source clip to fill a slide slot, preferring the parts that move.

``plan`` is pure (testable): it takes the clip length, the slot length and an optional per-second motion score
(:func:`motion_profile`), and returns ``Segment``s in playing order. A source shorter than the slot is slowed down (≤1.5x)
or looped by the caller; segments never exceed the source.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass

MIN_SEGMENT, MAX_SEGMENT = 3.0, 8.0
SKIP_EDGE = 0.5          # fade-in / fade-out at either end of a clip


@dataclass(frozen=True)
class Segment:
    start: float
    length: float


def segment_count(slot_seconds: float) -> int:
    return max(1, math.ceil(slot_seconds / MAX_SEGMENT - 1e-9))


def plan(source_seconds: float, slot_seconds: float, motion: list[float] | None = None,
         start: float | None = None, end: float | None = None) -> list[Segment]:
    """Segments that together last ``slot_seconds`` (or all the source has, when it is shorter).

    ``start`` alone pins a single cut at that second; with ``end`` it is the window the cuts are taken from.
    """
    if source_seconds <= 0 or slot_seconds <= 0:
        raise ValueError("source and slot must have a length")
    if end is not None:
        lo, hi = start or 0.0, min(end, source_seconds)
        if hi <= lo:
            raise ValueError("footage window is empty")
        inner = plan(hi - lo, slot_seconds, motion[int(lo):] if motion else None)
        return [Segment(round(seg.start + lo, 2), seg.length) for seg in inner]
    count = segment_count(slot_seconds)
    length = slot_seconds / count
    if source_seconds <= length + 2 * SKIP_EDGE:
        return [Segment(0.0, source_seconds)]
    if start is not None:
        return [Segment(min(max(start, 0.0), source_seconds - length), length)]
    usable = source_seconds - 2 * SKIP_EDGE
    count = min(count, max(1, int(usable // length)))
    length = min(slot_seconds / count, usable)
    if count == 1 and not motion:
        return [Segment(round(SKIP_EDGE + (usable - length) / 2, 2), length)]
    return _spread(source_seconds, count, length, motion)


def _spread(source: float, count: int, length: float, motion: list[float] | None) -> list[Segment]:
    last_start = source - SKIP_EDGE - length
    if not motion:
        step = (last_start - SKIP_EDGE) / max(count - 1, 1)
        return [Segment(round(SKIP_EDGE + i * step, 2), length) for i in range(count)]
    candidates = [s * 0.5 for s in range(int(SKIP_EDGE * 2), int(last_start * 2) + 1)]
    taken: list[float] = []
    for _ in range(count):
        free = [c for c in candidates if all(abs(c - t) >= length for t in taken)]
        if not free:
            break
        taken.append(max(free, key=lambda c: (_window_score(motion, c, length), -c)))
    return [Segment(round(t, 2), length) for t in sorted(taken)]


def _window_score(motion: list[float], start: float, length: float) -> float:
    lo, hi = int(start), min(len(motion), int(math.ceil(start + length)))
    window = motion[lo:hi]
    return sum(window) / len(window) if window else 0.0


def motion_profile(path: str, *, size: tuple[int, int] = (64, 36)) -> list[float]:
    """Mean absolute frame difference per second (1 fps, 64x36 grey). Empty list if ffmpeg or numpy is unavailable."""
    try:
        import numpy as np

        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps=1,scale={size[0]}:{size[1]},format=gray",
             "-f", "rawvideo", "-"], capture_output=True, timeout=300, check=True).stdout
    except (ImportError, OSError, subprocess.SubprocessError):
        return []
    frame = size[0] * size[1]
    frames = np.frombuffer(raw[: len(raw) // frame * frame], dtype=np.uint8).reshape(-1, frame).astype(np.int16)
    if len(frames) < 2:
        return []
    diffs = np.abs(np.diff(frames, axis=0)).mean(axis=1)
    return [0.0, *map(float, diffs)]
