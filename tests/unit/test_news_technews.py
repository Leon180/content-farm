"""科技新知 (technews): selection panel + format decision, no-mascot Short page, news branding."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.production.channels import load_channel
from content_farm.production.news import daily, select
from content_farm.production.news import script as ns
from content_farm.production.news.models import Candidate, Discussion, Ranked, Read
from content_farm.production.news.render import page_html, source_card
from content_farm.production.news.series import branding_for, news_series
from content_farm.review.client import CallResult


def _ranked(n: int, chars: int = 3000, ok: bool = True) -> dict:
    cand = Candidate(id=f"hn-{n}", title=f"Story {n}", url=f"https://ex{n}.com/a", domain=f"ex{n}.com",
                     posted_at="2026-10-23T01:00:00+00:00", discussions=(Discussion(site="hn", url="u", points=10),))
    read = Read(url=cand.url, read_at="2026-10-23T09:00:00+08:00", ok=ok, chars=chars, page_title=f"Page {n}",
                published="2026-10-22T08:00:00Z")
    return Ranked(candidate=cand, score=0.5, popularity=0.5, freshness=1, relevance=0.2, age_hours=3, read=read).model_dump()


def _seat_answer(rows: dict[str, tuple[float, str]], ok: bool = True) -> CallResult:
    items = [{"id": i, "score": s, "reason": "r", "format": f, "format_reason": "fr"} for i, (s, f) in rows.items()]
    return CallResult("x", ok, {"items": items} if ok else None, () if ok else ("boom",), "sonnet", "low",
                      cost_usd=0.1, seconds=1.0)


def test_seats_are_three_viewers_and_a_producer() -> None:
    seats = select.seats_for("technews")
    assert [s.id for s in seats] == ["commuter", "engineer", "student", "producer"]
    with pytest.raises(ValueError):
        select.seats_for("no-such-channel")


def test_panel_picks_top_stories_and_long_needs_votes_and_enough_material(tmp_path: Path) -> None:
    ranked = [_ranked(1, chars=9000), _ranked(2, chars=9000), _ranked(3, chars=1200), _ranked(4)]
    answers = {
        "a": _seat_answer({"hn-1": (9, "long"), "hn-2": (8, "short"), "hn-3": (7, "long"), "hn-4": (4, "short")}),
        "b": _seat_answer({"hn-1": (8, "long"), "hn-2": (7, "short"), "hn-3": (8, "long"), "hn-4": (5, "short")}),
        "c": _seat_answer({"hn-1": (9, "short"), "hn-2": (8, "long"), "hn-3": (7, "long"), "hn-4": (4, "short")}),
    }
    items = [{"id": r["candidate"]["id"], "title": r["candidate"]["title"], "domain": "d", "popularity": 0.5,
              "read": r["read"], "position": i} for i, r in enumerate(ranked, start=1)]
    got = select.aggregate(items, answers, count=3)
    by_id = {r["id"]: r for r in got.selection["items"]}
    assert [r["id"] for r in got.chosen] == ["hn-1", "hn-2", "hn-3"]
    assert by_id["hn-4"]["decision"] == "skip: below floor"
    assert by_id["hn-1"]["format"] == "long" and "2/3" in by_id["hn-1"]["format_why"]
    assert by_id["hn-2"]["format"] == "short"                       # one long vote only
    assert by_id["hn-3"]["format"] == "short" and "素材不夠" in by_id["hn-3"]["format_why"]   # 3/3 long, 1,200 chars
    assert got.selection["usd"] == pytest.approx(0.3)


def test_panel_with_every_seat_failing_is_an_error_not_a_silent_empty_pick() -> None:
    with pytest.raises(RuntimeError, match="every seat failed"):
        select.aggregate([{"id": "hn-1", "title": "t", "read": {"chars": 1}, "position": 1}],
                         {"a": _seat_answer({}, ok=False)}, count=2)


def test_select_writes_the_record_and_decisions(tmp_path: Path) -> None:
    ranked = [_ranked(1, chars=9000), _ranked(2)]

    def client(call):
        return _seat_answer({"hn-1": (9, "long"), "hn-2": (7, "short")})

    out = select.select(tmp_path, ranked, select.seats_for("technews"), "科技新知", count=2, client=client)
    assert json.loads((tmp_path / select.SELECTION_FILE).read_text())["items"][0]["id"] == "hn-1"
    path = select.write_decision(tmp_path / "run", out.chosen[0]) if (tmp_path / "run").mkdir() is None else None
    assert json.loads(path.read_text())["format"] == "long"


def test_technews_short_page_has_no_mascot_and_shows_the_source_card(tmp_path: Path) -> None:
    channel = load_channel("technews")
    (tmp_path / ns.ITEM_FILE).write_text(json.dumps({"day": "2026-10-23", **{
        k: v for k, v in Ranked.model_validate(_ranked(1)).model_dump().items()}}), encoding="utf-8")
    card = source_card(tmp_path)
    assert card == {"domain": "ex1.com", "title": "Page 1", "date": "發布 2026-10-22"}
    beat = lambda kind: ns.Beat(kind=kind, narration="測試旁白" * 8, screen=ns.Screen(headline="標題"))   # noqa: E731
    script = ns.NewsScript(item_id="hn-1", title="測試標題四字", summary="一句摘要要夠長才行吧", importance=3,
                           sources=(ns.SourceRef(url="https://ex1.com/a", title="t", read_at="2026-10-23T09:00:00+08:00"),),
                           beats=tuple(beat(k) for k in ns.BEAT_ORDER))
    html = page_html("beat", news=script, channel=channel, day="2026-10-23", index=4, duration=5.0, card=card)
    assert "科技新知" in html and "晶片貓" not in html and 'class="cat"' not in html
    assert "srccard" in html and "ex1.com" in html and "編輯觀點" in html


def test_branding_defaults_stay_chipcat_and_technews_overrides() -> None:
    chipcat, technews = branding_for(load_channel("chipcat")), branding_for(load_channel("technews"))
    assert chipcat == ns.Branding() and "晶片貓" in chipcat.series_line
    assert technews.take_label == "編輯觀點" and "晶片貓" not in " ".join((technews.byline, technews.series_line, *technews.tags))
    assert news_series(load_channel("technews")).sources == ("hn", "lobsters", "arxiv", "github")


def test_long_run_dir_seeds_a_topic_and_records_the_format(tmp_path: Path) -> None:
    ranked = [Ranked.model_validate(_ranked(1, chars=9000))]
    row = {"id": "hn-1", "title": "Story 1", "mean": 8.5, "format": "long", "format_why": "3/4 席判長片",
           "seats": {"commuter": {"score": 9}}}
    run_dir = daily.start_long(tmp_path, "2026-10-23", row, ranked, load_channel("technews"))
    topics = json.loads((run_dir / "topics" / "candidates.json").read_text())["candidates"]
    assert topics[0]["title"] == "Story 1" and topics[0]["sources"][0] == "https://ex1.com/a"
    assert json.loads((run_dir / select.DECISION_FILE).read_text())["why"] == "3/4 席判長片"
    assert daily.long_runs(tmp_path, "2026-10-23") == [run_dir]
