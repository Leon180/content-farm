"""Economy tier (Leon 2026-10-19, token limit): sonnet everywhere, fact-checkers and arbiters at high."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.review.config import (ECONOMY_THRESHOLD_NOTE, MODEL_RANK, REVIEW_TIER_ENV, REVIEW_TIER_FILE,
                                        economy_requested, load_review)
from tests.unit.test_production_runner import run_dir as run_dir  # noqa: F401  (fixture)
from tests.unit.test_review_script_stages import Panel, _runner


def test_economy_puts_every_seat_producer_and_arbiter_on_sonnet():
    config = load_review("yokai", economy=True)
    assert config.tier_mode == "economy"
    for name, stage in config.stages.items():
        for seat in stage.seats:
            assert MODEL_RANK[seat.model] <= MODEL_RANK["sonnet"], (name, seat.role, seat.model)
            kind = config.roles[seat.role].kind
            assert seat.effort == ("high" if kind == "fact" else "medium"), (name, seat.role, seat.effort)
        if stage.producer is not None:
            assert (stage.producer.model, stage.producer.effort) == ("sonnet", "medium"), name
        if stage.arbiter is not None:
            assert (stage.arbiter.model, stage.arbiter.effort) == ("sonnet", "high"), name


def test_economy_viewer_leave_threshold_is_scaled_and_noted():
    economy, default = load_review("yokai", economy=True), load_review("yokai")
    for name in ("script_structure", "final"):
        assert default.stages[name].threshold.leave_median_pct == 0.5
        assert economy.stages[name].threshold.leave_median_pct == 0.4
    assert "47% vs 81%" in ECONOMY_THRESHOLD_NOTE


def test_a_0_40_leave_threshold_is_rejected_outside_economy():
    from pydantic import ValidationError

    from content_farm.review.config import ReviewConfig

    raw = load_review("yokai", economy=True).model_dump()
    with pytest.raises(ValidationError, match="leave_median_pct=0.4 is looser"):
        ReviewConfig.model_validate({**raw, "tier_mode": "default",
                                     "stages": {**raw["stages"], **{n: {**s, "seats": load_review("yokai").model_dump()
                                                                         ["stages"][n]["seats"]}
                                                                    for n, s in raw["stages"].items()}}})


def test_reviewers_run_up_to_eight_at_once():
    assert load_review().defaults.max_parallel == 8


def test_default_mode_is_unchanged():
    config = load_review("yokai")
    assert config.tier_mode == "default"
    facts = config.stages["script_facts"]
    assert {(s.model, s.effort) for s in facts.seats} == {("opus", "high")}
    assert (facts.arbiter.model, facts.arbiter.effort) == ("opus", "high")
    assert (config.stages["script_structure"].producer.model) == "opus"


def test_economy_floors_apply_only_in_economy_mode():
    """A sonnet fact-checker is rejected in the default mode (the floor stays opus · high)."""
    from pydantic import ValidationError

    from content_farm.review.config import ReviewConfig

    raw = load_review("yokai", economy=True).model_dump()
    with pytest.raises(ValidationError, match="below opus"):
        ReviewConfig.model_validate({**raw, "tier_mode": "default"})


def test_economy_fact_checkers_must_stay_high():
    from pydantic import ValidationError

    from content_farm.review.config import ReviewConfig

    raw = load_review("yokai", economy=True).model_dump()
    facts = raw["stages"]["script_facts"]
    lowered = {**facts, "seats": [{**s, "effort": "medium"} for s in facts["seats"]]}
    with pytest.raises(ValidationError, match="below sonnet · high"):
        ReviewConfig.model_validate({**raw, "stages": {**raw["stages"], "script_facts": lowered}})


def test_economy_is_requested_by_env_or_run_dir_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(REVIEW_TIER_ENV, raising=False)
    assert not economy_requested(tmp_path)
    marker = tmp_path / REVIEW_TIER_FILE
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"tier": "economy", "why": "token limit"}), encoding="utf-8")
    assert economy_requested(tmp_path)
    marker.write_text(json.dumps({"tier": "default"}), encoding="utf-8")
    assert not economy_requested(tmp_path)
    monkeypatch.setenv(REVIEW_TIER_ENV, "economy")
    assert economy_requested(tmp_path) and economy_requested(None)


def test_the_round_scorecard_records_the_mode(run_dir: Path, monkeypatch: pytest.MonkeyPatch):  # noqa: F811
    monkeypatch.setenv(REVIEW_TIER_ENV, "economy")
    _runner(run_dir, Panel(writer=5)).run(until="gate_deck")
    card = json.loads((run_dir / "review" / "script_structure" / "round-1" / "scorecard.json").read_text(encoding="utf-8"))
    assert card["tier_mode"] == "economy"
    assert card["threshold"]["leave_median_pct"] == 0.4 and card["threshold_note"] == ECONOMY_THRESHOLD_NOTE
    assert {s["model"] for s in card["seats"]} == {"sonnet"}
    events = [json.loads(line) for line in (run_dir / "production.log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e.get("panel") == "script_structure" and e.get("tier_mode") == "economy" for e in events)
