"""Radar output on disk: ``output/radar/<date>/<channel>.json`` plus the 30-day YouTube data rule."""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import date, timedelta
from pathlib import Path

from content_farm.topic_radar.models import ChannelRadar

RETENTION_DAYS = 30
YOUTUBE_CACHE_MAX_AGE = 8 * 86400      # longest cache TTL is 7 days; anything older is useless and far below the 30-day limit


def default_root() -> Path:
    """``output/radar`` in the checkout; ``CF_RADAR_DIR`` overrides it (tests point it at tmp)."""
    override = os.environ.get("CF_RADAR_DIR", "").strip()
    return Path(override).expanduser() if override else Path(__file__).resolve().parents[3] / "output" / "radar"


def day_dir(root: Path, day: str) -> Path:
    return root / day


def write_channel(root: Path, radar: ChannelRadar) -> Path:
    path = day_dir(root, radar.date) / f"{radar.channel}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(radar.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def latest_for(root: Path, channel: str, today: date, max_age_days: int = 7) -> Path | None:
    """The newest radar file for ``channel`` no older than ``max_age_days`` (what the topic stage reads)."""
    for offset in range(max_age_days + 1):
        path = day_dir(root, (today - timedelta(days=offset)).isoformat()) / f"{channel}.json"
        if path.is_file():
            return path
    return None


def purge_expired(root: Path, today: date, cache_dir: Path | None = None, now: float | None = None) -> list[Path]:
    """Delete radar days older than 30 days (YouTube API terms: stored data expires after 30 days) and stale
    YouTube cache files. Returns what was removed."""
    removed: list[Path] = []
    cutoff = today - timedelta(days=RETENTION_DAYS)
    if root.is_dir():
        for child in sorted(root.iterdir()):
            try:
                stamp = date.fromisoformat(child.name)
            except ValueError:
                continue
            if child.is_dir() and stamp < cutoff:
                shutil.rmtree(child)
                removed.append(child)
    youtube_cache = (cache_dir / "www.googleapis.com") if cache_dir else None
    if youtube_cache and youtube_cache.is_dir():
        limit = (now or time.time()) - YOUTUBE_CACHE_MAX_AGE
        for file in youtube_cache.glob("*.json"):
            if file.stat().st_mtime < limit:
                file.unlink()
                removed.append(file)
    return removed
