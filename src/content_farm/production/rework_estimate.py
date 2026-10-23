"""Offline estimate of a rework round: re-run the whole chain vs. redo only the scenes a fix list touches.

Inputs are files a run already has: ``review/<gate>.fixes.json`` (each step's ``rerender.scenes``),
``deck.json`` (how many slides there are) and ``production.log.jsonl`` (what each step cost). Per step:
``full`` = its slowest successful run in the log (a cold render), ``floor`` = its fastest (everything cached:
process start, cache lookups, concat). An incremental run redoes ``k`` of ``n`` scenes, so
``floor + (full - floor) * k / n``. The scene count is the union over every step of the plan (an upper bound:
the plan lists linked scope, not only the sentences that really changed). 🟡 an estimate, not a measurement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CHAIN = ("slides", "illustrate", "voice", "media", "assembly", "mascot", "mix")
SCENE_SCALED = frozenset({"illustrate", "voice", "media", "assembly", "mascot"})   # per-scene caches; slides / mix are flat


@dataclass(frozen=True)
class StepEstimate:
    step: str
    full_s: float
    floor_s: float
    incremental_s: float


def affected_scenes(fixes: dict) -> set[str]:
    """Every scene any step of the plan names."""
    return {str(s) for slot in fixes.get("steps", {}).values() for s in (slot.get("rerender") or {}).get("scenes", [])}


def slide_count(deck: dict) -> int:
    return sum(len(section.get("slides", [])) for section in deck.get("sections", []))


def step_costs(log_rows: list[dict]) -> dict[str, tuple[float, float]]:
    """step → (slowest, fastest) successful run, in seconds."""
    seconds: dict[str, list[float]] = {}
    for row in log_rows:
        if row.get("exit_code") == 0 and row.get("seconds") is not None and row.get("step") in CHAIN:
            seconds.setdefault(row["step"], []).append(float(row["seconds"]))
    return {step: (max(v), min(v)) for step, v in seconds.items()}


def estimate(fixes: dict, deck: dict, log_rows: list[dict]) -> list[StepEstimate]:
    scenes, total = len(affected_scenes(fixes)), max(slide_count(deck), 1)
    share = min(scenes / total, 1.0)
    out = []
    for step, (full, floor) in step_costs(log_rows).items():
        redo = floor + (full - floor) * share if step in SCENE_SCALED else floor
        out.append(StepEstimate(step, round(full, 1), round(floor, 1), round(redo, 1)))
    return sorted(out, key=lambda e: CHAIN.index(e.step))


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows
