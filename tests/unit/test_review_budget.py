"""Cloud-lane budget per video (cf-cost-fix, Leon 2026-10-22): over the limit the run stops and reports."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from content_farm.production.runner import Outcome
from content_farm.review import budget
from content_farm.review.config import load_review
from tests.unit.test_production_runner import run_dir as run_dir  # noqa: F401  (fixture)
from tests.unit.test_review_script_stages import Panel, _runner


def _card(root: Path, stage: str, name: str, cost: float, at: datetime, seats: int = 3) -> None:
    path = root / "review" / stage / name / "scorecard.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"at": at.isoformat(), "cost_usd": cost,
                                "seats": [{"rid": f"s{n}", "cost_usd": cost / seats} for n in range(seats)]}),
                    encoding="utf-8")


def _producer(root: Path, cost: float, at: datetime) -> None:
    path = root / "review" / "producers" / "producers.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": at.isoformat(), "step": "deck", "cost_usd": cost}) + "\n")


NOW = datetime.now(timezone.utc)


def test_spent_adds_scorecards_and_producers_and_skips_snapshots(tmp_path: Path) -> None:
    _card(tmp_path, "script_structure", "round-1", 3.0, NOW)
    _card(tmp_path, "script_structure", "cycle-1/round-1", 2.0, NOW)          # an older cycle still cost money
    _card(tmp_path, "script_structure", "round-1/snapshot", 99.0, NOW)         # a copy of reviewed files, not a call
    _producer(tmp_path, 1.5, NOW)
    used = budget.spent(tmp_path)
    assert (used.total, used.cards, used.producers) == (6.5, 5.0, 1.5)


def test_since_counts_only_later_calls(tmp_path: Path) -> None:
    _card(tmp_path, "script_structure", "round-1", 10.0, NOW - timedelta(days=2))
    _producer(tmp_path, 4.0, NOW - timedelta(days=2))
    _card(tmp_path, "title_thumb", "round-1", 1.0, NOW)
    assert budget.spent(tmp_path, since=(NOW - timedelta(hours=1)).isoformat()).total == 1.0


def test_since_ignores_undated_legacy_producer_rows(tmp_path: Path) -> None:
    path = tmp_path / "review" / "producers" / "producers.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"step": "deck", "cost_usd": 5.0}) + "\n", encoding="utf-8")
    assert budget.spent(tmp_path, since=(NOW - timedelta(hours=1)).isoformat()).total == 0.0
    assert budget.spent(tmp_path).total == 5.0


def test_limit_precedence_override_file_env_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(budget.BUDGET_ENV, raising=False)
    assert budget.limit(tmp_path)[0] == budget.DEFAULT_USD == 15.0
    assert budget.limit(tmp_path, configured=12.0)[0] == 12.0
    monkeypatch.setenv(budget.BUDGET_ENV, "20")
    assert budget.limit(tmp_path, configured=12.0)[0] == 20.0
    budget.record_raise(tmp_path, 30.0, since="2026-10-22T00:00:00+00:00")
    assert budget.limit(tmp_path, configured=12.0) == (30.0, "2026-10-22T00:00:00+00:00")
    assert budget.limit(tmp_path, override=40.0)[0] == 40.0


def test_check_is_quiet_under_the_limit_and_writes_a_stop_note_over_it(tmp_path: Path) -> None:
    _card(tmp_path, "script_structure", "round-1", 6.0, NOW)
    assert budget.check(tmp_path, configured=15.0) is None and not (tmp_path / budget.STOP_FILE).exists()
    _producer(tmp_path, 10.0, NOW)
    message = budget.check(tmp_path, configured=15.0)
    assert message and "$16.00" in message and "$15.00" in message and "不自動繼續" in message
    stop = json.loads((tmp_path / budget.STOP_FILE).read_text(encoding="utf-8"))
    assert stop["spent_usd"] == 16.0 and stop["limit_usd"] == 15.0


def test_the_shipped_default_is_fifteen_dollars() -> None:
    assert load_review().budget.usd_per_video == 15.0


def test_the_runner_stops_before_a_round_when_the_video_is_over_budget(run_dir: Path) -> None:  # noqa: F811
    _producer(run_dir, 16.0, NOW)
    panel = Panel()
    result = _runner(run_dir, panel).run(until="gate_deck")
    assert result.outcome is Outcome.FAILED and "預算" in result.message
    assert panel.calls == [], "no reviewer may start once the budget is used up"
    events = [json.loads(line) for line in (run_dir / "production.log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e.get("budget_stop") for e in events)


def test_a_raised_allowance_lets_the_same_run_continue(run_dir: Path) -> None:  # noqa: F811
    _producer(run_dir, 16.0, NOW)
    budget.record_raise(run_dir, 40.0)
    panel = Panel()
    result = _runner(run_dir, panel).run(until="gate_deck")
    assert result.outcome is not Outcome.FAILED or "預算" not in result.message
    assert panel.calls
