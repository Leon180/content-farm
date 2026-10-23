"""Round N+1 re-runs only the seats that need it (cf-cost-fix, Leon 2026-10-22)."""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.review.client import Call, CallResult
from content_farm.review.config import load_review
from content_farm.review.gate import panel_gate
from content_farm.review.schemas import validate

CONFIG = load_review()
EVIDENCE = "第1張第一句"


def _deck(edits: dict[str, str] | None = None, slides: int = 6) -> dict:
    """``slides`` slides of two sentences each; ids are ``s<n>.1`` / ``s<n>.2``. ``edits`` replaces a sentence."""
    edits = edits or {}
    built = []
    for n in range(1, slides + 1):
        first, second = edits.get(f"s{n}.1", f"第{n}張第一句。"), edits.get(f"s{n}.2", f"第{n}張第二句。")
        built.append({"id": f"s{n}", "layout": "title", "heading": "h", "narration": first + second})
    return {"title": "測試", "description": "說明", "sections": [{"title": "章", "slides": built}]}


def _write(run_dir: Path, deck: dict) -> None:
    (run_dir / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")


class Scripted:
    """Every seat answers; knobs per seat id. ``claims`` apply to every fact-checker."""

    def __init__(self, scores: dict[str, float] | None = None, left: dict[str, str] | None = None,
                 refs: dict[str, str] | None = None, claims: list[dict] | None = None):
        self.scores, self.left, self.refs, self.claims, self.calls = scores or {}, left or {}, refs or {}, claims or [], []

    def __call__(self, call: Call) -> CallResult:
        rid = call.rid
        self.calls.append((rid, call.cwd.name))
        ref = self.refs.get(rid)
        issue = [{"ref": {"target": "script", "sentence_ids": [ref]}, "category": "content", "severity": "med",
                  "problem": "p", "fix": "f", "evidence": EVIDENCE, "caused_by": "deck"}] if ref else []
        if rid.startswith("viewer-"):
            out = {"persona": rid, "segments": [], "left_at_sentence": self.left.get(rid), "finish": True, "overall": "",
                   "top_fixes": issue}
        elif rid.startswith("fact_arbiter"):
            out = {"rulings": []}
        elif rid.startswith("fact_checker"):
            out = {"role": "fact_checker", "claims": list(self.claims), "issues": [], "verdict": ""}
        else:
            out = {"role": rid, "score": self.scores.get(rid, 8), "rubric": {}, "issues": issue, "verdict": ""}
        assert validate(out, call.schema) == [], (rid, validate(out, call.schema))
        return CallResult(call.rid, True, out, (), call.model, call.effort, (f"claude-{call.model}-5-5",), 1.0, 0.5,
                          {"input": 1, "output": 1})

    def ran(self, holdout: bool = False) -> set[str]:
        """Seats called; the holdout viewer's own addendum round (after a pass) is left out unless asked for."""
        return {rid for rid, _ in self.calls if holdout or rid != "viewer-teacher"}


def _gate(run_dir: Path, panel: Scripted, *, gate: str = "deck", stage: str = "script_structure"):
    return panel_gate(run_dir, gate=gate, stage_name=stage, config=CONFIG, channel="chipcat", channel_name="晶片貓",
                      client=panel)


def _card(run_dir: Path, stage: str, n: int) -> dict:
    return json.loads((run_dir / "review" / stage / f"round-{n}" / "scorecard.json").read_text(encoding="utf-8"))


def test_only_the_failed_seat_and_the_checker_run_again(tmp_path: Path) -> None:
    _write(tmp_path, _deck())
    first = Scripted(scores={"writer_story-1": 5.5})
    assert _gate(tmp_path, first).status == "rework"
    assert len(first.calls) == 8                                   # round 1: 4 viewers + 3 pros + 1 checker
    _write(tmp_path, _deck({"s1.1": "第1張第一句改成問句？"}))
    second = Scripted(scores={"writer_story-1": 8.0})
    assert _gate(tmp_path, second).status == "pass"
    assert second.ran() == {"writer_story-1", "fact_checker-1"}, second.ran()
    card = _card(tmp_path, "script_structure", 2)
    carried = {s["rid"] for s in card["seats"] if s.get("carried_from")}
    assert carried >= {"writer_density-1", "director-1"} and len([r for r in carried if r.startswith("viewer-")]) == 4
    assert all(s["cost_usd"] == 0 and s["carried_from"] == "round-1" for s in card["seats"] if s.get("carried_from")
               and s["rid"] != "fact_checker-1")
    assert card["cost_usd"] == 1.0 and card["cache"]["carried"] == 6
    assert card["carry"]["previous"] == "round-1" and "上一輪沒過" in card["carry"]["reasons"]["writer_story-1"]


def test_a_viewer_who_left_early_runs_again_and_the_ones_who_stayed_do_not(tmp_path: Path) -> None:
    _write(tmp_path, _deck())
    first = Scripted(left={"viewer-commuter": "s1.2", "viewer-engineer": "s1.2", "viewer-student": "s2.1"})
    assert _gate(tmp_path, first).status == "rework"             # median of 4: three left in the first third
    _write(tmp_path, _deck({"s1.2": "第1張第二句，改了鉤子。"}))
    second = Scripted()
    assert _gate(tmp_path, second).status == "pass"
    viewers = {r for r in second.ran() if r.startswith("viewer-")}
    assert viewers == {"viewer-commuter", "viewer-engineer", "viewer-student"}, viewers


def test_a_seat_whose_findings_point_at_a_changed_sentence_runs_again(tmp_path: Path) -> None:
    _write(tmp_path, _deck())
    assert _gate(tmp_path, Scripted(scores={"writer_story-1": 5.5}, refs={"director-1": "s4.1"})).status == "rework"
    _write(tmp_path, _deck({"s4.1": "第4張第一句，被修過。"}))
    second = Scripted()
    assert _gate(tmp_path, second).status == "pass"
    assert {"writer_story-1", "director-1", "fact_checker-1"} <= second.ran()
    assert "writer_density-1" not in second.ran()


def test_a_big_change_judges_everything_again(tmp_path: Path) -> None:
    _write(tmp_path, _deck())
    assert _gate(tmp_path, Scripted(scores={"writer_story-1": 5.5})).status == "rework"
    _write(tmp_path, _deck({f"s{n}.1": f"第{n}張，整段重寫過。" for n in range(1, 5)}))      # 4 of 12 sentences
    second = Scripted()
    assert _gate(tmp_path, second).status == "pass"
    assert len(second.ran()) == 8 and not _card(tmp_path, "script_structure", 2)["cache"]["carried"]


def test_the_switch_turns_reuse_off(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CF_REVIEW_REUSE", "0")
    monkeypatch.setenv("CF_REVIEW_CACHE", "0")
    _write(tmp_path, _deck())
    assert _gate(tmp_path, Scripted(scores={"writer_story-1": 5.5})).status == "rework"
    _write(tmp_path, _deck({"s1.1": "第1張第一句改成問句？"}))
    second = Scripted()
    assert _gate(tmp_path, second).status == "pass"
    assert len(second.ran()) == 8


def test_the_holdout_is_never_carried(tmp_path: Path) -> None:
    stage = CONFIG.stages["script_structure"]
    assert stage.max_rounds == 3
    _write(tmp_path, _deck())
    assert _gate(tmp_path, Scripted(scores={"writer_story-1": 5.5})).status == "rework"
    _write(tmp_path, _deck({"s1.1": "第一次修改過的第一句。"}))
    assert _gate(tmp_path, Scripted(scores={"writer_story-1": 5.5})).status == "rework"
    _write(tmp_path, _deck({"s1.1": "第二次修改過的第一句。"}))
    third = Scripted()
    assert _gate(tmp_path, third).status == "pass"
    assert "viewer-teacher" in third.ran(holdout=True)                          # the holdout sits in the last round, fresh


# ── the fact stage: only the changed sentences are re-checked ──────────────────────────────

def _wrong(sentence: str) -> dict:
    return {"claim": "c", "status": "wrong", "evidence": EVIDENCE, "sentence_ids": [sentence], "note": "來源不同"}


def _ok(sentence: str) -> dict:
    return {"claim": "d", "status": "ok", "evidence": EVIDENCE, "sentence_ids": [sentence], "note": ""}


def _facts(run_dir: Path, panel: Scripted):
    return _gate(run_dir, panel, gate="deck_facts", stage="script_facts")


def test_fact_checkers_recheck_only_the_changed_sentence_and_keep_the_rest(tmp_path: Path) -> None:
    _write(tmp_path, _deck())
    first = Scripted(claims=[_wrong("s3.1"), _ok("s5.1")])
    assert _facts(tmp_path, first).status == "rework"
    _write(tmp_path, _deck({"s3.1": "第3張第一句，加上據報導。"}))
    second = Scripted(claims=[_ok("s3.1")])
    result = _facts(tmp_path, second)
    assert result.status == "pass", result.message
    assert {cwd for _, cwd in second.calls} == {"delta"}
    prompt = (tmp_path / "review" / "script_facts" / "round-2" / "prompts" / "fact_checker-1.md").read_text(encoding="utf-8")
    assert "★" not in prompt or "script.txt" in prompt
    delta_listing = (tmp_path / "review" / "script_facts" / "round-2" / "delta" / "script.txt").read_text(encoding="utf-8")
    assert "★ [s3.1]" in delta_listing and "s5.1" not in delta_listing         # the checker is shown the edit, not the script
    merged = json.loads((tmp_path / "review" / "script_facts" / "round-2" / "results" / "fact_checker-1.json")
                        .read_text(encoding="utf-8"))
    statuses = {(c["sentence_ids"][0], c["status"]) for c in merged["claims"]}
    assert statuses == {("s3.1", "ok"), ("s5.1", "ok")}               # the old error on s3.1 is gone, s5.1 kept


def test_an_unfixed_error_on_an_untouched_sentence_stays_an_error(tmp_path: Path) -> None:
    _write(tmp_path, _deck())
    assert _facts(tmp_path, Scripted(claims=[_wrong("s3.1"), _wrong("s5.1")])).status == "rework"
    _write(tmp_path, _deck({"s3.1": "第3張第一句，加上據報導。"}))
    result = _facts(tmp_path, Scripted(claims=[_ok("s3.1")]))
    assert result.status == "rework"                                    # s5.1 was never fixed: no need to ask again
    merged = json.loads((tmp_path / "review" / "script_facts" / "round-2" / "results" / "fact_checker-1.json")
                        .read_text(encoding="utf-8"))
    assert {(c["sentence_ids"][0], c["status"]) for c in merged["claims"]} == {("s3.1", "ok"), ("s5.1", "wrong")}


def test_a_deleted_sentence_costs_no_call(tmp_path: Path) -> None:
    _write(tmp_path, _deck())
    assert _facts(tmp_path, Scripted(claims=[_wrong("s3.2")])).status == "rework"
    deck = _deck()
    deck["sections"][0]["slides"][2]["narration"] = "第3張第一句。"                   # s3.2 deleted, nothing edited
    _write(tmp_path, deck)
    second = Scripted()
    assert _facts(tmp_path, second).status == "pass"
    assert second.calls == [], "nothing was written, so nothing needs checking"
