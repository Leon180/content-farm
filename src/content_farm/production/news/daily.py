"""``produce.py news daily``: fetch → rank → read originals → candidate page → (pick) → run each Short.

Directories (all under ``output/``, never committed)::

    output/hn-<day>/                 candidates.json / candidates.html / reads/*.txt / timing.jsonl
    output/hn-<day>-<item-id>/       one Short run-dir (news_short.json marks it; steps.NEWS_SHORT_STEPS)

Each phase appends to ``timing.jsonl`` so the "pick → finished video ≤ 1–2 h"
target is measured, not guessed.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from content_farm.production.channels import Channel
from content_farm.production.news import fetch, rank, verify
from content_farm.production.news.models import Ranked
from content_farm.production.news.review import load_candidates, write_candidates
from content_farm.production.news.script import ITEM_FILE
from content_farm.production.news.series import NewsSeries

TIMING_FILE = "timing.jsonl"
SOURCE_FETCHERS = {"hn": fetch.fetch_hn, "lobsters": fetch.fetch_lobsters, "arxiv": fetch.fetch_arxiv,
                   "github": fetch.fetch_github}
SECOND_SHORT_OFFSET = timedelta(hours=7)   # 12:30 and 19:30 when two are picked


def day_dir(root: Path, day: str, prefix: str = "hn") -> Path:
    return root / f"{prefix}-{day}"


def short_dir(root: Path, day: str, item_id: str, prefix: str = "hn") -> Path:
    return root / f"{prefix}-{day}-{re.sub(r'[^a-z0-9.-]+', '-', item_id.lower())}"


def log_timing(directory: Path, phase: str, seconds: float, **extra: object) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    row = {"at": datetime.now().astimezone().isoformat(timespec="seconds"), "phase": phase,
           "seconds": round(seconds, 1), **extra}
    with (directory / TIMING_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _fetch(series: NewsSeries, get: fetch.Getter) -> fetch.FetchReport:
    found, errors, counts = [], [], {}
    allowed = verify.robots_allows(get)
    for name in series.sources:
        try:
            if name == "github" and not allowed(fetch.GITHUB_TRENDING):   # HTML page: honour robots.txt
                raise fetch.FetchError("github.com/robots.txt disallows /trending for us; skipped")
            items = SOURCE_FETCHERS[name](get)
        except (fetch.FetchError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{name}: {exc}")
            items = []
        counts[name] = len(items)
        found.extend(items)
    return fetch.FetchReport(tuple(found), tuple(errors), counts)


def collect(root: Path, day: str, series: NewsSeries, http: fetch.PoliteHttp, now: datetime,
            log: Callable[[str], None] = print) -> Path:
    """Fetch, rank, read the top ``review_candidates`` originals, write the review page."""
    directory = day_dir(root, day, series.dir_prefix)
    started = time.monotonic()
    report = _fetch(series, http.get)
    log_timing(directory, "fetch", time.monotonic() - started, counts=report.counts, errors=list(report.errors))
    ranked = rank.rank(report.candidates, now, series.weights(), series.max_age_hours)
    log(f"fetched {report.counts}; {len(ranked)} within {series.max_age_hours:.0f} h after dedupe")
    started = time.monotonic()
    robots = verify.robots_allows(http.get)
    shown = [r.model_copy(update={"read": verify.read_original(r.candidate, http.get, robots, directory / "reads")})
             for r in with_source_floor(ranked, series.review_candidates, series.min_per_source)]
    readable = sum(bool(r.read and r.read.ok) for r in shown)
    log_timing(directory, "verify", time.monotonic() - started, read=len(shown), readable=readable)
    page = write_candidates(directory, day, series, shown, fetched_at=now.astimezone(),
                            counts=report.counts, errors=report.errors)
    log(f"read {len(shown)} originals ({readable} readable) → {page}")
    return page


def _site(r: Ranked) -> str:
    return r.candidate.discussions[0].site if r.candidate.discussions else "hn"


def with_source_floor(ranked: list[Ranked], limit: int, per_source: int) -> list[Ranked]:
    """Top ``limit`` by score, but the best ``per_source`` stories of every non-HN source are always shown
    (HN's points would otherwise crowd out arXiv papers and trending repos), in score order."""
    if per_source <= 0:
        return ranked[:limit]
    forced: list[Ranked] = []
    for site in sorted({_site(r) for r in ranked} - {"hn"}):
        forced += [r for r in ranked if _site(r) == site][:per_source]
    keep = {r.candidate.id for r in forced}
    rest = [r for r in ranked if r.candidate.id not in keep][:max(0, limit - len(forced))]
    chosen = {r.candidate.id for r in (*forced, *rest)}
    return [r for r in ranked if r.candidate.id in chosen]


def parse_picks(text: str) -> list[int]:
    try:
        picks = [int(part) for part in text.split(",") if part.strip()]
    except ValueError as exc:
        raise ValueError(f"--pick takes list positions like 2,5 (got {text!r})") from exc
    if not picks or len(set(picks)) != len(picks) or min(picks) < 1:
        raise ValueError(f"--pick: positive, distinct positions please (got {text!r})")
    return picks


def publish_slot(day: str, series: NewsSeries, channel: Channel, order: int) -> datetime:
    hour, minute = (int(x) for x in series.shorts_time.split(":"))
    base = datetime.fromisoformat(day).replace(hour=hour, minute=minute,
                                               tzinfo=ZoneInfo(channel.cadence.timezone))
    return base + SECOND_SHORT_OFFSET * order


@dataclass(frozen=True)
class Picked:
    run_dir: Path
    ranked: Ranked


def pick(root: Path, day: str, picks: Sequence[int], series: NewsSeries, channel: Channel) -> list[Picked]:
    """Create one Short run-dir per picked position; refuses stories whose original was not read."""
    ranked = load_candidates(day_dir(root, day, series.dir_prefix))
    low, high = series.daily_shorts
    total = len({*picked_runs(root, day, series.dir_prefix), *(short_dir(root, day, ranked[p - 1].candidate.id, series.dir_prefix)
                                            for p in picks if p <= len(ranked))})
    if total > high:  # a guideline (policy review D6: quality over volume), not a hard stop
        print(f"⚠ {day} 共 {total} 支 Short，超過系列設定的每日 {high} 支")
    chosen = []
    for order, position in enumerate(picks):
        if position > len(ranked):
            raise ValueError(f"--pick {position}: the list has {len(ranked)} stories")
        item = ranked[position - 1]
        if item.read is None or not item.read.ok:
            raise ValueError(f"#{position} {item.candidate.title!r}: original not readable "
                             f"({item.read.reason if item.read else 'never read'}); pick another")
        run_dir = short_dir(root, day, item.candidate.id, series.dir_prefix)
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "series": "hn", "day": day, "position": position,
                   "picked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                   **item.model_dump()}
        (run_dir / ITEM_FILE).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        schedule = run_dir / "production.schedule.json"
        if not schedule.is_file():
            when = publish_slot(day, series, channel, order)
            schedule.write_text(json.dumps({"publish_at": when.isoformat()}), encoding="utf-8")
        chosen.append(Picked(run_dir, item))
    log_timing(day_dir(root, day, series.dir_prefix), "pick", 0.0, picks=list(picks),
               run_dirs=[str(p.run_dir) for p in chosen], below_min=len(picks) < low)
    return chosen


def long_runs(root: Path, day: str) -> list[Path]:
    """Long-video run-dirs the selection panel started for ``day``."""
    return sorted(p.parent for p in root.glob(f"technews-long-{day}-*/format_decision.json"))


def start_long(root: Path, day: str, row: dict, ranked: list[Ranked], channel: Channel) -> Path:
    """A story the panel judged worth a long video: an explainer run-dir whose topic step is already
    answered by the one candidate (the topic panel then still scores it; article → deck → … as usual)."""
    from content_farm.production.news import select

    item = next(r for r in ranked if r.candidate.id == row["id"])
    run_dir = root / f"technews-long-{day}-{re.sub(r'[^a-z0-9.-]+', '-', row['id'].lower())}"
    (run_dir / "topics").mkdir(parents=True, exist_ok=True)
    urls = [item.candidate.url, *(d.url for d in item.candidate.discussions)]
    candidate = {"id": "t01", "title": item.candidate.title, "hook": row["format_why"], "minutes": 8,
                 "sources": urls[:3], "note": f"每日選題評審團 {row['mean']} 分；原文 {item.candidate.domain}，已於 "
                                              f"{item.read.read_at if item.read else ''} 讀過"}
    (run_dir / "topics" / "candidates.json").write_text(
        json.dumps({"candidates": [candidate]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "news_origin.json").write_text(json.dumps(
        {"series": "news", "day": day, **item.model_dump()}, ensure_ascii=False, indent=2), encoding="utf-8")
    select.write_decision(run_dir, row)
    return run_dir


def picked_runs(root: Path, day: str, prefix: str = "hn") -> list[Path]:
    """Run-dirs already created for ``day`` (to resume without re-picking)."""
    return sorted(p.parent for p in root.glob(f"{prefix}-{day}-*/{ITEM_FILE}"))
