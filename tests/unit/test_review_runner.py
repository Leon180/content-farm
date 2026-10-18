"""Runner with review panels: the article gate is opened by its panel (agent-panel:article),
a failed round routes rework to the article step, and a manual approve needs --override."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.production.channels import Gate
from content_farm.production.runner import Outcome, Runner, decide
from content_farm.production.state import load_state
from content_farm.production.steps import Context, RunOptions
from content_farm.review.client import Call, CallResult
from tests.unit.test_production_runner import FakeExecutor, _fish_chipcat
from tests.unit.test_production_runner import run_dir as run_dir  # noqa: F401  (fixture)


class ArticlePanel:
    def __init__(self, status: str = "ok"):
        self.status, self.calls = status, []

    def __call__(self, call: Call) -> CallResult:
        self.calls.append(call)
        if call.rid.startswith("fact_checker"):
            out = {"role": "fact_checker", "verdict": "", "issues": [],
                   "claims": [{"claim": "c", "status": self.status, "evidence": "CoWoS", "note": "來源沒有這個數字"}]}
        else:
            out = {"role": "writer_story", "score": 7, "rubric": {}, "issues": [], "verdict": ""}
        return CallResult(call.rid, True, out, (), call.model, call.effort, (f"claude-{call.model}-5-5",), 1.0)


def _runner(run_dir: Path, panel: ArticlePanel) -> Runner:
    options = RunOptions(mock_voice=True, review_client=panel)
    return Runner(Context(_fish_chipcat(), run_dir, options), executor=FakeExecutor(run_dir), log=lambda _: None)


def test_article_gate_opened_by_panel(run_dir: Path) -> None:  # noqa: F811
    panel = ArticlePanel()
    result = _runner(run_dir, panel).run(until="deck")
    assert result.outcome is Outcome.COMPLETE, result.message
    decision = load_state(run_dir, "chipcat").decisions["article"]
    assert decision.by == "agent-panel:article" and "scorecard" in decision.note
    assert sorted(c.rid for c in panel.calls) == ["fact_checker-1", "fact_checker-2", "writer_story-1"]
    assert all(c.model == "opus" and c.effort == "high" for c in panel.calls if c.rid.startswith("fact"))
    card = json.loads((run_dir / "review" / "article" / "round-1" / "scorecard.json").read_text(encoding="utf-8"))
    assert {s["model"] for s in card["seats"]} == {"opus"}


def test_failed_round_routes_rework_and_waits_for_the_article_agent(run_dir: Path) -> None:  # noqa: F811
    result = _runner(run_dir, ArticlePanel(status="wrong")).run()
    assert result.outcome is Outcome.REWORK and result.step == "gate_article" and result.exit_code == 3
    state = load_state(run_dir, "chipcat")
    assert state.steps["article"].status == "rework"
    assert (run_dir / "review" / "article.fixes.json").is_file()
    again = _runner(run_dir, ArticlePanel()).run()
    assert again.outcome is Outcome.AGENT and again.step == "article" and "退回重做" in again.message


def test_frozen_step_marked_for_rework_is_not_redone(run_dir: Path) -> None:  # noqa: F811
    _runner(run_dir, ArticlePanel(status="wrong")).run()
    assert load_state(run_dir, "chipcat").steps["article"].status == "rework"
    (run_dir / "production.frozen.json").write_text('{"steps": ["article"]}', encoding="utf-8")
    result = _runner(run_dir, ArticlePanel(status="wrong")).run()
    article = load_state(run_dir, "chipcat").steps["article"]
    assert article.status == "done" and article.note == "frozen"
    assert result.step != "article"                      # the runner moved on instead of waiting for the agent


def test_frozen_article_survives_a_later_source_addition(run_dir: Path) -> None:  # noqa: F811
    """The script step may add a source to sources.json; the frozen article is not re-verified and
    its gate keeps the earlier approval (no new article panel round)."""
    assert _runner(run_dir, ArticlePanel()).run(until="gate_article").outcome is Outcome.COMPLETE
    (run_dir / "production.frozen.json").write_text('{"steps": ["article", "gate_article"]}', encoding="utf-8")
    sources = json.loads((run_dir / "sources.json").read_text(encoding="utf-8"))
    (run_dir / "sources.json").write_text(json.dumps([*sources, {"id": "added-by-script", "url": "https://x"}]),
                                          encoding="utf-8")
    panel = ArticlePanel(status="wrong")
    executor = FakeExecutor(run_dir)
    options = RunOptions(mock_voice=True, review_client=panel)
    result = Runner(Context(_fish_chipcat(), run_dir, options), executor=executor, log=lambda _: None).run(
        until="gate_article")
    assert result.outcome is Outcome.COMPLETE, result.message
    assert panel.calls == [] and "check_article.py" not in executor.calls
    state = load_state(run_dir, "chipcat")
    assert state.steps["gate_article"].note.startswith("frozen; by agent-panel:article")


def test_frozen_gate_without_an_earlier_approval_stops(run_dir: Path) -> None:  # noqa: F811
    (run_dir / "production.frozen.json").write_text('{"steps": ["gate_article"]}', encoding="utf-8")
    result = _runner(run_dir, ArticlePanel()).run()
    assert result.outcome is Outcome.FAILED and result.step == "gate_article" and "沒有先前的核可" in result.message


def test_manual_approve_is_a_logged_back_door(run_dir: Path) -> None:  # noqa: F811
    with pytest.raises(ValueError, match="--override"):
        decide(run_dir, _fish_chipcat(), Gate.ARTICLE, "approved")
    decide(run_dir, _fish_chipcat(), Gate.ARTICLE, "approved", override="panel down, checked by hand")
    events = [json.loads(line) for line in (run_dir / "production.log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert events[-1]["override"] == "panel down, checked by hand"
    assert "MANUAL OVERRIDE" in load_state(run_dir, "chipcat").decisions["article"].note
