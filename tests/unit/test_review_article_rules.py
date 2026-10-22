"""Article fact-check rules (Leon 2026-10-18 decision 59fdefb32bd7 = D): from round 2 a rewrite may
only delete or edit flagged sentences (checked by diff); two fact-checkers who disagree get a third
(opus · high) arbiter whose ruling decides; agreed errors count directly; threshold stays 0."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from content_farm.production import panel_flow
from content_farm.review import arbitration as arb
from content_farm.review.article_diff import check_rework, flagged_sentences, split_article
from content_farm.review.client import Call, CallResult
from content_farm.review.config import load_review
from content_farm.review.gate import enforce, panel_gate
from content_farm.review.schemas import validate

CONFIG = load_review()
ARTICLE = """# 標題

CoWoS 產能 2026 年底每月 13 萬片。摩根士丹利估 2028 年底每月 26 萬片。

台積電 2016 年說量太小。這是一句沒人點名的話。
"""


# ── delete-or-edit-only ─────────────────────────────────────────────────────────────────────────

def _flagged(*quotes: str) -> set[str]:
    return flagged_sentences(list(quotes), split_article(ARTICLE))


def test_split_and_quote_lookup():
    ids = {s.id: s.text for s in split_article(ARTICLE)}
    assert ids["p2.2"] == "摩根士丹利估 2028 年底每月 26 萬片。"
    assert _flagged("摩根士丹利估 2028 年底") == {"p2.2"}
    assert _flagged("13 萬片。摩根士丹利") == {"p2.1", "p2.2"}          # a quote across two sentences
    assert _flagged("文章裡沒有這句") == set()


def test_added_qualifier_and_corrected_attribution_pass():
    after = ARTICLE.replace("摩根士丹利估 2028 年底每月 26 萬片。", "據經濟日報報導，2028 年底估計每月 26 萬片。")
    assert check_rework(ARTICLE, after, _flagged("摩根士丹利估 2028 年底")) == []


def test_deleting_a_flagged_sentence_passes():
    after = ARTICLE.replace("摩根士丹利估 2028 年底每月 26 萬片。", "")
    assert check_rework(ARTICLE, after, _flagged("摩根士丹利估")) == []


def test_new_sentence_in_round_two_is_refused():
    after = ARTICLE.replace("這是一句沒人點名的話。", "這是一句沒人點名的話。蘋果也跑去小廠當品管。")
    problems = check_rework(ARTICLE, after, _flagged("摩根士丹利估"))
    assert any("新增句子" in p and "蘋果" in p for p in problems)
    split = ARTICLE.replace("摩根士丹利估 2028 年底每月 26 萬片。", "據報導 2028 年底每月 26 萬片。來源是經濟日報。")
    assert any("新增句子" in p for p in check_rework(ARTICLE, split, _flagged("摩根士丹利估")))


def test_unflagged_or_rewritten_sentences_are_refused():
    touched = ARTICLE.replace("這是一句沒人點名的話。", "這句被偷改了。")
    assert any("沒有被點名" in p for p in check_rework(ARTICLE, touched, _flagged("摩根士丹利估")))
    rewritten = ARTICLE.replace("摩根士丹利估 2028 年底每月 26 萬片。", "封裝產能的未來充滿變數，誰也說不準。")
    assert any("改寫幅度太大" in p for p in check_rework(ARTICLE, rewritten, _flagged("摩根士丹利估")))


# ── arbitration ─────────────────────────────────────────────────────────────────────────────────

def _claim(status: str, evidence: str, claim: str = "c") -> dict:
    return {"claim": claim, "status": status, "evidence": evidence, "note": f"{status} 的理由", "source_id": "s1",
            "source_quote": "原文"}


def _fact(*claims: dict) -> dict:
    return {"role": "fact_checker", "claims": list(claims), "issues": [], "verdict": ""}


def test_agreement_is_not_arbitrated_and_disagreement_is():
    sentences = split_article(ARTICLE)
    both = arb.split({"fact_checker-1": _fact(_claim("wrong", "摩根士丹利估")),
                      "fact_checker-2": _fact(_claim("unsourced", "2028 年底每月 26 萬片"))}, sentences)
    assert both == {"agreed": ["fact_checker-1#0"], "disputes": []}
    one = arb.split({"fact_checker-1": _fact(_claim("wrong", "摩根士丹利估")),
                     "fact_checker-2": _fact(_claim("ok", "摩根士丹利估 2028"))}, sentences)
    assert one["agreed"] == [] and [d["item"] for d in one["disputes"]] == ["fact_checker-1#0"]
    assert one["disputes"][0]["other_claims"][0]["status"] == "ok"        # the arbiter sees the other side
    unlisted = arb.split({"fact_checker-1": _fact(), "fact_checker-2": _fact(_claim("unsourced", "量太小"))}, sentences)
    assert [d["item"] for d in unlisted["disputes"]] == ["fact_checker-2#0"]


class ArticlePanel:
    """fact_checker-N answers ``checks[N]``; the arbiter answers ``rulings``; the writer scores 8."""

    def __init__(self, checks: dict[str, dict], rulings: dict[str, str] | None = None):
        self.checks, self.rulings, self.calls = checks, rulings or {}, []

    def __call__(self, call: Call) -> CallResult:
        self.calls.append(call)
        if call.rid.startswith("fact_checker"):
            out = self.checks[call.rid]
        elif call.rid.startswith(arb.ARBITER_ROLE):
            assert "fact_checker" in call.prompt and "的判定" in call.prompt     # both sides' reasons
            out = {"rulings": [{"item": k, "status": v, "note": "查過"} for k, v in self.rulings.items()]}
        else:
            out = {"role": "writer_story", "score": 8, "rubric": {}, "issues": [], "verdict": ""}
        assert validate(out, call.schema) == []
        return CallResult(call.rid, True, out, (), call.model, call.effort, (f"claude-{call.model}-5-5",), 1.0)


def _article_run(tmp_path: Path) -> Path:
    (tmp_path / "article.md").write_text(ARTICLE, encoding="utf-8")
    (tmp_path / "sources.json").write_text('{"sources": [{"id": "s1", "url": "https://example.com"}]}', encoding="utf-8")
    return tmp_path


def _gate(run_dir: Path, panel: ArticlePanel):
    return panel_gate(run_dir, gate="article", stage_name="article", config=CONFIG, channel="chipcat",
                      channel_name="晶片貓", client=panel)


DISPUTED = {"fact_checker-1": _fact(_claim("wrong", "摩根士丹利估 2028 年底每月 26 萬片", "摩根士丹利估 26 萬")),
            "fact_checker-2": _fact(_claim("ok", "摩根士丹利估 2028 年底每月 26 萬片"))}


def test_arbiter_overturns_a_lone_error_and_the_gate_opens(tmp_path):
    panel = ArticlePanel(DISPUTED, rulings={"fact_checker-1#0": "ok"})
    result = _gate(_article_run(tmp_path), panel)
    assert result.status == "pass", result.message
    arbiters = [c for c in panel.calls if c.rid.startswith(arb.ARBITER_ROLE)]
    assert len(arbiters) == 1 and (arbiters[0].model, arbiters[0].effort) == ("sonnet", "medium")
    assert "WebFetch" in arbiters[0].tools
    assert result.scores["confirmed_errors"] == 0 and result.scores["disputes"] == 1


def test_arbiter_upholds_a_lone_error_and_it_counts(tmp_path):
    result = _gate(_article_run(tmp_path), ArticlePanel(DISPUTED, rulings={"fact_checker-1#0": "wrong"}))
    assert result.status == "rework" and result.scores["confirmed_errors"] == 1
    fixes = json.loads((tmp_path / "review" / "article.fixes.json").read_text(encoding="utf-8"))
    assert [f["who"] for f in fixes["steps"]["article"]["fixes"] if f["category"] == "fact"] == ["fact_checker-1"]


def test_unanswered_dispute_counts_as_an_error(tmp_path):
    result = _gate(_article_run(tmp_path), ArticlePanel(DISPUTED, rulings={}))
    assert result.status == "rework" and result.scores["unanswered"] == 1


def test_agreed_errors_count_without_an_arbiter(tmp_path):
    both = {"fact_checker-1": _fact(_claim("wrong", "摩根士丹利估")),
            "fact_checker-2": _fact(_claim("wrong", "2028 年底每月 26 萬片"))}
    panel = ArticlePanel(both)
    result = _gate(_article_run(tmp_path), panel)
    assert result.status == "rework" and result.scores["agreed"] == 1 and result.scores["confirmed_errors"] == 1
    assert not any(c.rid.startswith(arb.ARBITER_ROLE) for c in panel.calls)


def test_enforce_refuses_disputes_without_a_valid_arbiter(tmp_path):
    _gate(_article_run(tmp_path), ArticlePanel(DISPUTED, rulings={"fact_checker-1#0": "ok"}))
    card = json.loads((tmp_path / "review" / "article" / "round-1" / "scorecard.json").read_text(encoding="utf-8"))
    current = card["inputs"]
    assert enforce(card, CONFIG, "article", current) == []
    stripped = {**card, "seats": [s for s in card["seats"] if s["role"] != arb.ARBITER_ROLE]}
    assert any("no arbiter seat" in p for p in enforce(stripped, CONFIG, "article", current))
    weak = {**card, "seats": [{**s, "model": "haiku"} if s["role"] == arb.ARBITER_ROLE else s for s in card["seats"]]}
    assert any("fact_arbiter-1: ran haiku" in p for p in enforce(weak, CONFIG, "article", current))


def test_third_round_is_the_last(tmp_path):
    run_dir = _article_run(tmp_path)
    for n in range(3):
        (run_dir / "article.md").write_text(ARTICLE + f"\n版本 {n}。\n", encoding="utf-8")
        result = _gate(run_dir, ArticlePanel(DISPUTED, rulings={"fact_checker-1#0": "wrong"}))
    assert result.status == "exhausted" and "第 3 輪" in result.message


# ── the producer side: a rewrite that adds sentences is refused, restored and redone ───────────

def _rework_run(tmp_path: Path) -> Path:
    run_dir = _article_run(tmp_path)
    (run_dir / "review").mkdir()
    plan = {"round": 1, "reasons": ["x"], "steps": {"article": {"fixes": [
        {"problem": "wrong：摩根士丹利", "fix": "改成經濟日報", "category": "fact", "who": "fact_checker-1",
         "evidence": "摩根士丹利估 2028 年底每月 26 萬片", "ref": {},
         "scope": {"sentence_ids": [], "titles": [], "thumbnail": False, "description": False}}]}}}
    (run_dir / "review" / "article.fixes.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return run_dir


def _ctx(run_dir: Path, writes: list[str]):
    prompts = []

    def agent(call: Call) -> CallResult:
        prompts.append(call.prompt)
        (run_dir / "article.md").write_text(writes[len(prompts) - 1], encoding="utf-8")
        return CallResult(call.rid, True, {"files": ["article.md"], "summary": "ok"}, (), call.model, call.effort,
                          ("claude-opus-5-5",))
    options = SimpleNamespace(review_tier=None, python="/py", review_client=agent)
    return SimpleNamespace(run_dir=run_dir, channel=SimpleNamespace(code="chipcat"), options=options), prompts


GOOD = ARTICLE.replace("摩根士丹利估", "據經濟日報報導，估計")
BAD = ARTICLE.replace("這是一句沒人點名的話。", "這是一句沒人點名的話。新加的一句。")


def test_refused_rewrite_is_restored_and_redone(tmp_path):
    run_dir = _rework_run(tmp_path)
    ctx, prompts = _ctx(run_dir, [BAD, GOOD])
    assert panel_flow.run_producer(ctx, "article", lambda _: None) is None
    assert (run_dir / "article.md").read_text(encoding="utf-8") == GOOD
    assert len(prompts) == 2 and "只准刪改" in prompts[0] and "被拒收" in prompts[1] and "新加的一句" in prompts[1]
    assert (run_dir / "review" / "article.before-article-round-2.md").read_text(encoding="utf-8") == ARTICLE


def test_rewrite_refused_twice_stops_with_the_original(tmp_path):
    run_dir = _rework_run(tmp_path)
    ctx, _ = _ctx(run_dir, [BAD, BAD])
    failure = panel_flow.run_producer(ctx, "article", lambda _: None)
    assert failure is not None and "不是只刪改" in failure
    assert (run_dir / "article.md").read_text(encoding="utf-8") == ARTICLE


def test_first_draft_is_not_guarded(tmp_path):
    (tmp_path / "review").mkdir()
    ctx, prompts = _ctx(tmp_path, [BAD])
    assert panel_flow.run_producer(ctx, "article", lambda _: None) is None and len(prompts) == 1
