"""The script stage in two parts (Leon 2026-10-18 decision 7afa95870a4e = A):

- script_structure (gate deck): viewers, writers, director; may rewrite freely; its fact check is listed, never blocks;
- script_facts (gate deck_facts): only after the structure passed; two checkers + arbiter, 0 errors, and every
  rework may only delete / edit the flagged narration sentences;
- the fact lock: after approval a deck change that only deletes / edits keeps the structure approval; a change
  that adds sentences sends the script back to the structure stage (both stages start a new cycle).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from content_farm.production import panel_flow
from content_farm.production.runner import Outcome, Runner
from content_farm.production.state import load_state
from content_farm.production.steps import Context, RunOptions, steps_for
from content_farm.review.client import Call, CallResult
from content_farm.review.config import load_review
from content_farm.review.gate import stage_for_gate
from content_farm.review.schemas import validate
from content_farm.review.sentences import deck_sentences
from tests.unit.test_production_runner import FakeExecutor, _fish_chipcat
from tests.unit.test_production_runner import run_dir as run_dir  # noqa: F401  (fixture)

CONFIG = load_review()


class Panel:
    """Every seat of every stage. ``writer``: the writers' score; ``facts``: claims per stage
    (script_structure / script_facts) for every fact-checker of that stage."""

    def __init__(self, writer: float = 8, facts: dict[str, list[dict]] | None = None):
        self.writer, self.facts, self.calls = writer, facts or {}, []

    def __call__(self, call: Call) -> CallResult:
        stage = call.cwd.parent.name
        self.calls.append((stage, call.rid))
        if call.rid.startswith("viewer-"):
            out = {"persona": call.rid, "segments": [], "left_at_sentence": None, "finish": True, "top_fixes": [],
                   "overall": ""}
        elif call.rid.startswith("fact_arbiter"):
            out = {"rulings": []}
        elif call.rid.startswith("fact_checker"):
            out = {"role": "fact_checker", "claims": self.facts.get(stage, []), "issues": [], "verdict": ""}
        else:
            out = {"role": call.rid, "score": self.writer, "rubric": {}, "issues": [], "verdict": ""}
        assert validate(out, call.schema) == [], (call.rid, validate(out, call.schema))
        return CallResult(call.rid, True, out, (), call.model, call.effort, (f"claude-{call.model}-5-5",), 1.0)

    def stages(self) -> set[str]:
        return {stage for stage, _ in self.calls}


def _runner(run_dir: Path, panel: Panel) -> Runner:
    options = RunOptions(mock_voice=True, review_client=panel)
    return Runner(Context(_fish_chipcat(), run_dir, options), executor=FakeExecutor(run_dir), log=lambda _: None)


def _first_sentence(run_dir: Path) -> tuple[str, str]:
    first = deck_sentences(json.loads((run_dir / "deck.json").read_text(encoding="utf-8")))[0]
    return first.id, first.text


def test_steps_and_stages_are_in_order():
    names = [s.name for s in steps_for(_fish_chipcat(), Path("/nonexistent"))]
    assert names.index("gate_deck") < names.index("gate_deck_facts") < names.index("thumbnail_spec")
    assert stage_for_gate("deck", short=False) == "script_structure"
    assert stage_for_gate("deck_facts", short=False) == "script_facts"
    facts = CONFIG.stages["script_facts"]
    assert [(s.role, s.count, s.model, s.effort) for s in facts.seats] == [("fact_checker", 2, "opus", "high")]
    assert facts.arbiter is not None and facts.max_rounds == 3 and facts.threshold.fact_errors_max == 0
    assert CONFIG.stages["script_structure"].threshold.fact_errors_max is None


def test_facts_stage_waits_for_the_structure_stage(run_dir: Path) -> None:  # noqa: F811
    panel = Panel(writer=5)
    result = _runner(run_dir, panel).run(until="gate_deck_facts")
    assert result.outcome is Outcome.REWORK and result.step == "gate_deck"
    assert "script_facts" not in panel.stages()
    assert not (run_dir / "review" / "script_facts").exists()


def test_structure_fact_errors_do_not_block_and_the_facts_stage_runs_next(run_dir: Path) -> None:  # noqa: F811
    sid, text = _first_sentence(run_dir)
    wrong = {"claim": "c", "status": "wrong", "evidence": text[:8], "sentence_ids": [sid], "note": "來源不同"}
    panel = Panel(writer=8, facts={"script_structure": [wrong]})
    result = _runner(run_dir, panel).run(until="gate_deck_facts")
    assert result.outcome is Outcome.COMPLETE, result.message
    state = load_state(run_dir, "chipcat")
    assert state.decisions["deck"].by == "agent-panel:script_structure"
    assert state.decisions["deck_facts"].by == "agent-panel:script_facts"
    card = json.loads((run_dir / "review" / "script_structure" / "round-1" / "scorecard.json").read_text(encoding="utf-8"))
    assert card["verdict"]["scores"]["fact_errors_advisory"] == {"fact_checker-1": 1}
    facts_seats = [c for stage, c in panel.calls if stage == "script_facts"]
    assert sorted(facts_seats) == ["fact_checker-1", "fact_checker-2"]
    assert (run_dir / panel_flow.LOCKED_DECK).is_file()


def test_facts_stage_counts_agreed_errors_and_reworks_the_deck(run_dir: Path) -> None:  # noqa: F811
    sid, text = _first_sentence(run_dir)
    wrong = {"claim": "c", "status": "wrong", "evidence": text[:8], "sentence_ids": [sid], "note": "來源不同"}
    result = _runner(run_dir, Panel(writer=8, facts={"script_facts": [wrong]})).run(until="gate_deck_facts")
    assert result.outcome is Outcome.REWORK and result.step == "gate_deck_facts"
    state = load_state(run_dir, "chipcat")
    assert state.steps["deck"].status == "rework" and state.steps["deck"].note == "review/deck_facts.fixes.json"
    assert panel_flow.rework_gate(state.steps["deck"].note) == "deck_facts"


# ── the fact stage's rework: delete / edit only, by narration sentence id ──────────────────────

def _deck(*narrations: str) -> dict:
    slides = [{"id": f"s{n}", "layout": "title", "heading": "h", "narration": text,
               "sentence_ids": [f"s{n}.{k}" for k in range(1, text.count("。") + 1)]}
              for n, text in enumerate(narrations, 1)]
    return {"title": "t", "sections": [{"title": "章", "slides": slides}]}


BEFORE = _deck("摩根士丹利估 2028 年每月 26 萬片。這句沒人點名。", "第二張投影片的旁白。")


def _facts_rework(tmp_path: Path, writes: list[dict]):
    (tmp_path / "deck.json").write_text(json.dumps(BEFORE, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "review").mkdir()
    plan = {"round": 1, "reasons": ["x"], "steps": {"deck": {"fixes": [
        {"problem": "wrong：歸屬", "fix": "改成經濟日報", "category": "fact", "who": "fact_checker-1",
         "evidence": "摩根士丹利估", "ref": {"target": "script", "sentence_ids": ["s1.1"]},
         "scope": {"sentence_ids": ["s1.1"], "titles": [], "thumbnail": False, "description": False}}]}}}
    (tmp_path / "review" / "deck_facts.fixes.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    prompts = []

    def agent(call: Call) -> CallResult:
        prompts.append(call.prompt)
        (tmp_path / "deck.json").write_text(json.dumps(writes[len(prompts) - 1], ensure_ascii=False), encoding="utf-8")
        return CallResult(call.rid, True, {"files": ["deck.json"], "summary": "ok"}, (), call.model, call.effort,
                          ("claude-opus-5-5",))
    ctx = SimpleNamespace(run_dir=tmp_path, channel=SimpleNamespace(code="chipcat"),
                          options=SimpleNamespace(review_tier=None, python="/py", review_client=agent))
    return ctx, prompts


EDITED = _deck("據經濟日報報導，2028 年每月可能 26 萬片。這句沒人點名。", "第二張投影片的旁白。")
ADDED = _deck("據經濟日報報導，2028 年每月可能 26 萬片。這句沒人點名。再加一句新的說法。", "第二張投影片的旁白。")


def test_facts_rework_that_adds_a_sentence_is_refused(tmp_path):
    ctx, prompts = _facts_rework(tmp_path, [ADDED, EDITED])
    assert panel_flow.run_producer(ctx, "deck", lambda _: None, gate="deck_facts") is None
    assert json.loads((tmp_path / "deck.json").read_text(encoding="utf-8")) == EDITED
    assert len(prompts) == 2 and "事實段" in prompts[0] and "被拒收" in prompts[1] and "再加一句" in prompts[1]
    assert "wrong：歸屬" in prompts[0]                      # the facts gate's fix list, not deck.fixes.json


def test_facts_rework_editing_an_unflagged_sentence_is_refused(tmp_path):
    touched = _deck("摩根士丹利估 2028 年每月 26 萬片。這句被偷改。", "第二張投影片的旁白。")
    ctx, _ = _facts_rework(tmp_path, [touched, touched])
    failure = panel_flow.run_producer(ctx, "deck", lambda _: None, gate="deck_facts")
    assert failure is not None and json.loads((tmp_path / "deck.json").read_text(encoding="utf-8")) == BEFORE


def test_structure_rework_is_not_guarded(tmp_path):
    ctx, prompts = _facts_rework(tmp_path, [ADDED])
    (tmp_path / "review" / "deck.fixes.json").write_text(
        (tmp_path / "review" / "deck_facts.fixes.json").read_text(encoding="utf-8"), encoding="utf-8")
    assert panel_flow.run_producer(ctx, "deck", lambda _: None, gate="deck") is None and len(prompts) == 1


# ── the fact lock ───────────────────────────────────────────────────────────────────────────────

def _approved_both(run_dir: Path) -> None:
    result = _runner(run_dir, Panel(writer=8)).run(until="gate_deck_facts")
    assert result.outcome is Outcome.COMPLETE, result.message


def _edit_first_slide(run_dir: Path, change) -> None:
    deck = json.loads((run_dir / "deck.json").read_text(encoding="utf-8"))
    slide = deck["sections"][0]["slides"][0]
    slide["narration"], slide["sentence_ids"] = change(slide["narration"], slide.get("sentence_ids") or [])
    (run_dir / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")


def test_after_the_lock_a_trim_keeps_the_structure_approval(run_dir: Path) -> None:  # noqa: F811
    _approved_both(run_dir)
    sid, text = _first_sentence(run_dir)
    _edit_first_slide(run_dir, lambda narration, ids: (narration.replace(text, "據報導，" + text, 1), ids))
    panel = Panel(writer=8)
    result = _runner(run_dir, panel).run(until="gate_deck_facts")
    assert result.outcome is Outcome.COMPLETE, result.message
    assert "script_structure" not in panel.stages() and "script_facts" in panel.stages()   # only facts re-reviewed
    assert load_state(run_dir, "chipcat").steps["gate_deck"].note.startswith("structure kept")


def test_after_the_lock_a_new_sentence_reopens_the_structure_stage(run_dir: Path) -> None:  # noqa: F811
    _approved_both(run_dir)
    _edit_first_slide(run_dir, lambda narration, ids: (narration + "這是後來新寫的一句話。", [*ids, "s99.1"]))
    panel = Panel(writer=8)
    result = _runner(run_dir, panel).run(until="gate_deck_facts")
    assert result.outcome is Outcome.COMPLETE, result.message
    assert {"script_structure", "script_facts"} <= panel.stages()        # both stages again
    structure = run_dir / "review" / "script_structure"
    assert (structure / "cycle-1" / "round-1" / "scorecard.json").is_file()
    assert (structure / "round-1" / "scorecard.json").is_file()          # the new cycle starts at round 1
    assert (run_dir / "review" / "script_facts" / "cycle-1" / "round-1").is_dir()
