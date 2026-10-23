"""Audience / writer threshold calibration: the same drafts, personas and order, judged by a sonnet and an
opus reviewer, then the opus threshold converted onto the sonnet scale (cf-pipeline-speed 追加「觀眾門檻校正」).

Pure arithmetic lives here (testable offline); ``scripts/calibrate_audience.py`` does the paid calls.
"""

from __future__ import annotations

import random
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content_farm.review.sentences import Sentence, position_share

OPUS_LEAVE_MEDIAN = 0.50      # the default-tier (opus) threshold the economy one is converted from
LEAVE_FLOOR = 0.35            # the converted threshold never goes below this (orchestrator's decision)
_LINE = re.compile(r"^\[(?P<id>[^\]]+)\]\s+~\d+:\d+\s+(?P<text>.+)$")


@dataclass(frozen=True)
class PairedSeat:
    """One persona's answer on one draft from both models."""
    draft: str
    rid: str
    sonnet: float
    opus: float


def sentences_from_listing(text: str) -> list[Sentence]:
    """Sentences of a round's ``script.txt`` (``[id] ~m:ss text`` lines)."""
    out = []
    for line in text.splitlines():
        match = _LINE.match(line.strip())
        if match:
            out.append(Sentence(match["id"], match["id"].split(".")[0], "", match["text"], True))
    return out


def leave_share(output: dict[str, Any] | None, sentences: list[Sentence]) -> float | None:
    """Share of the script a viewer heard (1.0 = stayed); ``None`` when the seat gave no usable answer."""
    if not output:
        return None
    return position_share(sentences, output.get("left_at_sentence"))


def median_of(values: list[float]) -> float:
    return round(statistics.median(values), 3) if values else 0.0


def bootstrap_ci(values: list[float], *, stat: Any = statistics.mean, rounds: int = 4000, seed: int = 7,
                 level: float = 0.9) -> tuple[float, float]:
    """Percentile bootstrap interval of ``stat(values)``; with fewer than 2 values the interval is the value."""
    if len(values) < 2:
        only = float(values[0]) if values else 0.0
        return only, only
    rng = random.Random(seed)
    draws = sorted(stat([rng.choice(values) for _ in values]) for _ in range(rounds))
    low = draws[int(((1 - level) / 2) * (rounds - 1))]
    high = draws[int((1 - (1 - level) / 2) * (rounds - 1))]
    return round(low, 3), round(high, 3)


def convert_threshold(opus_threshold: float, diffs: list[float], *, floor: float = LEAVE_FLOOR) -> dict[str, Any]:
    """``diffs`` = opus − sonnet leave share per draft (median-level). Sonnet scale = opus threshold − mean gap,
    never below ``floor``; the interval carries the bootstrap uncertainty of the gap."""
    gap = round(statistics.mean(diffs), 3) if diffs else 0.0
    low, high = bootstrap_ci(diffs)
    return {"gap_mean": gap, "gap_ci90": [low, high], "n": len(diffs),
            "sonnet_equivalent": round(opus_threshold - gap, 3),
            "sonnet_equivalent_ci90": [round(opus_threshold - high, 3), round(opus_threshold - low, 3)],
            "threshold": round(max(floor, opus_threshold - gap), 2)}


def draft_gaps(pairs: list[PairedSeat]) -> dict[str, dict[str, float]]:
    """Per draft: sonnet / opus leave median over the paired seats and their gap."""
    out: dict[str, dict[str, float]] = {}
    for draft in dict.fromkeys(p.draft for p in pairs):
        rows = [p for p in pairs if p.draft == draft]
        s, o = median_of([p.sonnet for p in rows]), median_of([p.opus for p in rows])
        out[draft] = {"sonnet": s, "opus": o, "gap": round(o - s, 3), "seats": len(rows)}
    return out


def score_bias(pairs: list[tuple[str, float, float]]) -> dict[str, Any]:
    """Writer scores (draft/role, sonnet, opus): mean opus − sonnet with bootstrap interval; ``systematic`` when
    the 90% interval of the difference excludes zero."""
    diffs = [round(o - s, 2) for _, s, o in pairs]
    if not diffs:
        return {"n": 0, "systematic": False}
    low, high = bootstrap_ci(diffs)
    return {"n": len(diffs), "mean_gap": round(statistics.mean(diffs), 2), "ci90": [low, high],
            "systematic": low > 0 or high < 0}


def load_listing(round_dir: Path) -> list[Sentence]:
    return sentences_from_listing((round_dir / "script.txt").read_text(encoding="utf-8"))
