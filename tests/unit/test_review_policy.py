"""review.policy (Leon 2026-10-23): score-only gates and the one-shot automatic fix of fact / licence stages."""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.review.config import FACT_STAGES, Policy, load_review
from content_farm.review.gate import panel_gate
from tests.unit.test_review_article_rules import ARTICLE, DISPUTED, ArticlePanel, _article_run
from tests.unit.test_review_gate import FakePanel, _deck

AUTO = load_review(policy=Policy())
STOP = load_review(policy=Policy(fact_on_fail="stop"))
UNFIXED = {"fact_checker-1#0": "wrong"}          # the arbiter upholds the error


def _structure(run_dir: Path, panel, config=AUTO):
    return panel_gate(run_dir, gate="deck", stage_name="script_structure", config=config, channel="chipcat",
                      channel_name="晶片貓", client=panel)


def _article(run_dir: Path, panel, config=AUTO):
    return panel_gate(run_dir, gate="article", stage_name="article", config=config, channel="chipcat",
                      channel_name="晶片貓", client=panel)


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_policy_is_on_by_default_in_the_yaml_and_never_touches_the_thresholds_it_does_not_name():
    assert AUTO.policy.score_only and AUTO.policy.fact_on_fail == "auto_fix_then_pass"
    for name, stage in AUTO.stages.items():
        if name in FACT_STAGES:
            assert stage.max_rounds == 1 and not stage.waive_on_last_round
        else:
            assert stage.max_rounds == 1 and stage.waive_on_last_round
    assert AUTO.stages["topic"].threshold.topic_min_score is None
    assert AUTO.stages["script_structure"].threshold.leave_median_pct == 0.35      # still recorded against the bar


def test_a_failing_score_is_recorded_and_the_run_goes_on(tmp_path):
    (tmp_path / "deck.json").write_text(json.dumps(_deck("開場第一句。開場第二句。"), ensure_ascii=False), encoding="utf-8")
    panel = FakePanel(writer=5.5)
    result = _structure(tmp_path, panel)
    assert result.status == "pass" and "放行" in result.message
    assert _structure(tmp_path, FakePanel(writer=5.5)).status == "pass"            # no second round, no rework
    ledger = json.loads((tmp_path / "review" / "score_ledger.json").read_text(encoding="utf-8"))
    entry = ledger["stages"]["deck"]
    assert entry["waived"] is True and entry["unmet"] and entry["comments"]
    assert ledger["after_upload"] == {"views": None, "retention": None, "ctr": None}
    assert not (tmp_path / "review" / "deck.fixes.json").exists()


def test_the_ledger_keeps_hand_filled_after_upload_numbers(tmp_path):
    from content_farm.review import score_ledger

    card = {"round": 1, "verdict": {"pass": True, "scores": {"x": 1}, "reasons": [], "issues": []}}
    path = score_ledger.record(tmp_path, "deck", "script_structure", card)
    filled = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**filled, "after_upload": {"views": 1200, "retention": 0.41, "ctr": 0.05}}), encoding="utf-8")
    score_ledger.record(tmp_path, "title", "title_thumb", card)
    assert json.loads(path.read_text(encoding="utf-8"))["after_upload"]["views"] == 1200
    assert set(json.loads(path.read_text(encoding="utf-8"))["stages"]) == {"deck", "title"}


def test_a_confirmed_error_is_fixed_once_then_the_run_passes_without_a_recheck(tmp_path):
    run_dir = _article_run(tmp_path)
    panel = ArticlePanel(DISPUTED, rulings=UNFIXED)
    first = _article(run_dir, panel)
    assert first.status == "rework" and "自動修" in first.message
    plan = json.loads((run_dir / "review" / "article.fixes.json").read_text(encoding="utf-8"))
    assert plan["auto_fact_fix"] is True and plan["restart"] == "article"
    calls = len(panel.calls)
    (run_dir / "article.md").write_text(ARTICLE.replace("摩根士丹利估 2028 年底每月 26 萬片。", ""), encoding="utf-8")
    second = _article(run_dir, panel)
    assert second.status == "pass" and "不重查" in second.message
    assert len(panel.calls) == calls                                     # nobody was asked again
    log = _lines(run_dir / "review" / "auto_fix.jsonl")
    assert [row["event"] for row in log] == ["fix_issued", "passed_without_recheck"]
    assert log[0]["errors"] and log[1]["content_changed"] is True
    decision = json.loads((run_dir / "review" / "article.decision.json").read_text(encoding="utf-8"))
    assert decision["waived"]["reasons"]


def test_a_fix_that_changed_nothing_still_passes_and_says_so(tmp_path):
    run_dir = _article_run(tmp_path)
    panel = ArticlePanel(DISPUTED, rulings=UNFIXED)
    assert _article(run_dir, panel).status == "rework"
    result = _article(run_dir, panel)                                    # the producer returned the same text
    assert result.status == "pass"
    assert _lines(run_dir / "review" / "auto_fix.jsonl")[-1]["content_changed"] is False


def test_a_clean_check_needs_no_fix(tmp_path):
    run_dir = _article_run(tmp_path)
    assert _article(run_dir, ArticlePanel(DISPUTED, rulings={"fact_checker-1#0": "ok"})).status == "pass"
    assert not (run_dir / "review" / "auto_fix.jsonl").exists()


def test_stop_mode_keeps_the_rounds_and_the_hard_stop(tmp_path):
    stage = STOP.stages["article"]
    assert stage.max_rounds == 3 and not stage.waive_on_last_round
    run_dir = _article_run(tmp_path)
    for n in range(3):
        (run_dir / "article.md").write_text(ARTICLE + f"\n版本 {n}。\n", encoding="utf-8")
        result = _article(run_dir, ArticlePanel(DISPUTED, rulings=UNFIXED), STOP)
    assert result.status == "exhausted"
    assert not (run_dir / "review" / "auto_fix.jsonl").exists()


def test_the_real_yaml_loads_with_the_policy_for_every_channel(monkeypatch):
    monkeypatch.delenv("CF_REVIEW_POLICY", raising=False)
    for channel in (None, "chipcat", "yokai", "cel", "offwork"):
        config = load_review(channel)
        assert config.policy.score_only and config.policy.fact_on_fail == "auto_fix_then_pass"
        assert all(s.max_rounds == 1 for s in config.stages.values())
