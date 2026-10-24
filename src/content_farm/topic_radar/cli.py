"""``produce.py radar --channel <c> | --all`` — one day's candidates with demand evidence, per channel.

Writes ``output/radar/<date>/<channel>.json`` (and ``SUMMARY.md`` with --all). Safe to run daily: answers are
cached on disk, YouTube quota is capped by ``--youtube-budget``, and radar days older than 30 days are deleted.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from content_farm.config import Settings
from content_farm.topic_radar import store
from content_farm.topic_radar.build import Notes, build_channel
from content_farm.topic_radar.config import CHANNEL_CODES, load_radar_config
from content_farm.topic_radar.http import RadarHttp
from content_farm.topic_radar.models import ChannelRadar
from content_farm.topic_radar.summary import render_summary
from content_farm.topic_radar.youtube import AuthStatus, YouTubeClient, build_auth

REPO = Path(__file__).resolve().parents[3]
CACHE_DIR = Path(".cache/radar")


def add_parser(sub: argparse._SubParsersAction) -> None:
    radar = sub.add_parser("radar", help="topic radar: candidates + demand evidence from official public sources")
    target = radar.add_mutually_exclusive_group(required=True)
    target.add_argument("--channel", choices=CHANNEL_CODES)
    target.add_argument("--all", action="store_true", help="every channel, and write SUMMARY.md")
    radar.add_argument("--root", type=Path, default=None, help="output root (default output/radar)")
    radar.add_argument("--env-file", type=Path, default=None, help="default <repo>/.env (read by the program only)")
    radar.add_argument("--no-youtube", action="store_true", help="skip YouTube (no quota spent)")
    radar.add_argument("--youtube-budget", type=int, default=6000, help="max YouTube quota units this run (daily quota 10,000)")
    radar.add_argument("--top", type=int, default=3, help="candidates per channel in SUMMARY.md")
    radar.add_argument("--no-cache", action="store_true", help="ignore cached answers")


def _youtube(http: RadarHttp, settings: Settings, args: argparse.Namespace) -> tuple[YouTubeClient | None, AuthStatus]:
    if args.no_youtube:
        return None, AuthStatus("none", False, "skipped (--no-youtube)")
    auth, status = build_auth(
        http, client_id=settings.youtube_client_id.get_secret_value(),
        client_secret=settings.youtube_client_secret.get_secret_value(),
        refresh_token=settings.youtube_refresh_token.get_secret_value(),
        api_key=settings.youtube_api_key.get_secret_value())
    return (YouTubeClient(http, auth, budget_units=args.youtube_budget) if auth else None), status


def _note(status: AuthStatus) -> str:
    return f"{status.mode}（{'可用' if status.ok else '不可用'}：{status.detail}）"


def run(args: argparse.Namespace) -> int:
    env_file = args.env_file or REPO / ".env"
    settings = Settings(_env_file=env_file if env_file.is_file() else None)
    root = args.root or store.default_root()
    now = datetime.now(timezone.utc).astimezone()
    http = RadarHttp(cache_dir=REPO / CACHE_DIR, default_ttl=0 if args.no_cache else 6 * 3600)
    try:
        for path in store.purge_expired(root, now.date(), REPO / CACHE_DIR):
            print(f"[purge] {path}")
        youtube, status = _youtube(http, settings, args)
        print(f"[youtube auth] {_note(status)}")
        codes = list(CHANNEL_CODES) if args.all else [args.channel]
        radars: list[ChannelRadar] = []
        for code in codes:
            radar = build_channel(load_radar_config(code), http, youtube, now, Notes())
            radars.append(radar)
            path = store.write_channel(root, radar)
            top = radar.candidates[0].title_draft if radar.candidates else "（無候選）"
            print(f"[radar] {code}: {len(radar.candidates)} candidates → {path}  top: {top}")
        if args.all:
            summary = store.day_dir(root, now.date().isoformat()) / "SUMMARY.md"
            summary.write_text(render_summary(radars, now.date().isoformat(), _note(status), args.top), encoding="utf-8")
            print(f"[summary] {summary}")
        print(f"[calls] network {dict(http.network)}  cache hits {dict(http.cached)}  "
              f"youtube units {youtube.units if youtube else 0}")
    finally:
        http.close()
    return 0
