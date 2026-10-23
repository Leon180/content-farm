"""Story-tension work after chipcat run1/run2 and cel run1 (Leon 2026-10-23): audience / writer threshold calibration
arithmetic, the narrative spine requested while the article is written, the quantity-word rule, and a fresh set of
article rounds after a structure rewrite."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from content_farm.production import panel_flow
from content_farm.review import calibrate as cal
from content_farm.review.brief import article_brief
from content_farm.review.client import Call, CallResult
from content_farm.review.config import load_review
from content_farm.review.story_spine import (CHARS_PER_BEAT, SPINE_FILE, check_quantifiers, check_spine)

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


# ── calibration arithmetic ───────────────────────────────────────────────────────────────────

LISTING = "# t\n\n## s\n[s01.1] ~0:00 第一句。\n[s01.2] ~0:02 第二句比較長一點。\n[s02.1] ~0:05 第三句。\n"


def test_listing_sentences_give_the_leave_share_the_judge_uses() -> None:
    sentences = cal.sentences_from_listing(LISTING)
    assert [s.id for s in sentences] == ["s01.1", "s01.2", "s02.1"]
    stay = cal.leave_share({"left_at_sentence": None}, sentences)
    left = cal.leave_share({"left_at_sentence": "s01.2"}, sentences)
    assert stay == 1.0 and 0 < left < 0.5
    assert cal.leave_share(None, sentences) is None


def test_the_opus_threshold_is_converted_by_the_mean_gap_and_never_below_the_floor() -> None:
    result = cal.convert_threshold(0.50, [0.04, 0.06, 0.08])
    assert result["gap_mean"] == 0.06 and result["threshold"] == 0.44 and result["n"] == 3
    low, high = result["sonnet_equivalent_ci90"]
    assert low <= result["sonnet_equivalent"] <= high
    assert cal.convert_threshold(0.50, [0.30, 0.32])["threshold"] == cal.LEAVE_FLOOR      # 0.19 → floor 0.35


def test_per_draft_gap_uses_the_median_of_the_paired_seats() -> None:
    pairs = [cal.PairedSeat("d", f"v{i}", s, o) for i, (s, o) in enumerate([(0.1, 0.2), (0.3, 0.5), (0.5, 0.5)])]
    assert cal.draft_gaps(pairs) == {"d": {"sonnet": 0.3, "opus": 0.5, "gap": 0.2, "seats": 3}}


def test_writer_bias_is_systematic_only_when_the_interval_excludes_zero() -> None:
    biased = cal.score_bias([("a", 6.0, 6.8), ("b", 6.0, 7.0), ("c", 6.0, 6.6), ("d", 6.8, 7.0)])
    assert biased["systematic"] and biased["mean_gap"] > 0
    mixed = cal.score_bias([("a", 6.0, 6.8), ("b", 7.0, 6.2), ("c", 6.5, 6.5), ("d", 6.0, 6.0)])
    assert not mixed["systematic"]
    assert cal.score_bias([]) == {"n": 0, "systematic": False}


def test_review_thresholds_follow_the_calibration() -> None:
    config = load_review()
    for stage in ("script_structure", "final", "shorts_script", "shorts_final"):
        assert config.stages[stage].threshold.leave_median_pct == 0.35
    assert config.stages["script_structure"].threshold.writer_min == 6.0


# ── quantity words ───────────────────────────────────────────────────────────────────────────

def test_a_quantity_word_must_match_the_listed_items() -> None:
    wrong = "法規把產品分成七類：醫材、藥品、食品、化妝品、玩具、電器 [src:a]。\n"
    problems = check_quantifiers(wrong)
    assert len(problems) == 1 and "七類" in problems[0] and "6 items" in problems[0]
    assert check_quantifiers("法規把產品分成六類：醫材、藥品、食品、化妝品、玩具、電器 [src:a]。\n") == []
    assert check_quantifiers("分成三類：醫材、藥品和食品。\n") == []                  # last item joined by 和
    assert check_quantifiers("共 7 類：醫材、藥品。\n") != []                         # digits count too
    assert check_quantifiers("他看了三類資料，覺得很多。\n") == []                    # no list: nothing to compare


# ── narrative spine ──────────────────────────────────────────────────────────────────────────

def _article(sections: dict[str, int]) -> str:
    return "\n".join(f"## 標題 {{#{anchor}}}\n" + "字" * size for anchor, size in sections.items()) + "\n"


def _spine(beats: list[tuple[str, str]], **over) -> dict:
    return {"hook": "為什麼 0.7 奈米不是尺寸", "through_line": "IBM 新聞稿自己打臉標題", "payoff": "回到那把卡住的尺",
            "beats": [{"section": s, "turn": t} for s, t in beats], **over}


def test_a_spine_that_fits_the_article_passes() -> None:
    article = _article({"a-hook": 400, "a-timeline": 500, "a-chain": 400})
    spine = _spine([("a-hook", "新聞稿自己打臉"), ("a-timeline", "數字離開尺寸那一年"), ("a-chain", "誰在用這個名字")])
    assert check_spine(spine, article) == []


def test_a_spine_without_hook_or_beats_for_a_long_section_is_refused() -> None:
    article = _article({"a-hook": 600, "a-timeline": 1800})
    problems = check_spine(_spine([("a-hook", "新聞稿自己打臉")], hook=""), article)
    text = "；".join(problems)
    assert "hook" in text and "no beat" in text and f"{CHARS_PER_BEAT}" in text
    assert "unknown section" in "；".join(check_spine(_spine([("a-nowhere", "不存在的章節轉折")]), article))
    assert check_spine([], article) == [f"{SPINE_FILE} must be a JSON object"]


def test_check_article_main_requires_the_spine_only_when_asked(tmp_path: Path, capsys) -> None:
    import check_article

    (tmp_path / "article.md").write_text("x", encoding="utf-8")
    (tmp_path / "sources.json").write_text("[]", encoding="utf-8")
    check_article.main(["--run-dir", str(tmp_path)])
    assert SPINE_FILE not in capsys.readouterr().err
    check_article.main(["--run-dir", str(tmp_path), "--require-spine"])
    assert SPINE_FILE in capsys.readouterr().err
    (tmp_path / SPINE_FILE).write_text(json.dumps(_spine([])), encoding="utf-8")        # present → checked without the flag
    check_article.main(["--run-dir", str(tmp_path)])
    assert "beats" in capsys.readouterr().err


# ── the briefs ───────────────────────────────────────────────────────────────────────────────

def test_article_brief_carries_spine_rubric_and_quantity_rule() -> None:
    text = article_brief(load_review())
    for needle in ("開場鉤子", "貫穿", "60–90 秒", SPINE_FILE, "留人點密度", "合成觀眾離開時間中位數 ≥ 片長 35%", "數量詞前後一致"):
        assert needle in text


APPROVED = "# t\n台積電 2022 年底量產 3 奈米製程 [src:a]。\n換算起來，成本不低。\n"


def _produce(tmp_path: Path, gate: str, plan_step_fixes: list[dict]) -> str:
    from content_farm.review.producers import produce

    (tmp_path / "review").mkdir(exist_ok=True)
    plan = {"round": 1, "reasons": ["x"], "steps": {"article": {"fixes": plan_step_fixes}}}
    (tmp_path / "review" / f"{gate}.fixes.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    seen: list[str] = []

    def agent(call: Call) -> CallResult:
        seen.append(call.prompt)
        return CallResult(call.rid, True, {"files": [], "summary": "ok"}, (), call.model, call.effort, ())

    produce("article", tmp_path, channel="chipcat", config=load_review(), python="/py", client=agent, gate=gate)
    return seen[0]


STORY_FIX = {"problem": "名詞表堆疊", "fix": "重構", "category": "story", "ref": {"target": "script", "scope": "global"},
             "scope": {"sentence_ids": [], "titles": [], "thumbnail": False, "description": False}}
FACT_FIX = {"problem": "來源沒有這個數字", "fix": "刪掉", "category": "fact", "who": "fact_checker-1", "ref": {},
            "scope": {"sentence_ids": [], "titles": [], "thumbnail": False, "description": False}}


def test_first_draft_and_structure_rewrite_get_the_spine_but_a_fact_fix_does_not(tmp_path: Path) -> None:
    from content_farm.review.producers import produce

    drafts: list[str] = []
    produce("article", tmp_path, channel="chipcat", config=load_review(), python="/py", gate="article",
            client=lambda c: drafts.append(c.prompt) or CallResult(c.rid, True, {"files": [], "summary": "ok"}, (), c.model, c.effort, ()))
    assert "敘事骨架" in drafts[0] and "--require-spine" in drafts[0]
    structure = _produce(tmp_path, "deck", [STORY_FIX])
    assert "敘事骨架" in structure and "數量詞前後一致" in structure and "--require-spine" in structure
    (tmp_path / "fact").mkdir()
    fact = _produce(tmp_path / "fact", "article", [FACT_FIX])
    assert "敘事骨架" not in fact and "只依下面的修改清單" in fact


# ── a structure rewrite is a new piece of content: fresh article rounds ──────────────────────

def test_an_accepted_structure_rewrite_moves_the_spent_article_rounds_aside(tmp_path: Path) -> None:
    (tmp_path / "review" / "article").mkdir(parents=True)
    for n in (1, 2, 3):
        (tmp_path / "review" / "article" / f"round-{n}").mkdir()
    (tmp_path / "article.md").write_text(APPROVED, encoding="utf-8")
    guard = panel_flow._StructuralArticle(tmp_path, tmp_path / "article.md", APPROVED)
    guard.accept({"rewrite_reason": "加鉤子與主線"})
    root = tmp_path / "review" / "article"
    assert not list(root.glob("round-*")) and (root / "cycle-1" / "round-3").is_dir()
    log = json.loads((tmp_path / "review" / "new_cycle.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert log["stages"] == {"article": "cycle-1"} and "結構改寫" in log["reason"]
    assert (tmp_path / "review" / "article.locked.md").is_file()      # the fact lock still limits the next check to new sentences


def test_the_next_article_round_after_a_structure_rewrite_is_round_one(tmp_path: Path) -> None:
    from content_farm.review.rounds import rounds_of

    (tmp_path / "review" / "article" / "round-3").mkdir(parents=True)
    panel_flow.new_stage_cycle(tmp_path, ("article",), reason=panel_flow.STRUCTURE_REWRITE_CYCLE_REASON)
    assert [p.name for p in rounds_of(tmp_path, "article") if p.name.startswith("round-")] == []


# ── yokai drops the frog clerk (Leon 2026-10-23) ────────────────────────────────────────────

def test_yokai_without_a_mascot_skips_the_overlay_the_share_rule_and_the_brief_line() -> None:
    from content_farm.explainer.pngtuber.profiles import PROFILES
    from content_farm.production.channel_rules import mascot_findings
    from content_farm.production.channels import load_channel
    from content_farm.production.steps import step_names
    from content_farm.review.brief import channel_rules_text
    from content_farm.explainer.deck import Deck
    from tests.unit.explainer_helpers import deck_dict

    yokai, chipcat = load_channel("yokai"), load_channel("chipcat")
    assert not yokai.mascot.rig_ready and "mascot" not in step_names(yokai)
    assert "mascot" in step_names(chipcat)
    deck = Deck.model_validate(deck_dict())
    assert not any(slide.mascot for slide in deck.slides)
    assert mascot_findings(yokai, deck) == []                                  # no share rule for yokai
    assert "青蛙書記" not in channel_rules_text("yokai")
    # kept for later: the pack and the frog motion profile
    assert (REPO / "src/content_farm/explainer/pngtuber/packs/frog-scribe").is_dir() and "frog" in PROFILES
    assert yokai.mascot.ref == "pngtuber/frog-scribe" and yokai.mascot.motion_profile == "frog"


def test_yokai_thumbnail_no_longer_needs_the_character(tmp_path: Path, monkeypatch) -> None:
    from content_farm.production import thumbnail
    from content_farm.production.channels import load_channel

    spec = SimpleNamespace(visual=SimpleNamespace(kind="object"), text="t")
    monkeypatch.setattr(thumbnail, "load_spec", lambda run_dir: spec)
    monkeypatch.setattr(thumbnail, "promise_findings", lambda run_dir, s, label="": [])
    (tmp_path / thumbnail.SPEC_FILE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / thumbnail.OUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / thumbnail.SPEC_FILE).write_text("{}", encoding="utf-8")
    (tmp_path / thumbnail.OUT_FILE).write_text("x", encoding="utf-8")
    yokai = thumbnail.thumbnail_findings(tmp_path, load_channel("yokai"))
    assert not [f for f in yokai if "must be on the thumbnail" in f.message]
    chipcat = thumbnail.thumbnail_findings(tmp_path, load_channel("chipcat"))
    assert [f for f in chipcat if "must be on the thumbnail" in f.message]
