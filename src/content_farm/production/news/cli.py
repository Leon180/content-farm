"""``produce.py news daily|weekly`` — wired into scripts/produce.py.

daily:  (no candidates yet) fetch → rank → read originals → candidates.html, stop (exit 3)
        --pick 2,5         create the Short run-dirs, then run each to its next stop
        (again, no --pick) resume every Short already picked for that day
weekly: pick the week's Shorts → weekly_plan.md → run the weekly run-dir to its next stop
Every run that stops at the final gate gets ``upload/manual/`` (README + preview.html).
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from content_farm.production.channels import load_channel
from content_farm.production.manual_kit import KitOptions, write_kit
from content_farm.production.news import daily, weekly
from content_farm.production.news.fetch import PoliteHttp
from content_farm.production.news.series import NewsSeries, news_series
from content_farm.production.runner import Outcome, Runner, RunResult
from content_farm.production.steps import Context, RunOptions

DEFAULT_ROOT = Path("output")


def add_parser(sub: argparse._SubParsersAction) -> None:
    news = sub.add_parser("news", help="HN 快報: daily Shorts / weekly long video")
    news.add_argument("mode", choices=("daily", "weekly"))
    news.add_argument("--channel", default="chipcat")
    news.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    news.add_argument("--date", default=None, help="daily: YYYY-MM-DD (default today)")
    news.add_argument("--pick", default="", help="daily: list positions from candidates.html, e.g. 2,5")
    news.add_argument("--refetch", action="store_true", help="daily: fetch again even if candidates exist")
    news.add_argument("--week", default=None, help="weekly: ISO week, e.g. 2026-W42 (default this week)")
    news.add_argument("--include-unapproved", action="store_true",
                      help="weekly: also use Shorts whose final gate is not approved (trial runs)")
    news.add_argument("--mock-voice", action="store_true")
    news.add_argument("--allow-paid", action="store_true")
    news.add_argument("--until", help="stop each run after this step")
    news.add_argument("--max-load", type=float, default=None)
    news.add_argument("--env-file", type=Path)


def _options(args: argparse.Namespace) -> RunOptions:
    return RunOptions(mock_voice=args.mock_voice, allow_paid=args.allow_paid,
                      **({"env_file": args.env_file} if args.env_file else {}))


def _advance(run_dir: Path, channel, args: argparse.Namespace) -> RunResult:
    runner = Runner(Context(channel, run_dir.resolve(), _options(args)), max_load=args.max_load)
    result = runner.run(until=args.until)
    print(f"  [{result.outcome.value}] {run_dir.name} · {result.step}: {result.message}")
    if result.outcome is Outcome.GATE and result.step == "gate_final":
        kit = write_kit(run_dir.resolve(), channel, KitOptions(playlist=_series(channel).playlist))
        print(f"    預覽：{kit.directory / 'preview.html'}")
        print(f"    核可：python scripts/produce.py approve --run-dir {run_dir} --gate final")
    elif result.review_page:
        print(f"    審核頁：{result.review_page}")
    return result


def _series(channel) -> NewsSeries:
    return news_series(channel)


def run_daily(args: argparse.Namespace) -> int:
    channel = load_channel(args.channel)
    series = _series(channel)
    day = args.date or date.today().isoformat()
    date.fromisoformat(day)
    candidates = daily.day_dir(args.root, day) / "candidates.json"
    if args.refetch or not candidates.is_file():
        http = PoliteHttp()
        try:
            page = daily.collect(args.root, day, series, http, datetime.now().astimezone())
        finally:
            http.close()
        if not args.pick:
            print(f"候選頁：{page}\n挑完：python scripts/produce.py news daily --date {day} --pick 1,3")
            return 3
    if args.pick:
        daily.pick(args.root, day, daily.parse_picks(args.pick), series, channel)
    runs = daily.picked_runs(args.root, day)
    if not runs:
        print(f"{day} 還沒挑題：開 {daily.day_dir(args.root, day) / 'candidates.html'}")
        return 3
    print(f"{day}：{len(runs)} 支 Short")
    results = [_advance(run, channel, args) for run in runs]
    return max(r.exit_code for r in results)


def run_weekly(args: argparse.Namespace) -> int:
    channel = load_channel(args.channel)
    series = _series(channel)
    year, week, _ = date.today().isocalendar()
    week_id = (args.week or f"{year}-W{week:02d}").upper()
    directory = weekly.weekly_dir(args.root, week_id)
    if not (directory / weekly.WEEKLY_FILE).is_file():
        items = weekly.week_items(args.root, week_id, channel)
        picked = weekly.select(items, series, include_unapproved=args.include_unapproved)
        weekly.write_plan(args.root, week_id, picked, series)
        print(f"{week_id}：從 {len(items)} 支 Short 選 {len(picked)} 則 → {directory / weekly.PLAN_MD}")
    result = _advance(directory, channel, args)
    return result.exit_code


def run(args: argparse.Namespace) -> int:
    return run_daily(args) if args.mode == "daily" else run_weekly(args)
