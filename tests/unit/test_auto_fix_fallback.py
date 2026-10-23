"""The automatic fix never stops a run (orchestrator request 2026-10-24, after the technews run2 stop at gate_article)."""

from __future__ import annotations

import json

from content_farm.production import panel_flow
from content_farm.production.auto_fix_fallback import delete_from_article, delete_from_deck
from tests.unit.test_review_article_rules import ARTICLE, BAD, _ctx, _rework_run


def _mark_auto(run_dir) -> None:
    path = run_dir / "review" / "article.fixes.json"
    path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "auto_fact_fix": True}), encoding="utf-8")


def test_a_refused_auto_fix_deletes_the_flagged_sentence_and_goes_on(tmp_path):
    run_dir = _rework_run(tmp_path)
    _mark_auto(run_dir)
    ctx, prompts = _ctx(run_dir, [BAD, BAD])
    assert panel_flow.run_producer(ctx, "article", lambda _: None) is None            # was: "不是只刪改" failure
    text = (run_dir / "article.md").read_text(encoding="utf-8")
    assert "摩根士丹利" not in text and "新加的一句" not in text and "台積電 2016 年說量太小" in text
    rows = [json.loads(x) for x in (run_dir / "review" / "auto_fix.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["event"] == "fallback_deleted" and rows[-1]["removed"] == ["p2.2"] and len(prompts) == 2
    assert text != ARTICLE


def test_without_the_auto_fix_marker_a_refused_rewrite_still_stops(tmp_path):
    run_dir = _rework_run(tmp_path)
    ctx, _ = _ctx(run_dir, [BAD, BAD])
    assert "不是只刪改" in (panel_flow.run_producer(ctx, "article", lambda _: None) or "")


def test_nothing_flagged_is_recorded_and_the_run_goes_on(tmp_path):
    run_dir = _rework_run(tmp_path)
    _mark_auto(run_dir)
    path = run_dir / "review" / "article.fixes.json"
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["steps"]["article"]["fixes"][0]["evidence"] = "文章裡沒有這句"
    plan["steps"]["article"]["fixes"][0]["problem"] = "x"
    plan["steps"]["article"]["fixes"][0]["fix"] = "y"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    ctx, _ = _ctx(run_dir, [BAD, BAD])
    assert panel_flow.run_producer(ctx, "article", lambda _: None) is None
    assert (run_dir / "article.md").read_text(encoding="utf-8") == ARTICLE             # restored, nothing deleted
    row = json.loads((run_dir / "review" / "auto_fix.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert row["event"] == "fallback_nothing_to_delete"


def test_delete_helpers_keep_original_ids_and_never_empty_a_slide():
    text, removed = delete_from_article("甲一。甲二。\n\n乙一。乙二。\n", {"p1.1", "p2.2"})
    assert text == "甲二。\n\n乙一。\n" and removed == ["p1.1", "p2.2"]
    deck = {"sections": [{"title": "s", "slides": [{"id": "a", "narration": "一句。二句。"},
                                                   {"id": "b", "narration": "只有一句。"}]}]}
    out, removed, protected = delete_from_deck(deck, {"a.1", "b.1"})
    assert out["sections"][0]["slides"][0]["narration"] == "二句。" and removed == ["a.1"] and protected == ["b.1"]
    assert out["sections"][0]["slides"][1]["narration"] == "只有一句。"
    assert deck["sections"][0]["slides"][0]["narration"] == "一句。二句。"            # the input is not mutated
