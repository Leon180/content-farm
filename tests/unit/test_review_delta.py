"""Delta fact-check (orchestrator decision on 80bd30689ee7 follow-up): after the fact stage approved,
a later trim or qualifier is re-checked sentence by sentence instead of using up the stage's rounds."""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.production import panel_flow
from content_farm.production.runner import Outcome
from content_farm.production.state import load_state
from content_farm.review.article_diff import ArticleSentence
from content_farm.review.config import load_review
from content_farm.review.delta import DELTA_MAX, delta_gate, edited_sentences
from tests.unit.test_production_runner import run_dir as run_dir  # noqa: F401  (fixture)
from tests.unit.test_review_script_stages import Panel, _approved_both, _edit_first_slide, _first_sentence, _runner

FACTS = "review/script_facts"


def test_edited_sentences_ignores_deletions_and_spacing():
    old = [ArticleSentence("a", "一。"), ArticleSentence("b", "二 。"), ArticleSentence("c", "三。")]
    new = [ArticleSentence("a", "據報導，一。"), ArticleSentence("b", "二。")]
    assert edited_sentences(old, new) == ["a"]


def _qualify_first(run_dir: Path) -> str:
    sid, text = _first_sentence(run_dir)
    _edit_first_slide(run_dir, lambda narration, ids: (narration.replace(text, "據報導，" + text, 1), ids))
    return sid


def test_a_qualifier_after_approval_is_delta_checked_without_spending_a_round(run_dir: Path) -> None:  # noqa: F811
    _approved_both(run_dir)
    sid = _qualify_first(run_dir)
    panel = Panel(writer=8)
    result = _runner(run_dir, panel).run(until="gate_deck_facts")
    assert result.outcome is Outcome.COMPLETE, result.message
    facts = run_dir / FACTS
    assert not (facts / "round-2").exists()                                  # no regular round spent
    card = json.loads((facts / "round-1-delta-1" / "scorecard.json").read_text(encoding="utf-8"))
    assert card["only_sentences"] == [sid] and card["delta_sentences"] == [sid]
    listing = (facts / "round-1-delta-1" / "script.txt").read_text(encoding="utf-8")
    assert f"★ [{sid}]" in listing and "差異查核" in listing
    assert sorted(rid for stage, rid in panel.calls if stage == "script_facts")[-2:] == ["fact_checker-1", "fact_checker-2"]
    state = load_state(run_dir, "chipcat")
    assert state.decisions["deck_facts"].by == "agent-panel:script_facts"
    assert json.loads((run_dir / panel_flow.FACTS_LOCKED_DECK).read_text(encoding="utf-8")) == \
        json.loads((run_dir / "deck.json").read_text(encoding="utf-8"))      # new baseline


def _trim_last_slide(run_dir: Path) -> None:
    """Drop the last narration sentence of a middle slide with two or more (the channel's opening and
    sign-off slides stay intact)."""
    deck = json.loads((run_dir / "deck.json").read_text(encoding="utf-8"))
    every = [s for sec in deck["sections"] for s in sec["slides"]]
    slides = [s for s in every[3:-1] if s.get("narration", "").count("。") >= 2]
    slide = slides[len(slides) // 2]
    parts = [p + "。" for p in slide["narration"].split("。") if p]
    slide["narration"], slide["sentence_ids"] = "".join(parts[:-1]), (slide.get("sentence_ids") or [])[:len(parts) - 1]
    (run_dir / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")


def test_a_pure_trim_after_approval_needs_no_reviewer(run_dir: Path) -> None:  # noqa: F811
    _approved_both(run_dir)
    _trim_last_slide(run_dir)
    panel = Panel(writer=8)
    result = _runner(run_dir, panel).run(until="gate_deck_facts")
    assert result.outcome is Outcome.COMPLETE, result.message
    assert not panel.calls                                                    # neither stage called a reviewer
    assert not list((run_dir / FACTS).glob("round-*-delta-*"))


def test_an_error_in_an_edited_sentence_sends_the_deck_back(run_dir: Path) -> None:  # noqa: F811
    _approved_both(run_dir)
    sid = _qualify_first(run_dir)
    wrong = {"claim": "c", "status": "wrong", "evidence": "據報導", "sentence_ids": [sid], "note": "沒有這篇報導"}
    result = _runner(run_dir, Panel(writer=8, facts={"script_facts": [wrong]})).run(until="gate_deck_facts")
    assert result.outcome is Outcome.REWORK and result.step == "gate_deck_facts", result.message
    state = load_state(run_dir, "chipcat")
    assert state.steps["deck"].status == "rework" and state.steps["deck"].note == "review/deck_facts.fixes.json"


def test_errors_outside_the_edited_sentences_are_not_judged(run_dir: Path) -> None:  # noqa: F811
    _approved_both(run_dir)
    _qualify_first(run_dir)
    elsewhere = {"claim": "c", "status": "wrong", "evidence": "x", "sentence_ids": ["s99.9"], "note": "前後文"}
    result = _runner(run_dir, Panel(writer=8, facts={"script_facts": [elsewhere]})).run(until="gate_deck_facts")
    assert result.outcome is Outcome.COMPLETE, result.message


def test_delta_checks_stop_after_the_limit(run_dir: Path) -> None:  # noqa: F811
    _approved_both(run_dir)
    sid = _qualify_first(run_dir)
    wrong = {"claim": "c", "status": "wrong", "evidence": "據報導", "sentence_ids": [sid], "note": "n"}
    panel = Panel(writer=8, facts={"script_facts": [wrong]})
    kwargs = dict(gate="deck_facts", stage_name="script_facts", config=load_review("chipcat"), channel="chipcat",
                  channel_name="晶片貓", locked_deck=run_dir / panel_flow.FACTS_LOCKED_DECK, client=panel)
    statuses = [delta_gate(run_dir, **kwargs).status for _ in range(DELTA_MAX + 1)]
    assert statuses == ["rework"] * DELTA_MAX + ["exhausted"]
    assert len(list((run_dir / FACTS).glob("round-*-delta-*"))) == DELTA_MAX


def test_an_approval_from_before_the_baseline_file_uses_the_round_snapshot(run_dir: Path) -> None:  # noqa: F811
    _approved_both(run_dir)
    (run_dir / panel_flow.FACTS_LOCKED_DECK).unlink()          # as in runs approved before this change
    sid = _qualify_first(run_dir)
    result = _runner(run_dir, Panel(writer=8)).run(until="gate_deck_facts")
    assert result.outcome is Outcome.COMPLETE, result.message
    card = json.loads((run_dir / FACTS / "round-1-delta-1" / "scorecard.json").read_text(encoding="utf-8"))
    assert card["delta_sentences"] == [sid]


def test_a_new_sentence_is_not_a_delta(run_dir: Path) -> None:  # noqa: F811
    _approved_both(run_dir)
    locked = run_dir / panel_flow.FACTS_LOCKED_DECK
    _edit_first_slide(run_dir, lambda narration, ids: (narration + "這是後來新寫的一句話。", [*ids, "s99.1"]))
    assert delta_gate(run_dir, gate="deck_facts", stage_name="script_facts", config=load_review("chipcat"),
                      channel="chipcat", channel_name="晶片貓", locked_deck=locked, client=Panel()) is None
