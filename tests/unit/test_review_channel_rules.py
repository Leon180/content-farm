"""Orchestrator decision 2026-10-19 (九尾狐 title rework broke the channel opening):
a title panel's rework only goes to the title / thumbnail spec, and every producer output is checked
against the channel's rules before it is accepted (one redo, then stop)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from content_farm.production import panel_flow
from content_farm.review.client import Call, CallResult
from content_farm.review.gate import _rework
from tests.unit.test_production_runner import _fish_chipcat
from tests.unit.test_production_runner import run_dir as run_dir  # noqa: F401  (fixture)

OPENING = "我是晶片貓"


def _card(issues: list[dict]) -> dict:
    return {"round": 1, "label": "round-1", "verdict": {"pass": False, "reasons": ["製作人判定 T6 誇大"],
                                                         "issues": issues}}


def _issue(caused_by: str | None, problem: str) -> dict:
    return {"ref": {"target": "title", "item": "T6"}, "category": "content", "severity": "high",
            "problem": problem, "fix": "改", "evidence": "", "who": "producer-1", "caused_by": caused_by}


def test_a_title_rework_only_goes_to_the_thumbnail_spec(run_dir: Path) -> None:  # noqa: F811
    (run_dir / "review").mkdir(exist_ok=True)
    issues = [_issue(None, "T6 誇大"), _issue("thumbnail_spec", "縮圖 B 沒兌現"),
              _issue("deck", "開場說最早的原典"), _issue("media", "縮圖 C 的壁畫裁太緊")]
    plan = _rework(run_dir, "title", "title_thumb", _card(issues), "thumbnail_spec")
    assert plan["restart"] == "thumbnail_spec" and set(plan["steps"]) == {"thumbnail_spec"}
    assert [a["problem"] for a in plan["advisory"]] == ["開場說最早的原典", "縮圖 C 的壁畫裁太緊"]


def test_other_stages_still_route_to_the_step_that_caused_it(run_dir: Path) -> None:  # noqa: F811
    (run_dir / "review").mkdir(exist_ok=True)
    plan = _rework(run_dir, "media", "media", _card([_issue("deck", "講稿")]), "media")
    assert plan["restart"] == "deck" and "advisory" not in plan


def _ctx(run_dir: Path, writes: list[dict]):
    calls = []

    def agent(call: Call) -> CallResult:
        calls.append(call.prompt)
        (run_dir / "deck.json").write_text(json.dumps(writes[len(calls) - 1], ensure_ascii=False), encoding="utf-8")
        return CallResult(call.rid, True, {"files": ["deck.json"], "summary": "ok"}, (), call.model, call.effort,
                          ("claude-sonnet-5-5",))
    ctx = SimpleNamespace(run_dir=run_dir, channel=_fish_chipcat(),
                          options=SimpleNamespace(review_tier=None, python="/py", review_client=agent))
    return ctx, calls


def _without_opening(deck: dict) -> dict:
    sections = [{**sec, "slides": [{**s, "narration": s["narration"].replace(OPENING, "我")} for s in sec["slides"]]}
                for sec in deck["sections"]]
    return {**deck, "sections": sections}


def test_a_rework_that_breaks_a_channel_rule_is_restored_and_redone(run_dir: Path) -> None:  # noqa: F811
    good = json.loads((run_dir / "deck.json").read_text(encoding="utf-8"))
    assert OPENING in json.dumps(good, ensure_ascii=False)           # control: the fixture keeps the rule
    bad = _without_opening(good)
    ctx, calls = _ctx(run_dir, [bad, good])
    assert panel_flow.run_producer(ctx, "deck", lambda _: None) is None
    assert len(calls) == 2 and "頻道規則" in calls[1] and OPENING in calls[1]
    assert json.loads((run_dir / "deck.json").read_text(encoding="utf-8")) == good


def test_breaking_the_rule_twice_stops_with_the_output_restored(run_dir: Path) -> None:  # noqa: F811
    good = json.loads((run_dir / "deck.json").read_text(encoding="utf-8"))
    bad = _without_opening(good)
    ctx, calls = _ctx(run_dir, [bad, bad])
    failure = panel_flow.run_producer(ctx, "deck", lambda _: None)
    assert failure is not None and "頻道規則" in failure and len(calls) == 2
    assert json.loads((run_dir / "deck.json").read_text(encoding="utf-8")) == good
