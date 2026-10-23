"""claude -p client, rework routing and the panel gate end to end with a fake reviewer client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.review import client as client_mod
from content_farm.review import routing
from content_farm.review.client import Call, CallResult, argv_for, child_env, run_call
from content_farm.review.config import load_review
from content_farm.review.gate import enforce, panel_gate
from content_farm.review.schemas import schema_for, validate
from content_farm.review.sentences import Sentence

CONFIG = load_review()
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["n"], "properties": {"n": {"type": "integer"}}}


# ── client ──────────────────────────────────────────────────────────────────────────────────────

def test_argv_never_bare_and_uses_config_tier():
    argv = argv_for(Call("r", "p", SCHEMA, "opus", "high", tools=("Read", "Bash(python x/*)")))
    assert "--bare" not in argv
    assert argv[argv.index("--model") + 1] == "opus" and argv[argv.index("--effort") + 1] == "high"
    assert json.loads(argv[argv.index("--json-schema") + 1]) == SCHEMA
    assert argv[argv.index("--tools") + 1] == "Read,Bash"
    assert argv[argv.index("--allowed-tools") + 1] == "Read,Bash(python x/*)"
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"


def test_child_env_drops_api_keys():
    env = child_env({"ANTHROPIC_API_KEY": "k", "CF_ANTHROPIC_API_KEY": "k", "ANTHROPIC_AUTH_TOKEN": "t", "HOME": "/h"})
    assert env == {"HOME": "/h"}


def _envelope(output, model="claude-opus-5-5"):
    return json.dumps({"is_error": False, "structured_output": output, "total_cost_usd": 0.01,
                       "usage": {"input_tokens": 3, "output_tokens": 4}, "modelUsage": {model: {}}})


def test_schema_mismatch_retries_then_fails():
    seen = []

    def runner(argv, stdin, cwd, env, timeout):
        seen.append(stdin)
        return 0, _envelope({"n": "not an int"}), ""
    result = run_call(Call("r", "p", SCHEMA, "opus", "high", retries=1), runner=runner)
    assert not result.ok and result.attempts == 2 and len(seen) == 2 and "schema" in result.errors[0]


def test_schema_retry_succeeds_and_records_usage():
    replies = iter([_envelope({"x": 1}), _envelope({"n": 2})])
    result = run_call(Call("r", "p", SCHEMA, "opus", "high"), runner=lambda *a: (0, next(replies), ""))
    assert result.ok and result.output == {"n": 2} and result.attempts == 2
    assert result.tokens["output"] == 8 and result.cost_usd == 0.02


def test_wrong_model_answer_fails():
    result = run_call(Call("r", "p", SCHEMA, "opus", "high"),
                      runner=lambda *a: (0, _envelope({"n": 1}, "claude-sonnet-5-5"), ""))
    assert not result.ok and "model mismatch" in result.errors[0]


def test_nonzero_exit_is_infrastructure_retried_then_failed():
    naps = []
    result = run_call(Call("r", "p", SCHEMA, "opus", "high", retries=0), runner=lambda *a: (1, "", "getaddrinfo ENOTFOUND"),
                      sleep=naps.append)
    assert not result.ok and result.infra and "exit 1" in result.errors[-1]
    assert naps == [60.0, 120.0, 180.0] and result.attempts == 4


def test_network_blip_recovers_without_using_a_schema_retry():
    replies = iter([(1, "", "ENOTFOUND api.anthropic.com"), (0, _envelope({"n": 3}), "")])
    result = run_call(Call("r", "p", SCHEMA, "opus", "high", retries=0), runner=lambda *a: next(replies),
                      sleep=lambda s: None)
    assert result.ok and result.output == {"n": 3} and not result.infra


def test_schema_failure_is_not_infrastructure():
    result = run_call(Call("r", "p", SCHEMA, "opus", "high", retries=0),
                      runner=lambda *a: (0, _envelope({"n": "x"}), ""), sleep=lambda s: None)
    assert not result.ok and not result.infra


def test_infrastructure_failure_does_not_count_as_a_round(tmp_path):
    (tmp_path / "deck.json").write_text(json.dumps(_deck("開場第一句。"), ensure_ascii=False), encoding="utf-8")
    good = FakePanel(writer=9)

    def flaky(call):
        if call.rid.startswith("fact_checker"):
            return CallResult(call.rid, False, None, ("exit 1: ENOTFOUND",), call.model, call.effort, infra=True)
        return good(call)
    result = _gate(tmp_path, flaky)
    assert result.status == "blocked" and "不算" in result.message
    assert not (tmp_path / "review" / "deck.fixes.json").exists()          # nothing routed back
    assert list((tmp_path / "review" / "script_structure").glob("round-1-incomplete-*"))
    assert _gate(tmp_path, FakePanel(writer=9)).status == "pass"           # rerun reopens round 1
    assert (tmp_path / "review" / "script_structure" / "round-1" / "scorecard.json").is_file()


def test_issue_schema_requires_ref_evidence_and_cause():
    schema = schema_for("script", "pro")
    good = {"role": "director", "score": 7, "rubric": {}, "verdict": "", "issues": [
        {"ref": {"target": "script", "sentence_ids": ["s1.1"]}, "category": "content", "severity": "low",
         "problem": "p", "fix": "f", "evidence": "e", "caused_by": "deck"}]}
    assert validate(good, schema) == []
    bad = json.loads(json.dumps(good))
    del bad["issues"][0]["caused_by"]
    bad["issues"][0]["ref"]["target"] = "nowhere"
    errors = validate(bad, schema)
    assert any("caused_by" in e for e in errors) and any("nowhere" in e for e in errors)


# ── routing ─────────────────────────────────────────────────────────────────────────────────────

SENTS = [Sentence("s1.1", "s1", "開場", "一片晶圓只排得下 62 個", False),
         Sentence("s1.2", "s1", "開場", "規劃中的九倍只剩 5 個", False),
         Sentence("s5.1", "s5", "算盤", "每月 13 萬片乘 62 個", False),
         Sentence("s9.1", "s9", "結論", "回到 62 個", False)]
TEXTS = routing.Texts(SENTS, {"T1": "62 個變 5 個？", "T2": "封裝卡住了"}, '{"lines":["62→5"]}', "說明：62 個")


def test_linked_scope_finds_every_occurrence():
    issue = {"ref": {"target": "script", "sentence_ids": ["s5.1"]}, "evidence": "乘 62 個", "caused_by": "deck",
             "problem": "沒說每月", "fix": "補每月"}
    scope = routing.simple_scope(issue, TEXTS)
    assert set(scope.sentence_ids) == {"s1.1", "s5.1", "s9.1"}
    assert scope.titles == ("T1",) and scope.thumbnail and scope.description


def test_claim_change_rereviews_whole_chapter():
    issue = {"ref": {"target": "script", "sentence_ids": ["s1.2"]}, "evidence": "九倍", "caused_by": "deck",
             "claim_change": True}
    scope = routing.simple_scope(issue, TEXTS)
    assert scope.chapters == ("開場",) and {"s1.1", "s1.2"} <= set(scope.sentence_ids)


def test_plan_routes_to_earliest_cause_and_lists_downstream():
    issues = [{"ref": {"target": "video", "t": "1:00"}, "evidence": "", "caused_by": "mix", "problem": "BGM"},
              {"ref": {"target": "script", "sentence_ids": ["s1.1"]}, "evidence": "62 個", "caused_by": "deck",
               "problem": "x"}]
    plan = routing.plan(issues, TEXTS, stage="final", round_no=1, default_step="assembly")
    assert plan["restart"] == "deck" and plan["downstream"][0] == "deck" and "mix" in plan["downstream"]
    assert plan["steps"]["deck"]["rerender"]["scenes"] == ["s1", "s5", "s9"]


def test_stable_sentence_ids_are_used_when_they_line_up():
    from content_farm.review.sentences import deck_sentences

    deck = {"sections": [{"title": "開場", "slides": [
        {"id": "s1", "narration": "第一句。第二句？", "sentence_ids": ["s1.4", "s1.7"]},
        {"id": "s2", "narration": "只有一句。", "sentence_ids": ["s2.1", "s2.2"]}]}]}   # stale ids: fall back
    got = deck_sentences(deck)
    assert [(s.id, s.stable) for s in got] == [("s1.4", True), ("s1.7", True), ("s2.1", False)]


def test_frozen_step_issues_go_to_the_next_unfrozen_step():
    issues = [{"ref": {"target": "script", "sentence_ids": ["s1.1"]}, "evidence": "62 個", "caused_by": "article",
               "problem": "來源沒有"},
              {"ref": {"target": "script", "sentence_ids": ["s5.1"]}, "evidence": "13 萬片", "caused_by": "deck",
               "problem": "歸屬錯"}]
    plan = routing.plan(issues, TEXTS, stage="script", round_no=1, default_step="deck", frozen=frozenset({"article"}))
    assert plan["restart"] == "deck" and "article" not in plan["steps"] and plan["frozen"] == ["article"]
    fixes = plan["steps"]["deck"]["fixes"]
    assert [f.get("rerouted_from") for f in fixes] == ["article", None]
    with pytest.raises(routing.PlanError, match="frozen"):
        routing.unfrozen("mix", frozenset({"mix"}))


def test_gate_replans_when_the_freeze_changes(tmp_path):
    (tmp_path / "deck.json").write_text(json.dumps(_deck("開場第一句。開場第二句。"), ensure_ascii=False), encoding="utf-8")
    panel = FakePanel(writer=5.5)
    original = panel.__call__

    def article_blamed(call):
        result = original(call)
        if call.rid.startswith("viewer-"):
            result.output["top_fixes"][0]["caused_by"] = "article"
        return result
    assert _gate(tmp_path, article_blamed).rework["restart"] == "article"
    (tmp_path / "production.frozen.json").write_text('{"steps": ["article"]}', encoding="utf-8")
    again = _gate(tmp_path, FakePanel(writer=9))          # same round, no new reviews: only the plan changes
    assert again.status == "rework" and again.rework["restart"] == "deck"
    assert len(list((tmp_path / "review" / "script_structure").glob("round-*"))) == 1


def test_frozen_rework_text_says_where_to_fix(tmp_path):
    from content_farm.review.producers import _fixes_text

    plan = {"round": 1, "reasons": ["x"], "steps": {"deck": {"fixes": [
        {"problem": "結構沒有來源", "fix": "補來源", "category": "fact", "who": "fact_checker-1", "ref": {},
         "rerouted_from": "article",
         "scope": {"sentence_ids": [], "titles": [], "thumbnail": False, "description": False}}]}}}
    (tmp_path / "review").mkdir()
    (tmp_path / "review" / "deck.fixes.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    text = _fixes_text(tmp_path, "deck")
    assert "原屬 article" in text and "sources.json" in text


def test_plan_without_scope_is_refused():
    with pytest.raises(routing.PlanError, match="no linked scope"):
        routing.check({"steps": {"deck": {"fixes": [{"problem": "x"}]}}})


# ── gate ────────────────────────────────────────────────────────────────────────────────────────

def _deck(narration: str) -> dict:
    return {"title": "測試", "description": "說明", "sections": [
        {"title": "開場", "slides": [{"id": "s1", "layout": "title", "heading": "h", "narration": narration}]},
        {"title": "結論", "slides": [{"id": "s2", "layout": "title", "heading": "h", "narration": "結論一句。結論二句。"}]}]}


class FakePanel:
    """Answers every seat; writers score ``writer`` and viewers leave at ``left``."""

    def __init__(self, writer: float = 8, left: str | None = None, model: str | None = None):
        self.writer, self.left, self.model, self.calls = writer, left, model, []

    def __call__(self, call: Call) -> CallResult:
        self.calls.append(call)
        role = call.rid.rsplit("-", 1)[0] if not call.rid.startswith("viewer-") else "viewer"
        if role == "viewer":
            out = {"persona": call.rid, "segments": [], "left_at_sentence": self.left, "finish": True, "overall": "",
                   "top_fixes": [{"ref": {"target": "script", "sentence_ids": ["s1.1"]}, "category": "content",
                                  "severity": "med", "problem": "鉤子弱", "fix": "改問句", "evidence": "開場第一句",
                                  "caused_by": "deck"}]}
        elif role == "fact_checker":
            out = {"role": role, "claims": [], "issues": [], "verdict": ""}
        else:
            out = {"role": role, "score": self.writer, "rubric": {}, "issues": [], "verdict": ""}
        assert validate(out, call.schema) == []
        return CallResult(call.rid, True, out, (), call.model, call.effort, (f"claude-{self.model or call.model}-5-5",),
                          1.0, 0.0, {"input": 1, "output": 1})


def _gate(run_dir: Path, panel: FakePanel):
    return panel_gate(run_dir, gate="deck", stage_name="script_structure", config=CONFIG, channel="chipcat",
                      channel_name="晶片貓", client=panel)


def test_gate_rework_then_pass(tmp_path):
    (tmp_path / "deck.json").write_text(json.dumps(_deck("開場第一句。開場第二句。"), ensure_ascii=False), encoding="utf-8")
    first = _gate(tmp_path, FakePanel(writer=5.5))
    assert first.status == "rework" and first.rework["restart"] == "deck"
    fixes = json.loads((tmp_path / "review" / "deck.fixes.json").read_text(encoding="utf-8"))
    assert fixes["steps"]["deck"]["fixes"][0]["scope"]["sentence_ids"] == ["s1.1"]
    assert _gate(tmp_path, FakePanel(writer=9)).status == "rework"       # inputs unchanged: no new round
    (tmp_path / "deck.json").write_text(json.dumps(_deck("改過的開場？開場第二句。"), ensure_ascii=False), encoding="utf-8")
    panel = FakePanel(writer=9)
    second = _gate(tmp_path, panel)
    assert second.status == "pass", second.message
    decision = json.loads((tmp_path / "review" / "deck.decision.json").read_text(encoding="utf-8"))
    assert decision["by"] == "agent-panel:script_structure" and decision["round"] == 2
    assert {c.model for c in panel.calls if c.rid.startswith("fact_checker")} == {"sonnet"}
    assert (tmp_path / "review" / "script_structure" / "round-2-holdout" / "scorecard.json").is_file()
    from content_farm.review.scorecard_html import render

    html = render(tmp_path, "晶片貓<script>").read_text(encoding="utf-8")
    assert "前後對照：script.txt" in html and "改過的開場" in html and "<script>" not in html
    assert "未過" in html and "通過" in html


def test_gate_exhausts_after_max_rounds(tmp_path):
    for n in range(CONFIG.stages["script_structure"].max_rounds):
        (tmp_path / "deck.json").write_text(json.dumps(_deck(f"版本{n}。開場第二句。"), ensure_ascii=False),
                                            encoding="utf-8")
        result = _gate(tmp_path, FakePanel(writer=5))
    assert result.status == "exhausted" and "最後一輪" in result.message
    last = json.loads((tmp_path / "review" / "script_structure" / "round-3" / "scorecard.json").read_text(encoding="utf-8"))
    assert any(s["holdout"] for s in last["seats"])                      # holdout sits in the last round


def test_gate_blocks_wrong_model(tmp_path):
    (tmp_path / "deck.json").write_text(json.dumps(_deck("開場第一句。"), ensure_ascii=False), encoding="utf-8")
    result = _gate(tmp_path, FakePanel(writer=9, model="haiku"))
    assert result.status == "blocked" and "answered by" in result.message
    assert not (tmp_path / "review" / "deck.decision.json").exists()


def test_enforce_rejects_missing_and_stale_cards():
    assert enforce(None, CONFIG, "script_structure", "x") == ["no scorecard"]
    card = {"stage": "script_structure", "inputs": "old", "seats": [], "verdict": {"pass": True, "reasons": []}}
    problems = enforce(card, CONFIG, "script_structure", "new")
    assert "reviewed inputs changed since the scorecard" in problems
    assert any(p.startswith("viewer: 0/4") for p in problems) and any(p.startswith("fact_checker: 0/1") for p in problems)


def test_producer_cannot_read_other_runs_and_runs_only_named_scripts(tmp_path):
    from content_farm.review.producers import REPO, produce

    seen = []

    def fake(call):
        seen.append(call)
        return CallResult(call.rid, True, {"files": [], "summary": "ok"}, (), call.model, call.effort,
                          ("claude-opus-5-5",))
    produce("article", tmp_path, channel="chipcat", config=CONFIG, python="/py", client=fake)
    call = seen[0]
    assert call.model == "sonnet" and call.effort == "low"
    assert all("output" not in Path(d).parts for d in call.add_dirs) and REPO not in call.add_dirs
    bash = [t for t in call.tools if t.startswith("Bash(")]
    assert bash and all(t.startswith(f"Bash(/py {REPO}/scripts/") and t.endswith(".py:*)") for t in bash)
    assert dict(call.env)["PYTHONPATH"] == str(REPO / "src")


def test_article_rework_carries_only_fact_items(tmp_path):
    from content_farm.review.producers import _fixes_text

    plan = {"round": 1, "reasons": ["x"], "steps": {"article": {"fixes": [
        {"problem": "來源沒有這個數字", "fix": "刪掉", "category": "fact", "who": "fact_checker-1", "ref": {},
         "scope": {"sentence_ids": [], "titles": [], "thumbnail": False, "description": False}},
        {"problem": "開頭不夠戲劇化", "fix": "加鉤子", "category": "structure", "who": "writer_story-1", "ref": {},
         "scope": {"sentence_ids": [], "titles": [], "thumbnail": False, "description": False}}]}}}
    (tmp_path / "review").mkdir()
    (tmp_path / "review" / "article.fixes.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    text = _fixes_text(tmp_path, "article")
    assert "來源沒有這個數字" in text and "開頭不夠戲劇化" not in text
    notes = json.loads((tmp_path / "review" / "article.story_notes.json").read_text(encoding="utf-8"))
    assert notes[0]["problem"] == "開頭不夠戲劇化"


def test_default_client_is_claude_cli_and_tests_use_a_stub():
    assert client_mod.CLAUDE_BIN == "claude"
    assert client_mod.claude_bin().endswith("claude-stub")
    result = run_call(Call("r", "p", SCHEMA, "haiku", "low", retries=0), sleep=lambda s: None)
    assert not result.ok and "exit 97" in result.errors[-1]
