"""cel-run1: a trailing [src:…] is part of its sentence, and the delete-or-edit-only guard flags the places a
fix quotes in its problem/fix text (not only the evidence)."""

import json

from content_farm.production.panel_flow import _delete_only_guard
from content_farm.review.article_diff import check_rework, split_article


def test_citation_stays_with_its_sentence():
    text = "這是舊稱。[src:a] 它規範付款。[src:b]\n"
    assert [s.text for s in split_article(text)] == ["這是舊稱。[src:a] 它規範付款。[src:b]"]


def test_deleting_a_cited_sentence_with_its_cite_is_allowed():
    before = "開頭一句。[src:a]\n它規範付款延遲與不當行為。[src:b]\n結尾一句。[src:c]\n"
    after = "開頭一句。[src:a]\n結尾一句。[src:c]\n"
    flagged = {s.id for s in split_article(before) if "它規範" in s.text}
    assert check_rework(before, after, flagged) == []


def test_guard_flags_places_quoted_in_fix_text(tmp_path):
    article = "公布了一份只針對動畫製作現場的指針。[src:a]\n結論寫成可能違法的類型。[src:b]\n"
    (tmp_path / "article.md").write_text(article, encoding="utf-8")
    (tmp_path / "review").mkdir()
    plan = {"round": 1, "steps": {"article": {"fixes": [{
        "category": "fact", "who": "fact_checker-1", "evidence": "寫成可能違法的類型。",
        "problem": "開頭說『一份只針對動畫』，實際是兩份", "fix": "改為兩份", "scope": {}}]}}}
    (tmp_path / "review" / "article.fixes.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    guard = _delete_only_guard(tmp_path, "article", "article")
    assert guard is not None and guard.flagged == {"p1.1", "p2.1"}
