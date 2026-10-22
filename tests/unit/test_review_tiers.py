"""Cost policy (Leon 2026-10-22): sonnet everywhere except the plan stage's producer; effort low by default,
fact-checkers and arbiters medium; viewer leave threshold 0.40. Replaces the opt-in economy mode of 2026-10-19."""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.review.config import (MODEL_RANK, PLAN_PRODUCER_STAGES, THRESHOLD_NOTE, load_review)
from tests.unit.test_production_runner import run_dir as run_dir  # noqa: F401  (fixture)
from tests.unit.test_review_script_stages import Panel, _runner


def test_no_opus_outside_the_plan_producer_and_no_haiku_seat():
    for channel in (None, "yokai", "chipcat", "cel", "offwork"):
        config = load_review(channel)
        for name, stage in config.stages.items():
            for seat in stage.seats:
                assert seat.model == "sonnet", (channel, name, seat.role, seat.model)
            for tier in (stage.arbiter, stage.producer):
                if tier is not None and name not in PLAN_PRODUCER_STAGES:
                    assert tier.model == "sonnet", (channel, name)


def test_default_effort_is_low_and_facts_are_medium():
    config = load_review("yokai")
    efforts = {(name, seat.role): seat.effort for name, stage in config.stages.items() for seat in stage.seats}
    for (name, role), effort in efforts.items():
        assert effort == ("medium" if config.roles[role].kind == "fact" else "low"), (name, role)
    assert config.stages["article"].arbiter.effort == config.stages["script_facts"].arbiter.effort == "medium"
    assert config.stages["topic"].producer.model == "opus"
    assert MODEL_RANK[config.stages["topic"].producer.model] > MODEL_RANK["sonnet"]


def test_the_round_scorecard_records_the_threshold_note(run_dir: Path):  # noqa: F811
    _runner(run_dir, Panel(writer=5)).run(until="gate_deck")
    card = json.loads((run_dir / "review" / "script_structure" / "round-1" / "scorecard.json").read_text(encoding="utf-8"))
    assert card["tier_mode"] == "default"
    assert card["threshold"]["leave_median_pct"] == 0.4 and card["threshold_note"] == THRESHOLD_NOTE
    assert {s["model"] for s in card["seats"]} == {"sonnet"}


def test_reviewers_run_up_to_eight_at_once():
    assert load_review().defaults.max_parallel == 8
