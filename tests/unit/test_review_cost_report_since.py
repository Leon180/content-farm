"""review_cost_report counts only this run's calls: ``since`` of review/budget.json, undated rows excluded."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "review_cost_report.py"
spec = importlib.util.spec_from_file_location("review_cost_report", SCRIPT)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def _setup(tmp_path: Path) -> Path:
    review = tmp_path / "review"
    (review / "producers").mkdir(parents=True)
    (review / "media" / "round-1").mkdir(parents=True)
    (review / "media" / "round-1" / "scorecard.json").write_text(
        json.dumps({"at": "2026-10-22T18:00:00+00:00", "seconds": 5, "seats": [{"cost_usd": 0.5}]}), encoding="utf-8")
    rows = [{"step": "deck", "cost_usd": 3.0},                                       # undated legacy row
            {"at": "2026-10-19T10:00:00+00:00", "step": "deck", "cost_usd": 4.0},
            {"at": "2026-10-22T19:00:00+00:00", "step": "deck", "cost_usd": 1.0}]
    (review / "producers" / "producers.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    (review / "budget.json").write_text(json.dumps({"usd": 15, "since": "2026-10-22T16:00:00+00:00"}), encoding="utf-8")
    return tmp_path


def test_since_keeps_only_this_runs_calls(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path)
    summary = report.summarize(run_dir, report.budget_since(run_dir))
    assert summary["producers"]["deck"]["cost"] == 1.0
    assert summary["stages"]["media"]["cost"] == 0.5


def test_without_since_everything_counts(tmp_path: Path) -> None:
    summary = report.summarize(_setup(tmp_path))
    assert summary["producers"]["deck"]["cost"] == 8.0
