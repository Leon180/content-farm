"""production/news: candidate page, picking, run-dir dispatch, weekly selection."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from content_farm.production import qc
from content_farm.production.channels import Gate, load_channel
from content_farm.production.news import daily, weekly
from content_farm.production.news import script as ns
from content_farm.production.news.models import Candidate, Discussion, Ranked, Read
from content_farm.production.news.review import load_candidates, write_candidates
from content_farm.production.news.series import NewsSeries, news_series
from content_farm.production.state import Decision, load_state, save_state
from content_farm.production.steps import NEWS_SHORT_STEPS, steps_for

DAY = "2026-10-16"
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def chipcat():
    return load_channel("chipcat")


@pytest.fixture
def series(chipcat) -> NewsSeries:
    return news_series(chipcat)


def _ranked(i: int, ok: bool = True, title: str = "Story") -> Ranked:
    url = f"https://ex{i}.com/a"
    cand = Candidate(id=f"hn-{i}", title=f"{title} {i}", url=url, domain=f"ex{i}.com",
                     posted_at=(NOW - timedelta(hours=i)).isoformat(),
                     discussions=(Discussion(site="hn", url=f"https://news.ycombinator.com/item?id={i}",
                                             points=100 - i, comments=10, rank=i),))
    read = Read(url=url, final_url=url, read_at="2026-10-16T20:00:00+08:00", ok=ok,
                reason="" if ok else "http 403 (paywall / blocked?)", chars=4000 if ok else 0)
    return Ranked(candidate=cand, score=1 - i / 10, popularity=0.5, freshness=0.9, relevance=0.4,
                  age_hours=float(i), reasons=("ai",), read=read)


def _write_day(root: Path, series: NewsSeries, items: list[Ranked]) -> Path:
    return write_candidates(daily.day_dir(root, DAY), DAY, series, items, fetched_at=NOW,
                            counts={"hn": len(items)}, errors=[])


def test_chipcat_has_a_valid_hn_series(series: NewsSeries) -> None:
    assert series.daily_shorts == (1, 2) and series.weekly.items == (3, 5)
    assert set(series.sources) == {"hn", "lobsters", "arxiv"}


def test_series_rejects_x_as_a_source() -> None:
    with pytest.raises(ValidationError, match="no X"):
        NewsSeries(name="n", playlist="p", sources=("hn", "x"))


def test_candidate_page_is_mobile_and_escaped(tmp_path: Path, series: NewsSeries) -> None:
    page = _write_day(tmp_path, series, [_ranked(1, title="<script>alert(1)</script>"), _ranked(2, ok=False)])
    html = page.read_text(encoding="utf-8")
    assert 'name="viewport"' in html and "<script>alert(1)" not in html and "&lt;script&gt;" in html
    assert "讀不到原文" in html and 'value="2" disabled' in html and 'value="1" disabled' not in html
    assert "--pick" in html
    assert [r.candidate.id for r in load_candidates(daily.day_dir(tmp_path, DAY))] == ["hn-1", "hn-2"]


def test_pick_creates_marked_run_dirs_with_schedule(tmp_path: Path, series: NewsSeries, chipcat) -> None:
    _write_day(tmp_path, series, [_ranked(1), _ranked(2), _ranked(3)])
    picked = daily.pick(tmp_path, DAY, [3, 1], series, chipcat)
    assert [p.run_dir.name for p in picked] == ["hn-2026-10-16-hn-3", "hn-2026-10-16-hn-1"]
    item = json.loads((picked[0].run_dir / ns.ITEM_FILE).read_text(encoding="utf-8"))
    assert item["position"] == 3 and item["read"]["ok"]
    slots = [json.loads((p.run_dir / "production.schedule.json").read_text())["publish_at"] for p in picked]
    assert slots == ["2026-10-16T12:30:00+08:00", "2026-10-16T19:30:00+08:00"]
    assert daily.picked_runs(tmp_path, DAY) == sorted(p.run_dir for p in picked)
    timing = (daily.day_dir(tmp_path, DAY) / daily.TIMING_FILE).read_text(encoding="utf-8")
    assert '"phase": "pick"' in timing


def test_pick_refuses_unreadable_originals(tmp_path: Path, series: NewsSeries, chipcat) -> None:
    _write_day(tmp_path, series, [_ranked(1, ok=False)])
    with pytest.raises(ValueError, match="not readable"):
        daily.pick(tmp_path, DAY, [1], series, chipcat)
    with pytest.raises(ValueError, match="positions"):
        daily.parse_picks("1,1")


def test_news_run_dir_gets_the_news_steps(tmp_path: Path, chipcat) -> None:
    (tmp_path / ns.ITEM_FILE).write_text("{}", encoding="utf-8")
    steps = steps_for(chipcat, tmp_path)
    # chipcat (series.hn): no script panel, no claim audit (entertainment-only)
    assert steps == tuple(s for s in NEWS_SHORT_STEPS if s.name not in ("gate_script", "fact_audit", "fact_check"))
    assert [s.gate for s in steps if s.kind == "gate"] == [Gate.FINAL]
    voice = next(s for s in steps if s.name == "voice")
    assert voice.inputs == ("voice_text.json",) and voice.paid
    assert qc.qc_channel(tmp_path, chipcat).format.aspect == "9:16"


def test_weekly_run_dir_skips_the_article_stage(tmp_path: Path, chipcat) -> None:
    (tmp_path / weekly.WEEKLY_FILE).write_text("{}", encoding="utf-8")
    names = [s.name for s in steps_for(chipcat, tmp_path)]
    assert names[:2] == ["deck", "weekly_check"]
    assert "article" not in names and "gate_deck" in names and names[-1] == "package"


def _short(root: Path, day: str, item_id: str, importance: int, approved: bool, chipcat) -> Path:
    run_dir = root / f"hn-{day}-{item_id}"
    run_dir.mkdir(parents=True)
    url = f"https://{item_id}.com/a"
    (run_dir / ns.ITEM_FILE).write_text(json.dumps({"day": day, "score": 0.5, "read": {"ok": True, "url": url}}),
                                        encoding="utf-8")
    beats = [{"kind": k, "narration": f"{k} 的旁白內容", "screen": {"headline": k}} for k in ns.BEAT_ORDER]
    script = {"item_id": item_id, "title": f"題目 {item_id}", "summary": "一句話摘要，十個字以上。",
              "importance": importance, "beats": beats,
              "sources": [{"url": url, "title": "t", "read_at": "2026-10-16T20:00:00+08:00"}]}
    (run_dir / ns.SCRIPT_FILE).write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    if approved:
        state = load_state(run_dir, chipcat.code)
        save_state(run_dir, state.with_decision(Decision("final", "approved", "fp", "2026-10-16T21:00:00+08:00")))
    return run_dir


def test_weekly_picks_the_most_important_approved_shorts(tmp_path: Path, chipcat, series: NewsSeries) -> None:
    _short(tmp_path, "2026-10-12", "a", 2, True, chipcat)
    _short(tmp_path, "2026-10-13", "b", 5, True, chipcat)
    _short(tmp_path, "2026-10-14", "c", 4, True, chipcat)
    _short(tmp_path, "2026-10-15", "d", 3, False, chipcat)       # not approved
    _short(tmp_path, "2026-10-19", "e", 5, True, chipcat)        # next week
    items = weekly.week_items(tmp_path, "2026-W42", chipcat)
    assert sorted(i.news.item_id for i in items) == ["a", "b", "c", "d"]
    picked = weekly.select(items, series)
    assert [i.news.item_id for i in picked] == ["a", "b", "c"]   # calendar order
    with pytest.raises(ValueError, match="include-unapproved"):
        weekly.select(items[:2], series)
    directory = weekly.write_plan(tmp_path, "2026-W42", picked, series)
    plan = (directory / weekly.PLAN_MD).read_text(encoding="utf-8")
    assert plan.count("## 第") == 3 and "https://b.com/a" in plan


def test_weekly_deck_check(tmp_path: Path) -> None:
    from types import SimpleNamespace

    plan = {"items": [{"item_id": "a", "sources": [{"url": "https://a.com/x", "kind": "article"}]},
                      {"item_id": "b", "sources": [{"url": "https://b.com/x", "kind": "article"}]}]}
    deck = SimpleNamespace(sections=[1, 2, 3], sources=[SimpleNamespace(url="https://a.com/x")])
    assert weekly.check_deck(deck, plan) == ["b: none of its read originals is in deck.sources (https://b.com/x)"]
    short_deck = SimpleNamespace(sections=[1, 2], sources=[SimpleNamespace(url=u) for u in ("https://a.com/x", "https://b.com/x")])
    assert "sections" in weekly.check_deck(short_deck, plan)[0]


def test_series_news_channel_also_gets_the_script_panel_before_voice(tmp_path: Path) -> None:
    from content_farm.production.channels import load_channel

    technews = load_channel("technews")
    (tmp_path / ns.ITEM_FILE).write_text("{}", encoding="utf-8")
    names = [s.name for s in steps_for(technews, tmp_path)]
    assert names.index("news_prepare") < names.index("gate_script") < names.index("voice")
    assert [s.gate for s in steps_for(technews, tmp_path) if s.kind == "gate"] == [Gate.SCRIPT, Gate.FINAL]
