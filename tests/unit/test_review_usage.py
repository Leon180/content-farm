"""Usage of the cloud lane (claude -p) is kept per seat, per producer call, per round and per video,
and ``produce.py usage`` adds the local lane's step times."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from content_farm.review import usage
from content_farm.review.client import Call, CallResult
from content_farm.review.producers import produce
from content_farm.review.rounds import write_result
from content_farm.review.scorecard_html import render
from tests.unit.test_review_gate import CONFIG, FakePanel, _deck, _gate

REPO = Path(__file__).resolve().parents[2]
SEAT_TOKENS = {"input": 3, "output": 200, "cache_read": 5000, "cache_write": 700}


class PricedPanel(FakePanel):
    def __call__(self, call: Call) -> CallResult:
        return replace(super().__call__(call), cost_usd=0.25, tokens=dict(SEAT_TOKENS), seconds=2.0)


def _producer(call: Call) -> CallResult:
    return CallResult(call.rid, True, {"files": ["deck.json"], "summary": "ok"}, (), call.model, call.effort,
                      ("claude-opus-5-5",), 30.0, 1.5, {"input": 10, "output": 900, "cache_read": 80000,
                                                         "cache_write": 4000})


def _run(tmp_path: Path) -> dict:
    (tmp_path / "deck.json").write_text(json.dumps(_deck("開場第一句。開場第二句。"), ensure_ascii=False), encoding="utf-8")
    _gate(tmp_path, PricedPanel(writer=6))                          # round 1: rework
    produce("deck", tmp_path, channel="chipcat", config=CONFIG, python="/py", client=_producer)
    (tmp_path / "deck.json").write_text(json.dumps(_deck("改過的開場？開場第二句。"), ensure_ascii=False), encoding="utf-8")
    _gate(tmp_path, PricedPanel(writer=9))                          # round 2 (+ holdout): pass
    log = [{"step": "voice", "exit_code": 0, "seconds": 80.5}, {"step": "voice", "exit_code": 0, "seconds": 20.0},
           {"step": "media", "exit_code": 1, "seconds": 5.0}, {"step": "deck", "producer": {"seconds": 30}}]
    (tmp_path / "production.log.jsonl").write_text("\n".join(json.dumps(r) for r in log) + "\n", encoding="utf-8")
    return usage.report(tmp_path)


def test_each_seat_result_file_carries_usage(tmp_path):
    _run(tmp_path)
    results = sorted((tmp_path / "review" / "script_structure" / "round-1" / "results").glob("*.json"))
    assert results
    for path in results:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["_usage"]["tokens"] == SEAT_TOKENS and data["_usage"]["cost_usd"] == 0.25
        assert data["_usage"]["model"] and data["_usage"]["models_used"]


def test_failed_seat_still_gets_a_result_file_with_usage(tmp_path):
    result = CallResult("viewer-1", False, None, ("schema: bad",), "sonnet", "low", ("claude-sonnet-5-5",), 3.0, 0.1,
                        {"input": 1, "output": 2, "cache_read": 3, "cache_write": 4})
    data = json.loads(write_result(tmp_path, result).read_text(encoding="utf-8"))
    assert data["_failed"] and data["_errors"] == ["schema: bad"] and data["_usage"]["tokens"]["cache_write"] == 4


def test_producers_jsonl_records_usage_and_time(tmp_path):
    _run(tmp_path)
    row = json.loads((tmp_path / "review" / "producers" / "producers.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["at"] and row["model"] == "sonnet" and row["cost_usd"] == 1.5 and row["tokens"]["output"] == 900


def test_report_totals_rounds_producers_and_local_steps(tmp_path):
    data = _run(tmp_path)
    stage = data["cloud"]["stages"]["script_structure"]
    seats = sum(r["calls"] for r in stage["rounds"].values())
    assert stage["review"]["calls"] == seats and set(stage["rounds"]) >= {"round-1", "round-2"}
    assert stage["review"]["cost_usd"] == round(0.25 * seats, 4)
    assert stage["producer"] == {"calls": 1, "seconds": 30.0, "cost_usd": 1.5, "models": ["claude-opus-5-5"],
                                 "tokens": {"input": 10, "output": 900, "cache_read": 80000, "cache_write": 4000},
                                 "reused": 0, "saved_usd": 0.0}
    total = data["cloud"]["total"]
    assert total["calls"] == seats + 1 and total["tokens"]["cache_read"] == 5000 * seats + 80000
    assert data["local"]["steps"]["voice"] == {"runs": 2, "seconds": 100.5, "last_seconds": 20.0, "failed": 0}
    assert data["local"]["steps"]["media"]["failed"] == 1 and "deck" not in data["local"]["steps"]


def test_scorecard_html_shows_round_subtotals_and_video_total(tmp_path):
    _run(tmp_path)
    html = render(tmp_path, "晶片貓").read_text(encoding="utf-8")
    assert "本輪小計" in html and "整支片總計" in html and "產出 agent（1 次）" in html
    assert "cache 讀" in html and "5,000" in html


def test_usage_cli_is_read_only(tmp_path):
    _run(tmp_path)
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}
    env = {"PYTHONPATH": str(REPO / "src"), "PATH": "/usr/bin:/bin"}
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / "produce.py"), "usage", "--run-dir", str(tmp_path)],
                          capture_output=True, text=True, env=env, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "雲端車道" in proc.stdout and "script_structure" in proc.stdout and "本機車道" in proc.stdout
    assert {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()} == before
