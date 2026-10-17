"""When each part of a slide appears, timed to the narration, so no slide sits still > 7 s.

A slide's *units* are what ``animate.js`` reveals one by one (bullet items, compare sides,
timeline events). Each unit appears just before the narration first talks about it (shared
numbers count most, then shared two-character words). Wherever the picture would still hold
longer than ``MAX_HOLD`` seconds, an emphasis *pulse* on the unit being discussed is added
(Leon 2026-10-17: 每 5–10 秒留下讓人繼續看的東西；靜態畫面 ≤ 8 秒).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from content_farm.explainer.deck import Layout, Slide

MAX_HOLD = 7.0          # s; the QC limit is 8 s, keep a margin for encoder/scene-detect slop
LEAD = 0.3              # a unit appears this long before its words
MIN_STEP = 0.8          # two reveals never closer than this
FIRST_LATEST = 4.0      # the first unit never waits longer than this (heading alone looks empty)
ENTRANCE = 1.2          # heading entrance
_NUM = re.compile(r"\d[\d,.]*")
_STRIP = re.compile(r"[\s，。、！？!?；;：:「」『』（）()\"'…—\-,.→％%]")


@dataclass(frozen=True)
class StagePlan:
    reveals: tuple[float, ...]             # seconds from slide start, one per unit
    pulses: tuple[tuple[float, int], ...]  # (seconds, unit index; -1 = the whole content)
    longest_hold: float


def units(slide: Slide) -> list[str]:
    media = slide.media
    if media is not None and media.diagram:      # a diagram's stages are its labels
        return [s.strip() for s in media.params.get("labels", "").split("|") if s.strip()]
    body = slide.body
    if slide.layout == Layout.BULLETS:
        return list(body.items)
    if slide.layout == Layout.COMPARE:
        return [f"{side.label} {' '.join(side.items)}" for side in (body.left, body.right)]
    if slide.layout == Layout.TIMELINE:
        return [f"{e.when} {e.what}" for e in body.events]
    return []


def _norm(text: str) -> str:
    return _STRIP.sub("", text)


def _score(unit: str, sentence: str) -> float:
    numbers = {n.replace(",", "").rstrip(".") for n in _NUM.findall(unit)} - {""}
    said_numbers = {n.replace(",", "").rstrip(".") for n in _NUM.findall(sentence)}   # keeps "3.3" whole
    said = _norm(sentence).replace(",", "")
    hits = sum(1 for n in numbers if n in said_numbers)
    if numbers and not hits:
        return 0.0      # a unit with numbers is said when its number is (labels share words like 倍光罩)
    score = 3.0 * hits
    plain = _norm(_NUM.sub("", unit))
    grams = {plain[i:i + 2] for i in range(len(plain) - 1)}
    return score + sum(1 for g in grams if g in said)


def match_times(unit_texts: list[str], sentences: list[tuple[float, str]], seconds: float) -> list[float]:
    """Reveal time per unit, monotonic; units nobody mentions are spread between neighbours."""
    times: list[float | None] = []
    cursor = 0
    for unit in unit_texts:
        best, best_score = None, 0.0
        for j in range(cursor, len(sentences)):
            score = _score(unit, sentences[j][1])
            if score >= 2.0 and score > best_score:
                best, best_score = j, score
                break                      # earliest sentence that clearly mentions it
        if best is None:
            times.append(None)
            continue
        cursor = best
        times.append(max(sentences[best][0] - LEAD, 0.0))
    return _fill_and_order(times, seconds)


def _fill_and_order(times: list[float | None], seconds: float) -> list[float]:
    n = len(times)
    known = [(i, t) for i, t in enumerate(times) if t is not None]
    anchors = [(-1, ENTRANCE * 0.6), *known, (n, seconds * 0.85)]
    filled: list[float] = []
    for (i0, t0), (i1, t1) in zip(anchors, anchors[1:]):
        for k in range(i0 + 1, i1):
            filled.append(t0 + (t1 - t0) * (k - i0) / (i1 - i0))
        if i1 < n:
            filled.append(t1)
    out: list[float] = []
    for k, t in enumerate(filled):
        t = min(t, FIRST_LATEST) if k == 0 else max(t, out[-1] + MIN_STEP)
        out.append(round(min(t, max(seconds - 0.5, 0)), 2))
    return out


def add_pulses(reveals: list[float], seconds: float, *, unit_count: int) -> tuple[list[tuple[float, int]], float]:
    """Pulses wherever the picture would hold > MAX_HOLD; returns them and the longest hold left."""
    events = sorted([0.0, ENTRANCE, *reveals])
    points = [*events, seconds]
    pulses: list[tuple[float, int]] = []
    longest = 0.0
    for a, b in zip(points, points[1:]):
        gap = b - a
        if gap <= MAX_HOLD:
            longest = max(longest, gap)
            continue
        extra = math.ceil(gap / MAX_HOLD) - 1
        step = gap / (extra + 1)
        for k in range(1, extra + 1):
            t = a + k * step
            shown = sum(1 for r in reveals if r <= t)
            pulses.append((round(t, 2), shown - 1 if unit_count and shown else -1))
        longest = max(longest, step)
    return pulses, round(longest, 2)


def plan(slide: Slide, sentences: list[tuple[float, str]], seconds: float) -> StagePlan:
    """``sentences``: (start seconds from the slide's start, text) of this slide's narration."""
    unit_texts = units(slide)
    reveals = match_times(unit_texts, sentences, seconds) if unit_texts else []
    pulses, longest = add_pulses(reveals, seconds, unit_count=len(unit_texts))
    return StagePlan(tuple(reveals), tuple(pulses), longest)
