import json
from datetime import datetime, timedelta, timezone

from content_farm.production import timing, timing_view
from content_farm.review import trace

T0 = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)


def at(minutes: float) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def write_lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def make_run(tmp_path):
    write_lines(tmp_path / "production.log.jsonl", [
        {"at": at(10), "step": "voice", "exit_code": 0, "seconds": 600},
        {"at": at(10), "step": "gate_title", "outcome": "waiting_gate"},
        {"at": at(100), "step": "media", "exit_code": 0, "seconds": 120},
    ])
    card = {"stage": "script_structure", "round": 1, "at": at(5), "seconds": 240, "seats": [{}, {"cached": True}],
            "verdict": {"pass": False}, "peak_parallel": 4}
    (tmp_path / "review" / "script_structure" / "round-1").mkdir(parents=True)
    (tmp_path / "review" / "script_structure" / "round-1" / "scorecard.json").write_text(json.dumps(card))
    write_lines(tmp_path / "review" / "producers" / "producers.jsonl", [
        {"at": at(2), "step": "deck", "rid": "deck-1", "seconds": 90, "cost_usd": 1.0},
        {"at": at(8), "step": "deck", "rid": "deck-2", "seconds": 120, "cost_usd": 0.5, "turns": 7},
    ])
    return tmp_path


def test_ledger_splits_machine_time_from_waits(tmp_path):
    data = timing.build(make_run(tmp_path))
    assert data["machine_s"] == 720       # voice 0–10 min swallows the round and both producers; media 98–100
    kinds = {g["kind"] for g in data["gaps"]}
    assert "decision" in kinds            # the runner stopped at gate_title, then nothing for ~90 min
    assert data["wait_s"]["decision"] > 0
    assert data["lane_s"]["local"] == 720


def test_rework_is_attributed_to_the_failed_round(tmp_path):
    data = timing.build(make_run(tmp_path))
    assert [(r["producer"], r["caused_by"]) for r in data["rework"]] == [("deck-2", "script_structure/round-1")]


def test_window_drops_older_attempts(tmp_path):
    data = timing.build(make_run(tmp_path), since=at(50))
    assert [s["name"] for s in data["spans"]] == ["media"]


def test_views_render(tmp_path):
    data = timing.write(make_run(tmp_path))
    assert (tmp_path / "timing.json").is_file()
    assert "script_structure/round-1" in timing_view.gantt(data)
    assert "top 5" in timing_view.bottlenecks(data)
    assert tmp_path.name in timing_view.compare([data])


def test_trace_summary_counts_tools_and_model_time():
    rows = [[1.0, "model", "", {}], [1.0, "tool_use", "Read", {"id": "a", "arg": "x"}],
            [3.0, "tool_result", "", {"id": "a"}], [10.0, "model", "", {}],
            [10.0, "tool_use", "Write", {"id": "b", "arg": "deck.json"}], [12.0, "tool_result", "", {"id": "b", "error": True}]]
    out = trace.summarize(rows)
    assert out["tools"]["Read"] == {"count": 1, "seconds": 2.0}
    assert out["model_seconds"] == 1.0 + 7.0
    assert out["writes"] == {"deck.json": 1} and out["tool_errors"] == 1
