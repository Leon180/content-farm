"""Hooks ledger, chapter rules, continuity check, observations kept apart from scores (quality v5 item 7)."""

from __future__ import annotations

import json
from typing import Any

from content_farm.explainer.deck import Deck
from content_farm.explainer.lint import lint_deck
from content_farm.review import coherence, hooks_ledger, schemas, score_ledger, script_checks
from content_farm.review.materials import script as script_materials
from tests.unit.explainer_helpers import deck_dict, slide


def _hook(**kw: Any) -> dict[str, Any]:
    return {"id": "h1", "kind": "question", "text": "為什麼沒人拍到活的？", "planted": "a1", "payoff": "c1",
            "status": "paid", "note": "", **kw}


def test_ledger_structure_is_validated() -> None:
    assert hooks_ledger.validate({"hooks": [_hook()]}) == []
    codes = {i.code for i in hooks_ledger.validate({"hooks": [
        _hook(), _hook(), _hook(id="h2", kind="oops"), _hook(id="h3", status="dropped"), {"kind": "question"}]})}
    assert {"hook-duplicate", "hook-kind", "hook-dropped-note", "hook-id"} <= codes


def test_open_hooks_late_payoffs_and_unknown_slides_are_found() -> None:
    order = ["a1", "b1", "b2", "c1"]
    assert hooks_ledger.check_against_deck({"hooks": [_hook()]}, order) == []
    codes = {i.code for i in hooks_ledger.check_against_deck({"hooks": [
        _hook(id="o", status="open", payoff=""), _hook(id="e", planted="c1", payoff="a1"),
        _hook(id="m", payoff="s99"), _hook(id="n", payoff="")]}, order)}
    assert {"hook-open", "hook-order", "hook-missing-slide", "hook-no-payoff"} <= codes


def test_render_lists_each_hook_and_the_open_ones() -> None:
    text = hooks_ledger.render({"hooks": [_hook(status="open", payoff="")]}, ["a1", "c1"])
    assert "h1" in text and "未收" in text and "never paid off" in text


def _sections(extra: dict[str, Any]) -> Deck:
    sections = [{"title": "甲", "slides": [slide("a1", "title", narration="牠全長約八公尺，是目前紀錄中最大的深海動物之一，這件事讓研究者非常驚訝，也讓整個團隊興奮不已。")], **extra},
                {"title": "乙", "slides": [slide("b1", "quote")]}, {"title": "丙", "slides": [slide("c1", "quote")]}]
    return Deck.model_validate(deck_dict(sections=sections))


def test_chapter_rules_are_lint_errors() -> None:
    assert not [i for i in lint_deck(_sections({})) if i.code.startswith("must")]
    deck = _sections({"must_keep": ["八公尺", "十三公尺"], "must_avoid": ["保證", "深海"]})
    codes = [i.code for i in lint_deck(deck)]
    assert codes.count("must-keep-missing") == 1 and codes.count("must-avoid-present") == 1


def test_quantity_clash_across_sentences_is_flagged_and_approximations_are_tolerated() -> None:
    clash = coherence.suspicions([("s1", "牠全長約8公尺。"), ("s2", "別的題目。"), ("s3", "牠全長十三公尺。")])
    assert len(clash) == 1 and "8" in clash[0].message() and "13" in clash[0].message()
    assert not coherence.suspicions([("s1", "牠全長約8公尺。"), ("s2", "牠全長約8.2公尺。")])
    assert not coherence.suspicions([("s1", "成立三年。"), ("s2", "上市十年。")])   # no shared context: different things


def test_promised_count_against_the_last_ordinal() -> None:
    notes = coherence.enumeration_suspicions([("s1", "有三個方法可以證明。"), ("s2", "第一，看影片。"), ("s3", "第二，看尺寸。"),
                                              ("s4", "第三，比對。"), ("s5", "第四，再看一次。")])
    assert len(notes) == 1 and "第 4 項" in notes[0]
    assert not coherence.enumeration_suspicions([("s1", "有三個方法。"), ("s2", "第一。"), ("s3", "第三。")])


def test_chinese_numbers() -> None:
    assert [coherence.to_number(t) for t in ("十三", "二十", "一百零五", "1,200", "8.5")] == [13, 20, 105, 1200, 8.5]


def test_script_checks_findings_and_materials(tmp_path) -> None:
    deck = json.loads(_sections({}).model_dump_json())
    (tmp_path / "deck.json").write_text(json.dumps(deck), encoding="utf-8")
    (tmp_path / hooks_ledger.LEDGER).write_text(json.dumps({"version": 1, "hooks": [_hook(status="open", payoff="")]}),
                                                encoding="utf-8")
    rows = script_checks.findings(tmp_path, deck)
    assert any(level == "warn" and check == "hooks_ledger" for level, check, _ in rows)
    out = tmp_path / "mat"
    out.mkdir()
    materials = script_materials(tmp_path, out)
    assert "hooks.txt" in materials.files and "hooks.txt" in materials.visible_to("pro").files
    assert "hooks.txt" not in materials.visible_to("viewer").files


def test_pro_schema_takes_observations_and_they_are_stored_apart_from_scores(tmp_path) -> None:
    assert "observations" in schemas.PRO["properties"] and "observations" not in schemas.PRO["required"]
    card = {"round": 1, "verdict": {"scores": {"story": 6}, "pass": False, "reasons": ["story < 7"], "issues": []},
            "observations": [{"role": "pro", "quote": "牠全長約8公尺", "observed": "第 3 段連續 5 句都是數字"}]}
    score_ledger.record(tmp_path, "deck", "script_structure", card)
    entry = score_ledger.load(tmp_path)["stages"]["deck"]
    assert entry["scores"] == {"story": 6} and entry["observations"][0]["observed"].startswith("第 3 段")
    assert "observed" not in json.dumps(entry["scores"])
