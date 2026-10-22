"""A structure-level return to the article (script_structure: list-of-terms, no leave points) is a free rewrite with a
stated reason, fact-locked: the sentences that passed keep their numbers and source ids; only new sentences are fact-checked
(cf-chipcat-run2, from run1 where the "delete-or-edit only" rule fought a structural fix)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from content_farm.production import panel_flow
from content_farm.review import materials
from content_farm.review.article_diff import check_structural, split_article
from content_farm.review.client import Call, CallResult

APPROVED = (
    "# 3 奈米的成本\n"
    "台積電 2022 年底量產 3 奈米製程 [src:tsmc-n3]。\n"
    "據財報，2023 年第一季先進製程占營收 54% [src:tsmc-q1]。\n"
    "換算起來，一片晶圓的成本不是小數目。\n"
)


def test_moving_and_rewording_without_touching_facts_is_fine_and_new_sentences_are_listed() -> None:
    after = (
        "# 3 奈米的成本\n"
        "你知道一顆手機晶片背後有多少錢嗎？\n"                      # new hook
        "據財報，2023 年第一季先進製程占營收 54% [src:tsmc-q1]。\n"   # moved up, same facts
        "台積電 2022 年底量產 3 奈米製程 [src:tsmc-n3]，這是故事的起點。\n"   # reworded, same facts
        "換算起來，一片晶圓的成本不是小數目。\n"
    )
    problems, fresh = check_structural(APPROVED, after)
    assert problems == []
    assert [s.text for s in split_article(after) if s.id in fresh] == ["你知道一顆手機晶片背後有多少錢嗎？"]


def test_changing_a_number_or_a_source_of_a_checked_sentence_is_refused() -> None:
    wrong_number = APPROVED.replace("54%", "64%")
    wrong_source = APPROVED.replace("[src:tsmc-n3]", "[src:other]")
    for after, needle in ((wrong_number, "數字或來源"), (wrong_source, "數字或來源")):
        problems, _ = check_structural(APPROVED, after)
        assert len(problems) == 1 and needle in problems[0]


def test_dropping_a_number_from_a_checked_sentence_is_refused_too() -> None:
    problems, _ = check_structural(APPROVED, APPROVED.replace("2022 年底量產", "年底量產"))
    assert len(problems) == 1


def test_the_old_edit_only_check_would_have_refused_the_same_restructure() -> None:
    """Why the old path was wrong for this: a restructure adds sentences and reworks unflagged ones."""
    from content_farm.review.article_diff import check_rework

    after = "你知道一顆手機晶片背後有多少錢嗎？\n" + APPROVED
    assert check_rework(APPROVED, after, set()) != []
    assert check_structural(APPROVED, after)[0] == []


# ── through the producer step ───────────────────────────────────────────────────────────────

def _run(tmp_path: Path, writes: list[str], receipts: list[dict], *, gate: str = "deck"):
    (tmp_path / "review").mkdir()
    (tmp_path / "article.md").write_text(APPROVED, encoding="utf-8")
    (tmp_path / "review" / "article.approved.md").write_text(APPROVED, encoding="utf-8")
    fix = {"problem": "名詞表堆疊，缺留人點", "fix": "重構", "category": "story", "ref": {"target": "script", "scope": "global"},
           "scope": {"sentence_ids": [], "titles": [], "thumbnail": False, "description": False}}
    plan = {"round": 1, "reasons": ["離開中位 25%"], "steps": {"article": {"fixes": [fix]}}}
    (tmp_path / "review" / f"{gate}.fixes.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    prompts: list[str] = []

    def agent(call: Call) -> CallResult:
        prompts.append(call.prompt)
        (tmp_path / "article.md").write_text(writes[len(prompts) - 1], encoding="utf-8")
        return CallResult(call.rid, True, {"files": ["article.md"], "summary": "ok", **receipts[len(prompts) - 1]}, (),
                          call.model, call.effort, ("claude-sonnet-5-5",))
    ctx = SimpleNamespace(run_dir=tmp_path, channel=SimpleNamespace(code="chipcat"),
                          options=SimpleNamespace(review_tier=None, python="/py", review_client=agent))
    return ctx, prompts


RESTRUCTURED = "你知道一顆手機晶片背後有多少錢嗎？\n" + APPROVED


def test_structure_return_uses_the_structure_brief_and_accepts_a_reasoned_rewrite(tmp_path: Path) -> None:
    ctx, prompts = _run(tmp_path, [RESTRUCTURED], [{"rewrite_reason": "開場加鉤子，離開點前移"}])
    assert panel_flow.run_producer(ctx, "article", lambda _: None, gate="deck") is None
    assert "結構退回" in prompts[0] and "rewrite_reason" in prompts[0] and "只准刪改" not in prompts[0]
    assert (tmp_path / "article.md").read_text(encoding="utf-8") == RESTRUCTURED
    marker = json.loads((tmp_path / "review" / "article.rewrite.json").read_text(encoding="utf-8"))
    assert marker["new_sentences"] == 1 and "離開點" in marker["rewrite_reason"]
    assert (tmp_path / "review" / "article.locked.md").read_text(encoding="utf-8") == APPROVED


def test_a_rewrite_without_a_reason_is_refused_and_redone(tmp_path: Path) -> None:
    ctx, prompts = _run(tmp_path, [RESTRUCTURED, RESTRUCTURED], [{}, {"rewrite_reason": "開場加鉤子"}])
    assert panel_flow.run_producer(ctx, "article", lambda _: None, gate="deck") is None
    assert len(prompts) == 2 and "rewrite_reason" in prompts[1]            # first try: no reason → asked again


def test_two_rewrites_that_move_a_checked_number_stop_with_the_article_restored(tmp_path: Path) -> None:
    broken = RESTRUCTURED.replace("54%", "64%")
    ctx, _ = _run(tmp_path, [broken, broken], [{"rewrite_reason": "a rewrite"}, {"rewrite_reason": "a rewrite"}])
    failure = panel_flow.run_producer(ctx, "article", lambda _: None, gate="deck")
    assert failure and "已查核句子" in failure
    assert (tmp_path / "article.md").read_text(encoding="utf-8") == APPROVED
    assert not (tmp_path / "review" / "article.locked.md").exists()


def test_the_article_panels_own_rework_keeps_the_edit_only_guard(tmp_path: Path) -> None:
    assert panel_flow._structural_article_guard(tmp_path, "article", "article") is None
    assert panel_flow._structural_article_guard(tmp_path, "article", None) is None
    ctx, _ = _run(tmp_path, [RESTRUCTURED], [{"rewrite_reason": "r"}])
    assert panel_flow._structural_article_guard(tmp_path, "article", "deck") is not None
    assert panel_flow._structural_article_guard(tmp_path, "deck", "deck") is None


# ── the next article round: only the new sentences are fact-checked and may be edited ──────

def test_fact_checkers_see_only_the_new_sentences_marked(tmp_path: Path) -> None:
    (tmp_path / "review").mkdir()
    (tmp_path / "sources.json").write_text('{"sources": []}', encoding="utf-8")
    (tmp_path / "article.md").write_text(RESTRUCTURED, encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    plain = materials.article(tmp_path, out)
    assert "★" not in (out / "article.md").read_text(encoding="utf-8") and "差異查核" not in plain.notes["article.md"]
    (tmp_path / "review" / "article.locked.md").write_text(APPROVED, encoding="utf-8")
    marked = materials.article(tmp_path, out)
    text = (out / "article.md").read_text(encoding="utf-8")
    assert text.count("★") == 1 and "★你知道一顆手機晶片" in text and "結構改寫後的差異查核" in marked.notes["article.md"]


def test_new_sentences_stay_editable_for_the_next_rounds_fact_fixes(tmp_path: Path) -> None:
    (tmp_path / "review").mkdir()
    (tmp_path / "article.md").write_text(RESTRUCTURED, encoding="utf-8")
    assert panel_flow.changed_since_lock(tmp_path, RESTRUCTURED) == set()          # no pending rewrite
    (tmp_path / "review" / "article.locked.md").write_text(APPROVED, encoding="utf-8")
    changed = panel_flow.changed_since_lock(tmp_path, RESTRUCTURED)
    assert [s.text for s in split_article(RESTRUCTURED) if s.id in changed] == ["你知道一顆手機晶片背後有多少錢嗎？"]
