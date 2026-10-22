"""A rework touches only what the fix list names (cf-cost-fix, Leon 2026-10-22: no whole-file rewrites)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from content_farm.production import panel_flow
from content_farm.review import producers
from content_farm.review.client import Call, CallResult
from content_farm.review.touch_guard import deck_problems, named_in, titles_problems


def _deck(*slides: tuple[str, str], title: str = "t") -> dict:
    """(id, narration) pairs; sentence ids are ``<slide>.<n>``."""
    built = [{"id": sid, "layout": "bullets", "heading": f"h-{sid}", "narration": text, "media": {"kind": "slide"},
              "sentence_ids": [f"{sid}.{k}" for k in range(1, text.count("。") + 1)]} for sid, text in slides]
    return {"title": title, "description": "d", "sections": [{"title": "章", "slides": built}]}


BEFORE = _deck(("s1", "第一句要改。第二句別動。"), ("s2", "整張都別動。還有這句。"), ("s3", "最後一張。"))


def _plan(ids: list[str], *, target: str = "script", scope_ids: list[str] | None = None, **scope: object) -> dict:
    fix = {"problem": "p", "fix": "f", "ref": {"target": target, "sentence_ids": ids},
           "scope": {"sentence_ids": scope_ids if scope_ids is not None else ids, "titles": [], "thumbnail": False,
                     "description": False, **scope}}
    return {"round": 1, "reasons": ["x"], "steps": {"deck": {"fixes": [fix]}}}


def _edit(deck: dict, slide: str, narration: str) -> dict:
    out = json.loads(json.dumps(deck))
    for sec in out["sections"]:
        for s in sec["slides"]:
            if s["id"] == slide:
                s["narration"] = narration
    return out


# ── pure checks ───────────────────────────────────────────────────────────────────────────

def test_named_ids_come_from_the_ref_and_the_linked_scope() -> None:
    named = named_in(_plan(["s1.1"], scope_ids=["s1.1", "s3.1"]), "deck")
    assert named.sentence_ids == {"s1.1", "s3.1"} and not named.open


def test_a_fix_that_names_no_sentence_opens_the_plan() -> None:
    assert named_in(_plan([]), "deck").open
    plan = _plan([], target="media", scope_ids=[])
    plan["steps"]["deck"]["fixes"][0]["ref"]["item"] = "s08b"
    assert not named_in(plan, "deck").open            # a media fix names an item, not "the script as a whole"


def test_editing_the_named_sentence_is_fine() -> None:
    after = _edit(BEFORE, "s1", "改好的第一句。第二句別動。")
    assert deck_problems(BEFORE, after, named_in(_plan(["s1.1"]), "deck")) == []


def test_adding_a_sentence_inside_a_named_slide_is_fine() -> None:
    after = _edit(BEFORE, "s1", "改好的第一句。多一句鉤子。第二句別動。")
    assert deck_problems(BEFORE, after, named_in(_plan(["s1.1"]), "deck")) == []


def test_changing_an_unnamed_sentence_of_a_named_slide_is_refused() -> None:
    after = _edit(BEFORE, "s1", "改好的第一句。第二句被偷改。")
    problems = deck_problems(BEFORE, after, named_in(_plan(["s1.1"]), "deck"))
    assert len(problems) == 1 and "s1.2" in problems[0]


def test_changing_an_unnamed_slide_is_refused() -> None:
    after = _edit(BEFORE, "s2", "整張被重寫了。還有這句。")
    problems = deck_problems(BEFORE, after, named_in(_plan(["s1.1"]), "deck"))
    assert len(problems) == 1 and "s2" in problems[0] and "narration" in problems[0]


def test_a_non_narration_field_of_an_unnamed_slide_is_protected_too() -> None:
    after = json.loads(json.dumps(BEFORE))
    after["sections"][0]["slides"][2]["heading"] = "換標題"
    assert any("s3" in p and "heading" in p for p in deck_problems(BEFORE, after, named_in(_plan(["s1.1"]), "deck")))


def test_new_or_removed_unnamed_slides_are_refused() -> None:
    added = _deck(("s1", "第一句要改。第二句別動。"), ("s2", "整張都別動。還有這句。"), ("s3", "最後一張。"), ("s4", "新增的。"))
    assert any("新增投影片 s4" in p for p in deck_problems(BEFORE, added, named_in(_plan(["s1.1"]), "deck")))
    removed = _deck(("s1", "第一句要改。第二句別動。"), ("s3", "最後一張。"))
    assert any("s2" in p and "不能刪除" in p for p in deck_problems(BEFORE, removed, named_in(_plan(["s1.1"]), "deck")))


def test_deleting_a_named_slide_is_allowed() -> None:
    removed = _deck(("s1", "第一句要改。第二句別動。"), ("s3", "最後一張。"))
    assert deck_problems(BEFORE, removed, named_in(_plan(["s2.1", "s2.2"]), "deck")) == []


def test_description_changes_need_the_scope_to_say_so() -> None:
    after = {**BEFORE, "description": "新的說明"}
    assert deck_problems(BEFORE, after, named_in(_plan(["s1.1"]), "deck"))
    assert deck_problems(BEFORE, after, named_in(_plan(["s1.1"], description=True), "deck")) == []


def test_an_open_plan_is_not_scoped() -> None:
    assert deck_problems(BEFORE, _deck(("x1", "全部重寫。")), named_in(_plan([]), "deck")) == []


def test_unflagged_titles_must_keep_their_text() -> None:
    before = {"titles": [{"id": "T1", "text": "甲"}, {"id": "T2", "text": "乙"}]}
    after = {"titles": [{"id": "T1", "text": "甲改"}, {"id": "T2", "text": "乙被偷改"}]}
    plan = {"steps": {"thumbnail_spec": {"fixes": [{"ref": {"target": "title", "item": "T1"}, "scope": {
        "sentence_ids": [], "titles": ["T1"]}}]}}}
    problems = titles_problems(before, after, named_in(plan, "thumbnail_spec"))
    assert len(problems) == 1 and "T2" in problems[0]


# ── through the runner's producer step ─────────────────────────────────────────────────────

def _rework(tmp_path: Path, plan: dict, writes: list[dict], receipts: list[dict] | None = None):
    (tmp_path / "deck.json").write_text(json.dumps(BEFORE, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "review").mkdir()
    (tmp_path / "review" / "deck.fixes.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    prompts: list[str] = []

    def agent(call: Call) -> CallResult:
        prompts.append(call.prompt)
        (tmp_path / "deck.json").write_text(json.dumps(writes[len(prompts) - 1], ensure_ascii=False), encoding="utf-8")
        receipt = (receipts or [{}] * len(writes))[len(prompts) - 1]
        return CallResult(call.rid, True, {"files": ["deck.json"], "summary": "ok", **receipt}, (), call.model,
                          call.effort, ("claude-sonnet-5-5",))
    ctx = SimpleNamespace(run_dir=tmp_path, channel=SimpleNamespace(code="chipcat"),
                          options=SimpleNamespace(review_tier=None, python="/py", review_client=agent))
    return ctx, prompts


def test_the_rework_brief_is_a_diff_not_a_redo(tmp_path: Path) -> None:
    ctx, prompts = _rework(tmp_path, _plan(["s1.1"]), [_edit(BEFORE, "s1", "改好的第一句。第二句別動。")])
    assert panel_flow.run_producer(ctx, "deck", lambda _: None, gate="deck") is None
    brief = prompts[0]
    assert "要改的句子" in brief and "s1.1（s1）｜第一句要改。" in brief      # the id and its current wording
    assert "不要整份重寫" in brief and "deck-outline/SKILL.md" not in brief   # no skill re-read, no redo
    assert "s2.1" not in brief.split("要改的句子")[1]                          # unnamed sentences are not quoted
    assert len(brief) < len(producers.TASKS["deck"]) + 1500


def test_a_whole_file_rewrite_is_refused_restored_and_redone(tmp_path: Path) -> None:
    rewrite = _edit(_edit(BEFORE, "s1", "改好的第一句。第二句別動。"), "s2", "我順手也改了第二張。還有這句。")
    ctx, prompts = _rework(tmp_path, _plan(["s1.1"]), [rewrite, _edit(BEFORE, "s1", "改好的第一句。第二句別動。")])
    assert panel_flow.run_producer(ctx, "deck", lambda _: None, gate="deck") is None
    assert len(prompts) == 2 and "被拒收" in prompts[1] and "s2" in prompts[1]
    assert json.loads((tmp_path / "deck.json").read_text(encoding="utf-8")) == _edit(BEFORE, "s1", "改好的第一句。第二句別動。")


def test_two_refused_rewrites_stop_with_the_original_restored(tmp_path: Path) -> None:
    rewrite = _edit(BEFORE, "s2", "又改了第二張。還有這句。")
    ctx, _ = _rework(tmp_path, _plan(["s1.1"]), [rewrite, rewrite])
    failure = panel_flow.run_producer(ctx, "deck", lambda _: None, gate="deck")
    assert failure and "改到沒被點名的部分" in failure
    assert json.loads((tmp_path / "deck.json").read_text(encoding="utf-8")) == BEFORE


def test_a_structure_rewrite_needs_a_stated_reason(tmp_path: Path) -> None:
    rebuilt = _deck(("a1", "重新排過的開場。"), ("a2", "重新排過的主體。"))
    ctx, prompts = _rework(tmp_path, _plan([]), [rebuilt, rebuilt],
                           [{}, {"rewrite_reason": "整體離開點太早，把鉤子與結論前移"}])
    assert panel_flow.run_producer(ctx, "deck", lambda _: None, gate="deck") is None
    assert len(prompts) == 2 and "rewrite_reason" in prompts[1]
    events = [json.loads(line) for line in (tmp_path / "production.log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e.get("rewrite_reason") == "整體離開點太早，把鉤子與結論前移" for e in events)
