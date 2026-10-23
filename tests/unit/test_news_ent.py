"""娛樂快報 (ent): source whitelist, forbidden topics, sourced-claim audit with its one auto-fix, selection guard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.production.channels import load_all, load_channel
from content_farm.production.news import audit_step, claims, daily, feeds, guard, select
from content_farm.production.news import script as ns
from content_farm.production.news.models import Candidate, Discussion, Ranked, Read
from content_farm.production.news.series import branding_for, news_series
from content_farm.review.client import CallResult

PAGE = ("自由時報報導，歌手小明今天在社群宣布，年底將在台北小巨蛋舉辦兩場演唱會。"
        "他的經紀公司對媒體表示，首場售票時間訂在下週三中午十二點。"
        "網傳他正在籌備電影演出，但經紀公司尚未回應。這是他出道十週年的第一場大型演出。")
URL = "https://ent.ltn.com.tw/news/breakingnews/1"
READ_AT = "2026-10-23T09:00:00+08:00"


@pytest.fixture(scope="module")
def series():
    return news_series(load_channel("ent"))


def _claim(sentence: str, evidence: str, status: str = "reported", by: str = "", source: str = URL) -> claims.Claim:
    return claims.Claim(sentence=sentence, source=source, status=status, evidence=evidence, confirmed_by=by)


def _beat(kind: str, narration: str, *cl: claims.Claim) -> ns.Beat:
    return ns.Beat(kind=kind, narration=narration, claims=cl, screen=ns.Screen(headline="標題"), term="")


GOOD = {
    "hook": _beat("hook", "據自由時報報導，歌手小明年底要開兩場演唱會。",
                  _claim("據自由時報報導，歌手小明年底要開兩場演唱會。", "年底將在台北小巨蛋舉辦兩場演唱會")),
    "what": _beat("what", "他在社群宣布，地點是台北小巨蛋。",
                  _claim("他在社群宣布，地點是台北小巨蛋。", "今天在社群宣布", "confirmed", "他")),
    "why": _beat("why", "據自由時報報導，這是他出道十週年的第一場大型演出。",
                 _claim("據自由時報報導，這是他出道十週年的第一場大型演出。", "出道十週年的第一場大型演出")),
    "analogy": _beat("analogy", "經紀公司表示首場售票訂在下週三中午十二點。",
                     _claim("經紀公司表示首場售票訂在下週三中午十二點。", "他的經紀公司對媒體表示，首場售票時間訂在下週三中午十二點", "confirmed", "經紀公司")),
    "take": _beat("take", "我覺得先等售票公告再決定要不要搶。"),
}


def _script(**override: ns.Beat) -> ns.NewsScript:
    beats = {**GOOD, **override}
    return ns.NewsScript(item_id="ltn-1", title="小明年底開唱", summary="歌手小明宣布年底在小巨蛋開兩場演唱會", importance=3,
                         sources=(ns.SourceRef(url=URL, title="小明宣布開唱", publisher="自由時報", read_at=READ_AT),),
                         beats=tuple(beats[k] for k in ns.BEAT_ORDER))


ITEM = {"read": {"ok": True, "url": URL, "final_url": URL}, "candidate": {"title": "小明宣布年底開唱", "domain": "ent.ltn.com.tw"}}


# ── config ────────────────────────────────────────────────────────────────────

def test_ent_channel_loads_with_whitelist_and_guardrail_switches(series) -> None:
    channel = load_channel("ent")
    assert channel.code in {c.code for c in load_all()}
    assert series.sources == ("rss",) and series.topic_guard and series.claims_audit and not series.analogy_required
    assert {f.id for f in series.feeds} >= {"cna", "ltn", "udn", "ettoday", "yahoo", "soompi", "variety", "deadline"}
    assert not any(channel.media.model_dump()[k] for k in ("stock", "ai_image", "artwork", "source_footage"))
    assert channel.mascot.rig_ready is False and series.dir_prefix == "ent"


def test_ent_branding_is_not_the_tech_defaults(series) -> None:
    brand = branding_for(load_channel("ent"))
    text = " ".join((brand.byline, brand.series_line, *brand.tags))
    assert "科技" not in text and "晶片貓" not in text
    assert brand.labels()["analogy"] == "各方說法" and brand.labels()["take"] == "快報點評"
    assert branding_for(load_channel("chipcat")) == ns.Branding()


def test_series_needs_rss_exactly_when_it_has_a_whitelist() -> None:
    with pytest.raises(ValueError, match="rss"):
        news_series(load_channel("ent")).model_validate({**news_series(load_channel("ent")).model_dump(), "feeds": ()})


# ── guard ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,category", [
    ("某童星未成年就出道", "未成年人"), ("藝人涉嫌性騷擾遭爆", "性醜聞細節"), ("資深演員病逝享壽70歲", "病情與死因"),
    ("網友起底女星住址", "私人住址與家人"), ("K-pop idol under-age drinking scandal", "未成年人"),
    ("Actor dies at 70", "病情與死因"), ("俳優 死去 94歳", "病情與死因"),
])
def test_forbidden_topics_are_blocked_in_three_languages(text: str, category: str) -> None:
    assert guard.blocked_reason(text).startswith(category)


def test_ordinary_entertainment_headlines_pass() -> None:
    for text in ("金曲獎入圍名單公布", "Netflix 影集宣布第二季", "新專輯本週發行，演唱會加開一場"):
        assert guard.blocked_reason(text) is None


def test_outlet_match_is_by_host_not_substring(series) -> None:
    assert series.outlet("https://ent.ltn.com.tw/news/x").id == "ltn"
    assert series.outlet("https://tw.news.yahoo.com/a").id == "yahoo"
    assert series.outlet("https://ltn.com.tw.evil.example/x") is None
    assert series.outlet("https://example.com/ltn.com.tw") is None
    assert series.outlet("https://www.dcard.tw/f/trending/p/1") is None


def _cand(i: int, url: str, title: str = "歌手宣布新專輯", summary: str = "") -> Candidate:
    return Candidate(id=f"c{i}", title=title, url=url, domain=guard.host_of(url), posted_at="2026-10-23T01:00:00+00:00",
                     discussions=(Discussion(site="rss", url="https://x/feed", rank=i),), summary=summary)


def test_admit_drops_off_list_and_forbidden_stories_before_ranking(series) -> None:
    pool = [_cand(1, "https://ent.ltn.com.tw/a"), _cand(2, "https://www.dcard.tw/b"),
            _cand(3, "https://udn.com/c", title="童星驚傳意外"), _cand(4, "https://udn.com/d", summary="疑似病情惡化住院")]
    kept, excluded = daily.admit(pool, series)
    assert [c.id for c in kept] == ["c1"]
    reasons = {e["id"]: e["why"] for e in excluded}
    assert reasons["c2"] == "不在來源白名單" and "未成年人" in reasons["c3"] and "病情與死因" in reasons["c4"]


def test_tech_channels_are_not_touched_by_admit() -> None:
    tech = news_series(load_channel("technews"))
    pool = [_cand(1, "https://example.com/a", title="童星 under-age")]
    assert daily.admit(pool, tech) == (pool, [])


# ── feeds ────────────────────────────────────────────────────────────────────

RSS = """<?xml version="1.0"?><rss version="2.0" xmlns:feedburner="http://rssnamespace.org/feedburner/ext/1.0"><channel>
<item><title>歌手宣布年底開唱</title><link>https://ent.ltn.com.tw/news/1</link><pubDate>Thu, 23 Oct 2026 01:00:00 +0000</pubDate>
<description>&lt;p&gt;小巨蛋兩場&lt;/p&gt;</description></item>
<item><title>轉載農場文</title><link>https://content-farm.example/x</link><pubDate>Thu, 23 Oct 2026 02:00:00 +0000</pubDate></item>
<item><title>Feedburner 條目</title><link>https://feedproxy.example/r</link><feedburner:origLink>https://ent.ltn.com.tw/news/2</feedburner:origLink>
<pubDate>Thu, 23 Oct 2026 03:00:00 +0000</pubDate></item></channel></rss>""".encode()

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Tour announced</title><link href="https://variety.com/2026/a/"/>
<updated>2026-10-23T05:00:00Z</updated><summary>A tour.</summary></entry></feed>""".encode()


def test_feed_entries_off_the_whitelist_are_dropped_at_parse_time(series) -> None:
    ltn = next(f for f in series.feeds if f.id == "ltn")
    result = feeds.parse_feed(RSS, ltn)
    assert [c.url for c in result.candidates] == ["https://ent.ltn.com.tw/news/1", "https://ent.ltn.com.tw/news/2"]
    assert result.off_list == 1 and result.candidates[0].summary == "小巨蛋兩場" and result.candidates[0].publisher == "自由時報"
    assert feeds.parse_feed(ATOM, next(f for f in series.feeds if f.id == "variety")).candidates[0].title == "Tour announced"


def test_one_dead_feed_does_not_stop_the_others(series) -> None:
    ltn, variety = (next(f for f in series.feeds if f.id == i) for i in ("ltn", "variety"))

    def get(url: str):
        from content_farm.production.news.fetch import Response

        return Response(url, 200, "text/xml", RSS) if "ltn" in url else Response(url, 503, "text/html", b"")

    found, errors, counts = feeds.fetch_feeds(get, [ltn, variety])
    assert counts == {"ltn": 2, "variety": 0} and len(found) == 2 and any("http 503" in e for e in errors)


# ── selection ────────────────────────────────────────────────────────────────

def _ranked(n: int, title: str, summary: str = "") -> dict:
    cand = Candidate(id=f"ltn-{n}", title=title, url=f"https://ent.ltn.com.tw/n{n}", domain="ent.ltn.com.tw",
                     posted_at="2026-10-23T01:00:00+00:00", discussions=(Discussion(site="rss", url="u", rank=n),), summary=summary)
    read = Read(url=cand.url, read_at=READ_AT, ok=True, chars=1500, page_title=title)
    return Ranked(candidate=cand, score=0.5, popularity=0.5, freshness=1, relevance=0.5, age_hours=3, read=read).model_dump()


def _answer(rows: dict[str, tuple[float, bool]]) -> CallResult:
    items = [{"id": i, "score": s, "reason": "r", "format": "short", "format_reason": "fr", "sensitive": flag,
              "sensitive_reason": "牽涉私生活" if flag else ""} for i, (s, flag) in rows.items()]
    return CallResult("x", True, {"items": items}, (), "sonnet", "low", cost_usd=0.1, seconds=1.0)


def test_ent_panel_has_viewers_and_a_producer() -> None:
    assert [s.id for s in select.seats_for("ent")] == ["fan", "casual", "media_literate", "producer"]


def test_selection_never_shows_a_forbidden_story_to_the_panel_and_honours_seat_flags(tmp_path: Path) -> None:
    ranked = [_ranked(1, "歌手宣布開唱"), _ranked(2, "女星住址曝光"), _ranked(3, "影集開拍"), _ranked(4, "新專輯發行")]
    seen: list[str] = []

    def client(call):
        seen.append(call.prompt)
        return _answer({"ltn-1": (9, False), "ltn-3": (8, True), "ltn-4": (7, False)})

    out = select.select(tmp_path, ranked, select.seats_for("ent"), "娛樂快報", count=3, client=client, topic_guard=True,
                        brief="娛樂新聞頻道")
    assert all("女星住址曝光" not in p for p in seen) and "sensitive" in seen[0] and "娛樂新聞頻道" in seen[0]
    rows = {r["id"]: r for r in out.selection["items"]}
    assert [r["id"] for r in out.chosen] == ["ltn-1", "ltn-4"]
    assert rows["ltn-2"]["decision"].startswith("skip: 禁碰題材（程式過濾）")
    assert rows["ltn-3"]["decision"] == "skip: 禁碰題材（評審標記）" and rows["ltn-3"]["sensitive"]


def test_tech_selection_prompt_is_unchanged_without_the_guard() -> None:
    seat = select.seats_for("technews")[0]
    prompt = select.prompt_for(seat, [], "科技新知")
    assert "每日科技新知頻道" in prompt and "sensitive" not in prompt


# ── claim audit ──────────────────────────────────────────────────────────────

def test_a_fully_sourced_script_audits_clean(series) -> None:
    assert claims.audit(_script(), ITEM, PAGE, series) == []


def _codes(series, script) -> list[str]:
    return [p.code for p in claims.audit(script, ITEM, PAGE, series)]


def test_a_sentence_of_fact_without_a_claim_is_an_error(series) -> None:
    assert _codes(series, _script(what=_beat("what", "他在社群宣布，地點是台北小巨蛋。他還簽了新公司。",
                                            GOOD["what"].claims[0]))) == [claims.NO_CLAIM]


def test_a_rumour_told_as_fact_is_an_error_and_the_fix_makes_it_attributed(series) -> None:
    text = "他正在籌備電影演出。"
    script = _script(why=_beat("why", text, _claim(text, "網傳他正在籌備電影演出")))
    assert _codes(series, script) == [claims.UNATTRIBUTED]
    fixed, fixes = claims.auto_fix(script, claims.audit(script, ITEM, PAGE, series), ITEM, series)
    assert fixes[0].action == "rewritten"
    assert fixed.beats[2].narration == "據自由時報報導，他正在籌備電影演出。"
    assert claims.audit(fixed, ITEM, PAGE, series) == []                 # idempotent: the fixed script is clean


def test_claims_must_quote_the_page_that_was_read(series) -> None:
    text = "據自由時報報導，他下個月要結婚。"
    script = _script(why=_beat("why", text, _claim(text, "他下個月要結婚了喔")))
    assert _codes(series, script) == [claims.NO_EVIDENCE]
    other = _script(why=_beat("why", text, _claim(text, "出道十週年的第一場大型演出", source="https://udn.com/other")))
    assert _codes(series, other) == [claims.BAD_SOURCE]
    offlist = dict(ITEM, read={"ok": True, "url": "https://blog.example/x", "final_url": ""})
    bad = claims.audit(_script(why=_beat("why", text, _claim(text, "出道十週年的第一場大型演出", source="https://blog.example/x"))),
                       offlist, PAGE, series)
    assert [p.code for p in bad if p.beat == 2] == [claims.BAD_SOURCE]          # a page we did not read, off the whitelist


def test_confirmed_needs_the_party_to_have_said_it_and_to_be_named(series) -> None:
    text = "經紀公司證實他正在籌備電影演出。"
    no_marker = _script(why=_beat("why", text, _claim(text, "網傳他正在籌備電影演出", "confirmed", "經紀公司")))
    assert _codes(series, no_marker) == [claims.NOT_CONFIRMED]            # the page only says 網傳; nobody confirmed
    unnamed = "他的演出已經確定。"
    assert _codes(series, _script(why=_beat("why", unnamed, _claim(unnamed, "經紀公司對媒體表示，首場售票時間訂在下週三中午十二點",
                                                                      "confirmed", "經紀公司")))) == [claims.NOT_CONFIRMED]
    fixed, fixes = claims.auto_fix(*_fix_args(series, no_marker), ITEM, series)
    assert fixed.beats[2].claims[0].status == "reported" and fixed.beats[2].narration.startswith("據自由時報報導，")


def _fix_args(series, script):
    return script, claims.audit(script, ITEM, PAGE, series)


def test_unsourceable_sentences_are_deleted_and_an_emptied_beat_falls_back_to_the_headline(series) -> None:
    text = "他的新戀情曝光。"
    script = _script(why=_beat("why", text))
    fixed, fixes = claims.auto_fix(*_fix_args(series, script), ITEM, series)
    assert fixes[0].action == "deleted" and fixes[1].code == "EMPTY_BEAT"
    assert fixed.beats[2].narration == "據自由時報報導，小明宣布年底開唱。" and claims.audit(fixed, ITEM, PAGE, series) == []
    assert script.beats[2].narration == text                              # the input is never mutated


def test_the_take_beat_is_opinion_and_needs_no_claim(series) -> None:
    assert not any(p.beat == 4 for p in claims.audit(_script(), ITEM, PAGE, series))


# ── the run step ─────────────────────────────────────────────────────────────

def _run_dir(tmp_path: Path, script: ns.NewsScript) -> Path:
    cache = tmp_path / "reads"
    cache.mkdir()
    (cache / "ltn-1.txt").write_text("# t\nURL: x\n\n" + PAGE, encoding="utf-8")
    item = dict(ITEM, read={**ITEM["read"], "text_path": str(cache / "ltn-1.txt")})
    (tmp_path / ns.ITEM_FILE).write_text(json.dumps(item), encoding="utf-8")
    (tmp_path / ns.SCRIPT_FILE).write_text(script.model_dump_json(indent=2), encoding="utf-8")
    return tmp_path


def _bad_script() -> ns.NewsScript:
    rumour = "他正在籌備電影演出。"
    return _script(why=_beat("why", rumour + "他的新戀情曝光。", _claim(rumour, "網傳他正在籌備電影演出")))


def test_audit_step_fixes_once_logs_and_passes_without_a_recheck(tmp_path: Path, series, monkeypatch, capsys) -> None:
    monkeypatch.delenv("CF_REVIEW_POLICY", raising=False)
    run = _run_dir(tmp_path, _bad_script())
    assert audit_step.run(run, "ent", series) == 0
    report = json.loads((run / audit_step.REPORT).read_text())
    assert report["outcome"] == "auto_fixed_then_passed" and len(report["errors"]) == 2
    assert {f["action"] for f in report["fixes"]} == {"deleted", "rewritten"}
    rows = [json.loads(line) for line in (run / "review" / "auto_fix.jsonl").read_text().splitlines()]
    assert [r["event"] for r in rows] == ["fix_issued", "passed_without_recheck"] and rows[1]["content_changed"] is True
    fixed = ns.load_script(run)
    assert fixed.beats[2].narration == "據自由時報報導，他正在籌備電影演出。" and (run / audit_step.DRAFT).is_file()
    assert audit_step.was_fixed(run)
    before = (run / audit_step.REPORT).read_text()
    assert audit_step.run(run, "ent", series) == 0 and (run / audit_step.REPORT).read_text() == before   # idempotent
    assert len((run / "review" / "auto_fix.jsonl").read_text().splitlines()) == 2


def test_audit_step_stops_when_the_policy_is_stop(tmp_path: Path, series) -> None:        # conftest: legacy ⇒ fact_on_fail=stop
    run = _run_dir(tmp_path, _bad_script())
    before = (run / ns.SCRIPT_FILE).read_text()
    assert audit_step.run(run, "ent", series) == 1
    assert (run / ns.SCRIPT_FILE).read_text() == before and not (run / audit_step.DRAFT).exists()
    assert json.loads((run / audit_step.REPORT).read_text())["outcome"] == "stopped"


def test_clean_script_passes_untouched(tmp_path: Path, series, monkeypatch) -> None:
    monkeypatch.delenv("CF_REVIEW_POLICY", raising=False)
    run = _run_dir(tmp_path, _script())
    assert audit_step.run(run, "ent", series) == 0
    assert json.loads((run / audit_step.REPORT).read_text())["outcome"] == "clean" and not (run / audit_step.DRAFT).exists()


# ── lint guardrails ──────────────────────────────────────────────────────────

def test_lint_rejects_forbidden_topics_and_off_list_sources(series) -> None:
    bad_topic = _script(why=_beat("why", "據自由時報報導，他的家人也到場。", _claim("據自由時報報導，他的家人也到場。", "x" * 6)))
    assert any("禁碰題材" in p for p in ns.lint(bad_topic, ITEM, series=series, glossary={}))
    off = _script().model_copy(update={"sources": (ns.SourceRef(url="https://blog.example/x", title="t", read_at=READ_AT),)})
    assert any("白名單" in p for p in ns.lint(off, ITEM, series=series, glossary={}))


def test_ent_script_needs_no_glossary_analogy_but_tech_still_does(series) -> None:
    problems = ns.lint(_script(), ITEM, series=series, glossary={}, after_fix=True)
    assert not any("analogy" in p for p in problems)
    tech = ns.lint(_script(), ITEM, glossary={}, after_fix=True)
    assert any("analogy: term is empty" in p for p in tech)


def test_after_fix_relaxes_length_but_not_the_ceiling(series) -> None:
    short = _script(why=_beat("why", "據自由時報報導，小明宣布開唱。", _claim("據自由時報報導，小明宣布開唱。", "年底將在台北小巨蛋舉辦兩場演唱會")))
    assert any("why: narration" in p for p in ns.lint(short, ITEM, series=series, glossary={}))
    assert not any("why: narration" in p for p in ns.lint(short, ITEM, series=series, glossary={}, after_fix=True))
