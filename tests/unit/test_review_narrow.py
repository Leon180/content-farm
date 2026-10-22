"""Item 2 (cf-pipeline-speed): the fix list names less. narrow.py caps issues per seat and by share of the script,
claim_change expands to slides not chapters, a script issue must name sentences, a video issue gets ids from its time."""

from __future__ import annotations

from content_farm.review import routing
from content_farm.review.narrow import narrow, sentences_at, with_sentences_from_time
from content_farm.review.schemas import schema_for, validate
from content_farm.review.sentences import Sentence
from content_farm.review.verdicts import verify_issue


def _sentences(slides: int = 10, per: int = 5) -> list[Sentence]:
    return [Sentence(f"s{s}.{n}", f"s{s}", f"章{s // 5}", f"句{s}-{n}的內容。", True)
            for s in range(1, slides + 1) for n in range(1, per + 1)]


def _issue(who: str, ids: list[str], severity: str = "med", **extra) -> dict:
    return {"who": who, "ref": {"target": "script", "sentence_ids": ids}, "category": "content", "severity": severity,
            "problem": "p", "fix": "f", "evidence": "e", **extra}


def test_per_seat_cap_keeps_the_heaviest() -> None:
    sentences = _sentences()
    issues = [_issue("director-1", [f"s{n}.1"], "low") for n in range(1, 9)] + [_issue("director-1", ["s9.1"], "high")]
    kept, deferred, stats = narrow(issues, sentences, per_seat=3, hard=1.0)
    assert len(kept) == 3 and any(i["severity"] == "high" for i in kept)
    assert len(deferred) == 6 and stats["issues_before"] == 9 and stats["issues_after"] == 3


def test_union_is_cut_at_the_hard_share() -> None:
    sentences = _sentences()                                                        # 50 sentences
    issues = [_issue(f"seat-{n}", [f"s{n}.{k}" for k in range(1, 5)]) for n in range(1, 9)]   # 8 × 4 = 32 ids
    kept, deferred, stats = narrow(issues, sentences, hard=0.30)
    assert stats["named_before"] == 32 and stats["named_after"] <= 15
    assert len(kept) + len(deferred) == 8 and len(deferred) == 5 and stats["over_warn"] is False   # 12/50 = 24%


def test_global_with_reason_and_non_script_issues_pass_through() -> None:
    sentences = _sentences()
    big = _issue("a", [s.id for s in sentences[:30]], scope=None)
    big["ref"].update(scope="global", why_global="整支節奏都慢")
    title = {"who": "t", "ref": {"target": "title", "item": "T1"}, "severity": "high", "category": "title"}
    kept, deferred, _ = narrow([big, title], sentences, hard=0.1)
    assert kept == [big, title] and deferred == []


def test_fact_issues_rank_first_and_shared_ids_vote() -> None:
    sentences = _sentences()
    fact = _issue("fact_checker-1", ["s1.1"], "low", category="fact")
    voted = [_issue(f"seat-{n}", ["s2.1"], "med") for n in range(3)]
    lonely = _issue("seat-9", ["s3.1"], "med")
    kept, _, _ = narrow([lonely, *voted, fact], sentences, per_seat=1, hard=0.05)   # room for exactly 2 sentences... first always kept
    ids = {i["ref"]["sentence_ids"][0] for i in kept}
    assert "s1.1" in ids and "s3.1" not in ids


def test_nothing_changes_when_under_the_limits() -> None:
    sentences = _sentences()
    issues = [_issue("a", ["s1.1"]), _issue("b", ["s2.1"])]
    kept, deferred, stats = narrow(issues, sentences)
    assert kept == issues and deferred == [] and stats["over_warn"] is False


def test_claim_change_expands_to_slides_not_the_chapter() -> None:
    sentences = _sentences()
    texts = routing.Texts(sentences)
    issue = _issue("a", ["s2.1"], claim_change=True, evidence="")
    scope = routing.simple_scope(issue, texts)
    assert set(scope.sentence_ids) == {f"s2.{n}" for n in range(1, 6)}               # the slide, not slides 1-4 of 章0
    assert scope.chapters == ("章0",)                                                 # whole chapter still goes back to review
    wider = routing.simple_scope({**issue, "affected_slides": ["s3", "s4", "s5", "s6"]}, texts)
    assert {s.split(".")[0] for s in wider.sentence_ids} == {"s2", "s3", "s4", "s5"}   # extra slides capped at 3


def test_common_terms_do_not_link() -> None:
    sentences = [Sentence(f"s1.{n}", "s1", "A", f"台積電第{n}句。", True) for n in range(1, 9)]
    scope = routing.simple_scope(_issue("a", ["s1.1"], evidence="台積電"), routing.Texts(sentences))
    assert scope.sentence_ids == ("s1.1",)


def test_script_issue_without_sentences_is_dropped_unless_global() -> None:
    ctx = {"corpus": "ee", "sentence_ids": {"s1.1"}, "items": set(), "duration": 0}
    bare = {"ref": {"target": "script"}, "evidence": "ee"}
    assert "names no sentence" in verify_issue(bare, **ctx)
    assert verify_issue({"ref": {"target": "script", "scope": "global", "why_global": "全片慢"}, "evidence": "ee"}, **ctx) == ""
    assert verify_issue({"ref": {"target": "script", "sentence_ids": ["s1.1"]}, "evidence": "ee"}, **ctx) == ""


def test_time_maps_to_neighbouring_sentences() -> None:
    times = [["a", 0, 5], ["b", 5, 9], ["c", 9, 14], ["d", 14, 20]]
    assert sentences_at(times, 10.0) == ["b", "c", "d"]
    assert sentences_at(times, 0.0, radius=0) == ["a"]
    assert sentences_at(times, 99.0, radius=0) == ["d"]
    issue = {"ref": {"target": "video", "t": "0:10", "sentence_ids": ["5", "6"]}}
    assert with_sentences_from_time(issue, times, 10.0)["ref"]["sentence_ids"] == ["b", "c", "d"]
    assert with_sentences_from_time({"ref": {"target": "script"}}, times, 10.0) == {"ref": {"target": "script"}}
    assert with_sentences_from_time(issue, [], 10.0) is issue


def test_schema_takes_the_new_fields_and_checks_max_items() -> None:
    issue = {"ref": {"target": "script", "sentence_ids": ["s1.1"], "scope": "global", "why_global": "x"},
             "category": "content", "severity": "med", "problem": "p", "fix": "f", "evidence": "e",
             "caused_by": "deck", "claim_change": True, "affected_slides": ["s1"]}
    out = {"role": "director", "score": 5, "rubric": {}, "issues": [issue], "verdict": "v"}
    assert validate(out, schema_for("script_structure", "pro")) == []
    assert validate([1, 2, 3], {"type": "array", "maxItems": 2}) == ["$: 3 items > 2"]
