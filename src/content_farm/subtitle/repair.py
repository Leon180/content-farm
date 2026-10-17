"""Repair collapsed subtitle timings from forced alignment.

stable-ts sometimes squeezes the last words of a scene into its final instant (2026-10-17
CoWoS s13: two sentences got 0.3 s and 0.0 s cues after a 9.5 s hole with no subtitle). A run of
cues spoken impossibly fast is spread back over the gap before it, proportional to characters.
"""

from __future__ import annotations



from content_farm.subtitle.schemas import SubtitleSegment

MAX_CHARS_PER_SECOND = 9.0      # faster than any narration we produce (≈4–6 c/s)
MIN_SECONDS = 0.4
GAP_LEAD = 0.05


def _chars(segment: SubtitleSegment) -> int:
    return sum(1 for c in segment.text if not c.isspace())


def _collapsed(segment: SubtitleSegment) -> bool:
    seconds = segment.end_seconds - segment.start_seconds
    return seconds < MIN_SECONDS or _chars(segment) / max(seconds, 1e-3) > MAX_CHARS_PER_SECOND


def _spread(out: list[SubtitleSegment], i: int, j: int, start: float, end: float) -> None:
    total = sum(_chars(s) for s in out[i:j + 1]) or 1
    clock = start
    for k in range(i, j + 1):
        length = (end - start) * _chars(out[k]) / total
        out[k] = out[k].model_copy(update={"start_seconds": round(clock, 3), "end_seconds": round(clock + length, 3)})
        clock += length


def repair_collapsed(segments: tuple[SubtitleSegment, ...] | list[SubtitleSegment],
                     scene_start: float, scene_end: float | None = None) -> tuple[SubtitleSegment, ...]:
    """Spread a collapsed run over the gap before it; with no gap, re-split the previous cue's span
    together with the run (up to ``scene_end``) by characters."""
    out = list(segments)
    i = 0
    while i < len(out):
        if not _collapsed(out[i]):
            i += 1
            continue
        j = i
        while j + 1 < len(out) and _collapsed(out[j + 1]):
            j += 1
        window_start = (out[i - 1].end_seconds if i > 0 else scene_start) + GAP_LEAD
        window_end = max(out[j].end_seconds, scene_end or 0.0) if j == len(out) - 1 else out[j].end_seconds
        if window_end - window_start >= MIN_SECONDS * (j - i + 1):
            _spread(out, i, j, window_start, window_end)
        elif i > 0:
            _spread(out, i - 1, j, out[i - 1].start_seconds, window_end)
        i = j + 1
    return tuple(out)
