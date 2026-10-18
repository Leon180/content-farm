"""Stage threshold judgements (review/verdicts.py)."""

from __future__ import annotations

from content_farm.review.config import load_review
from content_farm.review.sentences import Sentence
from content_farm.review.verdicts import JUDGES, Seat, verify_issue

CONFIG = load_review()
SENTENCES = [Sentence(f"s1.{n}", "s1", "開場", "一二三四五六七八九十", False) for n in range(1, 5)] + \
            [Sentence(f"s2.{n}", "s2", "結論", "一二三四五六七八九十", False) for n in range(1, 5)]


def seat(rid, role, kind, output, ok=True, holdout=False):
    return Seat(rid, role, kind, holdout, ok, output)


def issue(sentence_ids=("s1.1",), evidence="一二三四", caused_by="deck", **extra):
    return {"ref": {"target": "script", "sentence_ids": list(sentence_ids)}, "category": "content", "severity": "med",
            "problem": "p", "fix": "f", "evidence": evidence, "caused_by": caused_by, **extra}


def script_panel(left=("s2.1", "s2.2", None, "s2.3"), writers=(8, 7), fact_status="ok", holdout_left="s1.1"):
    seats = [seat(f"viewer-{n}", "viewer", "viewer", {"left_at_sentence": sid, "top_fixes": [issue()]})
             for n, sid in enumerate(left)]
    seats.append(seat("viewer-teacher", "viewer", "viewer", {"left_at_sentence": holdout_left,
                                                             "top_fixes": [issue(evidence="holdout only")]},
                      holdout=True))
    seats += [seat("writer_story-1", "writer_story", "pro", {"score": writers[0], "issues": []}),
              seat("writer_density-1", "writer_density", "pro", {"score": writers[1], "issues": []}),
              seat("director-1", "director", "pro", {"score": 6, "issues": []}),
              seat("fact_checker-1", "fact_checker", "fact",
                   {"claims": [{"claim": "c", "status": fact_status, "evidence": "一二三四", "sentence_ids": ["s1.2"],
                                "note": "n"}], "issues": []})]
    return seats


def judge(name, seats, **context):
    return JUDGES[name](CONFIG.stages[name], seats, **context)


def test_script_passes_at_thresholds():
    verdict = judge("script", script_panel(), sentences=SENTENCES, corpus="一二三四五六七八九十")
    assert verdict.passed, verdict.reasons
    assert verdict.scores["leave_median_pct"] == 0.688
    assert verdict.scores["holdout_leave"] == [0.0]          # reported, not judged


def test_script_fails_on_leave_writer_and_fact():
    verdict = judge("script", script_panel(left=("s1.1", "s1.2", "s1.3", None), writers=(6.5, 9),
                                           fact_status="wrong"), sentences=SENTENCES, corpus="一二三四")
    assert not verdict.passed
    text = " ".join(verdict.reasons)
    assert "觀眾離開中位" in text and "writer_story-1 6.5/10 < 7" in text and "fact_checker-1 找到 1 個事實錯誤" in text


def test_missing_seat_blocks():
    seats = script_panel()
    seats[-1] = seat("fact_checker-1", "fact_checker", "fact", None, ok=False)
    verdict = judge("script", seats, sentences=SENTENCES, corpus="一二三四")
    assert not verdict.passed and "fact_checker-1" in verdict.reasons[0]


def test_holdout_issues_never_feed_fixes():
    verdict = judge("script", script_panel(), sentences=SENTENCES, corpus="一二三四 holdout only")
    assert all(i["who"] != "viewer-teacher" for i in verdict.issues)


def test_unverifiable_issues_are_dropped():
    context = {"corpus": "一二三四", "sentence_ids": {"s1.1"}, "items": set(), "duration": 0}
    assert verify_issue(issue(), **context) == ""
    assert "unknown sentence" in verify_issue(issue(sentence_ids=("s9.9",)), **context)
    assert "not found" in verify_issue(issue(evidence="完全沒出現的話"), **context)
    video = {"ref": {"target": "video", "t": "9:59"}, "evidence": "x"}
    assert "not in the video" in verify_issue(video, **{**context, "duration": 120})
    assert verify_issue({"ref": {"target": "video", "t": "1:30"}}, **{**context, "duration": 120}) == ""


def test_article_needs_both_checkers_clean():
    clean = {"claims": [{"claim": "a", "status": "ok", "evidence": "x", "note": ""}], "issues": []}
    dirty = {"claims": [{"claim": "b", "status": "unsourced", "evidence": "文章原句", "note": ""}], "issues": []}
    writer = seat("writer_story-1", "writer_story", "pro", {"score": 7, "issues": []})
    ok = judge("article", [seat("fact_checker-1", "fact_checker", "fact", clean),
                           seat("fact_checker-2", "fact_checker", "fact", clean), writer], corpus="文章原句")
    assert ok.passed
    bad = judge("article", [seat("fact_checker-1", "fact_checker", "fact", clean),
                            seat("fact_checker-2", "fact_checker", "fact", dirty), writer], corpus="文章原句")
    assert not bad.passed and bad.issues and bad.issues[0]["caused_by"] == "article"


def test_labelled_own_analysis_is_not_an_error_but_unlabelled_inference_is():
    analysis = {"claims": [{"claim": "換算起來每公尺 2.8 微米", "status": "analysis", "evidence": "x", "note": "算式正確"}],
                "issues": []}
    inference = {"claims": [{"claim": "前任的謹慎左右了開工時機", "status": "unsourced", "evidence": "x",
                             "note": "寫成事實"}], "issues": []}
    writer = seat("writer_story-1", "writer_story", "pro", {"score": 7, "issues": []})
    ok = judge("article", [seat("fact_checker-1", "fact_checker", "fact", analysis),
                           seat("fact_checker-2", "fact_checker", "fact", analysis), writer], corpus="x")
    assert ok.passed
    bad = judge("article", [seat("fact_checker-1", "fact_checker", "fact", analysis),
                            seat("fact_checker-2", "fact_checker", "fact", inference), writer], corpus="x")
    assert not bad.passed


def test_topic_ranks_and_vetoes():
    viewers = [seat(f"viewer-{n}", "viewer", "viewer", {"picks": [{"candidate_id": "t1", "click": 9, "why": ""},
                                                                  {"candidate_id": "t2", "click": 8, "why": ""}]})
               for n in range(3)]
    pros = [seat("writer_story-1", "writer_story", "pro", {"scores": [
                {"candidate_id": "t1", "score": 9, "why": "", "veto": False},
                {"candidate_id": "t2", "score": 7, "why": "", "veto": False}]}),
            seat("producer-1", "producer", "producer", {"scores": [
                {"candidate_id": "t1", "score": 9, "why": "", "veto": True},
                {"candidate_id": "t2", "score": 7, "why": "", "veto": False}]})]
    verdict = judge("topic", viewers + pros, candidate_ids=["t1", "t2"])
    assert verdict.passed and verdict.extra["chosen"] == ["t2"]
    short = judge("topic", viewers + pros, candidate_ids=["t1", "t2"], short=True)
    assert not short.passed and "需要 3" in short.reasons[0]


def _title_viewer(n, noticed, picked):
    return seat(f"viewer-{n}", "viewer", "viewer", {
        "homepage": [{"feed": f"feeds/viewer-{n}_feed1.jpg", "noticed": noticed, "picked": picked, "why": ""}],
        "titles": [{"title_id": "T1", "click": 7}, {"title_id": "T2", "click": 8}], "thumbnails": {"A": 6},
        "top_fixes": []})


def test_title_thumb_homepage_auto_and_producer():
    keys = {f"viewer-{n}_feed1.jpg": {"variant": "A", "ours_card": 4, "cards": 12} for n in range(5)}
    viewers = [_title_viewer(n, [4, 1, 2], 4) for n in range(5)]
    designer = seat("designer-1", "designer", "designer", {"score": 7, "variants": {"A": 7}, "issues": []})
    honest = seat("producer-1", "producer", "producer", {"checks": [{"item": "T2", "exaggerated": False,
                                                                     "consistent": True, "why": ""}], "issues": []})
    verdict = judge("title_thumb", [*viewers, designer, honest], keys=keys, auto={"A": []})
    assert verdict.passed, verdict.reasons
    assert verdict.scores["best_title"] == "T2"
    hype = seat("producer-1", "producer", "producer", {"checks": [{"item": "T2", "exaggerated": True,
                                                                   "consistent": True, "why": "誇大"}], "issues": []})
    verdict = judge("title_thumb", [*viewers, designer, hype], keys=keys, auto={"A": ["對比 3.9"]})
    assert not verdict.passed and verdict.scores["best_title"] == "T1"
    assert any("自動檢查" in r for r in verdict.reasons) and any("誇大" in r for r in verdict.reasons)
    unseen = [_title_viewer(n, [1, 2, 3], 1) for n in range(5)]
    verdict = judge("title_thumb", [*unseen, designer, honest], keys=keys, auto={})
    assert any("被注意名次" in r for r in verdict.reasons) and any("被選比例" in r for r in verdict.reasons)


def test_feed_names_match_loosely_but_only_within_the_viewer():
    from content_farm.review.verdicts import feed_key

    keys = {"viewer-a_feed1.jpg": {"v": "A"}, "viewer-b_feed1.jpg": {"v": "B"}}
    assert feed_key("viewer-a", "feeds/viewer-a_feed1.jpg", keys) == {"v": "A"}
    assert feed_key("viewer-a", "viewer-a_feed1", keys) == {"v": "A"}
    assert feed_key("viewer-b", "feed1", keys) == {"v": "B"}
    assert feed_key("viewer-a", "feed9", keys) is None


def test_media_compliance_and_pending():
    good = seat("compliance-1", "compliance", "compliance", {"assets": [
        {"asset": "s03", "logo": False, "real_person": False, "official_character": False, "license_ok": True,
         "note": ""}], "issues": []})
    assert judge("media", [good], pending=[]).passed
    logo = seat("compliance-1", "compliance", "compliance", {"assets": [
        {"asset": "s03", "logo": True, "real_person": False, "official_character": False, "license_ok": True,
         "note": "logo"}], "issues": []})
    verdict = judge("media", [logo], pending=[{"slide_id": "s05"}])
    assert not verdict.passed and verdict.extra["rework_assets"] == ["s03"] and len(verdict.reasons) == 2


def test_final_objective_and_thumbnail_consistency():
    viewers = [seat(f"viewer-{n}", "viewer", "viewer", {"left_at": left, "thumbnail_matches": n != 0,
                                                        "pronunciation": [], "top_fixes": []})
               for n, left in enumerate(("4:00", "5:00", None, "6:00"))]
    pros = [seat(f"{r}-1", r, "pro", {"score": 7, "issues": []}) for r in ("editor_visual", "editor_audio", "director")]
    green = {"visual": {"light": "green"}, "audio": {"light": "green"}, "content": {"light": "yellow"}}
    assert judge("final", viewers + pros, duration=600, columns=green).passed
    red = {**green, "audio": {"light": "red"}}
    verdict = judge("final", viewers + pros, duration=600, columns=red)
    assert not verdict.passed and "audio" in verdict.reasons[0]
