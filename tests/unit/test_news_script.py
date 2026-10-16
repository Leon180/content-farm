"""production/news: news_script.json rules, script.json conversion, render helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from content_farm.production.news import script as ns
from content_farm.production.news.render import relayout, reveal_times, source_strip
from content_farm.production.shorts_cut import Cue

READ_URL = "https://ipinfo.io/blog/rpki-protects-70-internet-routes"
GLOSSARY = {"RPKI": {"analogy": "印章", "definition": "Resource PKI", "say": "R P K I"}}


def _beats(**override: str) -> list[dict]:
    text = {
        "hook": "網路上該走哪條路，現在七成有蓋章了。",
        "what": "IPinfo 分析一年資料：通過 RPKI 驗證的路由從五十四升到七十，大半成長來自中國，失敗路由幾乎傳不出去。",
        "why": "原文沒列台灣的數字。但路由被冒名，連線就會被帶走，二零零八年 YouTube 被導走兩小時。",
        "analogy": "RPKI 就像給路線地圖蓋上官方印章，冒牌路標一眼就被認出來。",
        "take": "我覺得七成不是終點。重點不是有沒有蓋章，是蓋得對不對，還有百分之十六的印章太鬆。",
    } | override
    return [{"kind": k, "narration": v, "screen": {"headline": k}, **({"term": "RPKI"} if k == "analogy" else {})}
            for k, v in text.items()]


def _script(beats: list[dict] | None = None, sources: list[dict] | None = None, **fields) -> ns.NewsScript:
    data = {"item_id": "hn-1", "title": "RPKI 一年升到七成", "summary": "IPinfo：RPKI 驗證路由一年從 54% 升到 70%。",
            "importance": 3,
            "sources": sources if sources is not None else [
                {"url": READ_URL, "title": "RPKI 70%", "publisher": "IPinfo", "read_at": "2026-10-16T23:46:16+08:00"},
                {"url": "https://news.ycombinator.com/item?id=1", "title": "HN", "kind": "discussion"}],
            "beats": beats or _beats(), **fields}
    return ns.NewsScript.model_validate(data)


ITEM = {"read": {"ok": True, "url": READ_URL, "final_url": READ_URL}}


def test_a_good_script_passes() -> None:
    assert ns.lint(_script(), ITEM, GLOSSARY) == []


def test_take_must_be_an_opinion() -> None:
    script = _script(_beats(take="RPKI 的覆蓋率從百分之五十四升到七十，中國貢獻最多，其他國家也有成長。"))
    assert any("觀點" in p for p in ns.lint(script, ITEM, GLOSSARY))


def test_discussion_alone_is_not_a_source() -> None:
    script = _script(sources=[{"url": "https://news.ycombinator.com/item?id=1", "title": "HN", "kind": "discussion"}])
    problems = ns.lint(script, ITEM, GLOSSARY)
    assert any("leads, not facts" in p for p in problems)


def test_primary_source_must_be_the_page_that_was_read() -> None:
    other = [{"url": "https://elsewhere.com/x", "title": "x", "read_at": "2026-10-16T23:00:00+08:00"}]
    assert any("URL that was read" in p for p in ns.lint(_script(sources=other), ITEM, GLOSSARY))
    unread = {"read": {"ok": False, "url": READ_URL}}
    assert any("never read" in p for p in ns.lint(_script(), unread, GLOSSARY))
    no_time = [{"url": READ_URL, "title": "x"}]
    assert any("no read_at" in p for p in ns.lint(_script(sources=no_time), ITEM, GLOSSARY))


def test_analogy_term_must_be_in_the_glossary() -> None:
    beats = _beats()
    beats[3] = {**beats[3], "term": "ASPA"}
    assert any("glossary" in p for p in ns.lint(_script(beats), ITEM, GLOSSARY))


@pytest.mark.parametrize(("field", "text", "needle"), [
    ("hook", "這消息真的太神了，七成有蓋章。", "流行語"),
    ("take", "我覺得現在可以買進網通股，重點不是蓋章，是蓋得對不對，還有很多印章太鬆。", "投資建議"),
])
def test_banned_words(field: str, text: str, needle: str) -> None:
    assert any(needle in p for p in ns.lint(_script(_beats(**{field: text})), ITEM, GLOSSARY))


def test_length_window_and_beat_order() -> None:
    long_what = "很長的句子。" * 30
    problems = ns.lint(_script(_beats(what=long_what)), ITEM, GLOSSARY)
    assert any(p.startswith("what: narration") for p in problems)
    shuffled = _beats()
    shuffled[0], shuffled[1] = shuffled[1], shuffled[0]
    assert any("beats must be" in p for p in ns.lint(_script(shuffled), ITEM, GLOSSARY))


def test_to_script_is_deterministic_and_carries_sources() -> None:
    news = _script()
    a, b = ns.to_script(news, GLOSSARY), ns.to_script(news, GLOSSARY)
    assert a.model_dump_json() == b.model_dump_json()
    assert a.video_title.endswith("#Shorts") and len(a.scenes) == 5
    assert a.orientation.value == "portrait"
    assert any("讀取 2026-10-16 23:46" in s for s in a.sources)
    assert any("只當線索" in s for s in a.sources)
    assert a.pronunciation_map == {"RPKI": "R P K I"}
    assert "不是翻譯" in a.description


def test_screen_only_edits_keep_measured_durations_and_voice_text() -> None:
    measured = ns.to_script(_script(), GLOSSARY)
    measured = measured.model_copy(update={"scenes": tuple(s.model_copy(update={"duration_seconds": 7.0})
                                                           for s in measured.scenes),
                                           "total_duration_seconds": 35.0})
    beats = _beats()
    beats[4] = {**beats[4], "screen": {"headline": "改了畫面字"}}
    edited = ns.to_script(_script(beats), GLOSSARY)
    kept = ns.keep_measured(edited, measured)
    assert [s.duration_seconds for s in kept.scenes] == [7.0] * 5
    assert ns.voice_text(kept) == ns.voice_text(measured)
    reworded = ns.to_script(_script(_beats(hook="網路上該走哪條路，七成有章了。")), GLOSSARY)
    assert ns.keep_measured(reworded, measured).scenes[0].duration_seconds != 7.0


def test_glossary_file_is_valid() -> None:
    glossary = ns.load_glossary()
    assert {"RPKI", "MoE", "授權費"} <= set(glossary)


def test_glossary_entries_need_analogy_and_definition(tmp_path: Path) -> None:
    bad = tmp_path / "g.yaml"
    bad.write_text("terms:\n  X:\n    analogy: a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="definition"):
        ns.load_glossary(bad)


def test_relayout_keeps_cues_within_two_lines() -> None:
    cues = relayout([Cue(0.0, 6.0, "授權費就像用別人的食譜開店，\n每賣一碗都要付錢，高通想主張作者違約在先所以五年不用付。")])
    assert all(len(c.text.split("\n")) <= 2 for c in cues)
    assert cues[0].start == 0.0 and cues[-1].end == pytest.approx(6.0)
    assert relayout(cues) == cues     # idempotent: render may run again on its own output


def test_reveals_spread_over_the_beat() -> None:
    times = reveal_times(3, 9.0)
    assert times == sorted(times) and times[-1] < 9.0 and times[1] - times[0] >= 1.5
    assert reveal_times(0, 5.0) == []


def test_source_strip_names_the_original_not_hn() -> None:
    assert source_strip(_script()).startswith("來源：IPinfo・10-16 讀原文")
