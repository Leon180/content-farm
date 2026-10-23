"""Fact-check confidence (Leon 2026-10-24: "正確性 50% 信心度就好").

A fact-checker (and the arbiter) gives every doubtful claim a ``confidence`` in [0, 1] that the claim really is
wrong or unsourced. At ``>= FACT_CONFIDENCE_MIN`` it counts as an error and goes to the one automatic fix; below it
the claim is only recorded: its status becomes ``low_confidence`` (the original one is kept in ``original_status``),
which every downstream reader (verdicts, arbitration, reuse) already treats as "not an error".
A claim without a confidence counts as certain, so older outputs behave as before.
"""

from __future__ import annotations

from typing import Any

FACT_CONFIDENCE_MIN = 0.5
ERROR_STATUSES = ("wrong", "unsourced")
LOW_CONFIDENCE = "low_confidence"
_LISTS = ("claims", "rulings")


def _demote_item(item: dict[str, Any], minimum: float) -> dict[str, Any]:
    confidence = item.get("confidence")
    if item.get("status") in ERROR_STATUSES and isinstance(confidence, (int, float)) and confidence < minimum:
        return {**item, "status": LOW_CONFIDENCE, "original_status": item["status"]}
    return item


def demote_low_confidence(output: dict[str, Any], minimum: float = FACT_CONFIDENCE_MIN) -> dict[str, Any]:
    """A copy of a fact-checker / arbiter output with sub-threshold error claims demoted to ``low_confidence``."""
    changed = {key: [_demote_item(i, minimum) for i in output[key]] for key in _LISTS if isinstance(output.get(key), list)}
    return {**output, **changed}


def low_confidence_items(output: dict[str, Any]) -> list[dict[str, Any]]:
    """The claims that were recorded but not counted."""
    return [i for key in _LISTS for i in (output.get(key) or []) if i.get("status") == LOW_CONFIDENCE]
