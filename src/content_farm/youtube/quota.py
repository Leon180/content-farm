"""Local YouTube Data API quota ledger.

The API has no endpoint that reports quota used, so usage is tracked locally.
The daily quota resets at midnight Pacific time and is shared by every channel
under the same Cloud project.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

VIDEOS_INSERT_COST = 1600
THUMBNAILS_SET_COST = 50
CHANNELS_LIST_COST = 1
FAILED_CALL_COST = 1  # booked for a rejected call (policy requested by orchestrator; real cost may differ)
DEFAULT_DAILY_LIMIT = 10_000

_PACIFIC = ZoneInfo("America/Los_Angeles")


def pacific_day(now: datetime | None = None) -> str:
    """Quota-day key (YYYY-MM-DD in Pacific time)."""
    moment = now or datetime.now(_PACIFIC)
    return moment.astimezone(_PACIFIC).strftime("%Y-%m-%d")


def upload_cost(*, has_thumbnail: bool) -> int:
    """Units for one video: channels.list check + insert (+ thumbnail)."""
    return CHANNELS_LIST_COST + VIDEOS_INSERT_COST + (THUMBNAILS_SET_COST if has_thumbnail else 0)


@dataclass(frozen=True)
class QuotaLedger:
    """Immutable view of units spent per Pacific day, persisted as JSON."""

    path: Path
    days: dict[str, int]
    limit: int = DEFAULT_DAILY_LIMIT

    @classmethod
    def load(cls, path: Path, limit: int = DEFAULT_DAILY_LIMIT) -> QuotaLedger:
        if not path.is_file():
            return cls(path=path, days={}, limit=limit)
        raw = json.loads(path.read_text(encoding="utf-8"))
        days = {str(k): int(v) for k, v in raw.get("days", {}).items()}
        return cls(path=path, days=days, limit=limit)

    def used(self, day: str) -> int:
        return self.days.get(day, 0)

    def remaining(self, day: str) -> int:
        return max(0, self.limit - self.used(day))

    def can_afford(self, day: str, cost: int) -> bool:
        return cost <= self.remaining(day)

    def spend(self, day: str, cost: int) -> QuotaLedger:
        """Return a new ledger with ``cost`` added and persist it."""
        updated = QuotaLedger(
            path=self.path,
            days={**self.days, day: self.used(day) + cost},
            limit=self.limit,
        )
        updated._save()
        return updated

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"days": self.days}, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
