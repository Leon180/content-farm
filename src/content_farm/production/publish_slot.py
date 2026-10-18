"""Suggested release time per video, from the channel's ``publish:`` section (Leon 2026-10-18,
research/upload-timing-2026-10.md: the windows are 🟡 starting guesses — no Taiwan hour-by-hour
data exists — to be replaced by Studio's 「觀眾上線時間」 report once the channel has data).

Rules: one long video per channel per day, on the channel's long days, at the start of its window;
Shorts in their daily windows, at most ``per_day`` and at least ``min_gap_hours`` apart;
time-sensitive news (``urgent``) goes out as soon as the gap allows.
Analytics override: ``channels/analytics/<code>.json`` ({"long": {...}, "shorts": {...}} with the
same fields as ``publish:``) replaces the yaml windows when present.
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from content_farm.production.channels import CHANNELS_DIR

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_WINDOW = r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$"
SCHEDULE_FILE = "production.schedule.json"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LongSlots(_Strict):
    days: tuple[str, ...] = Field(min_length=1)
    window: str = Field(pattern=_WINDOW)

    @field_validator("days")
    @classmethod
    def _days(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        bad = [d for d in value if d not in WEEKDAYS]
        if bad:
            raise ValueError(f"days must be among {WEEKDAYS}, got {bad}")
        return value


class ShortSlots(_Strict):
    days: tuple[str, ...] = WEEKDAYS
    windows: tuple[str, ...] = Field(min_length=1)
    per_day: int = Field(ge=1, le=10)
    min_gap_hours: float = Field(ge=0, le=24)

    @field_validator("windows")
    @classmethod
    def _windows(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        import re

        bad = [w for w in value if not re.match(_WINDOW, w)]
        if bad:
            raise ValueError(f"windows must look like 20:00-21:00, got {bad}")
        return value


class PublishPlan(_Strict):
    timezone: str = "Asia/Taipei"
    long: LongSlots | None = None
    shorts: ShortSlots | None = None
    urgent_news_asap: bool = False
    source: str = ""          # where the windows come from (research doc / analytics export)


def _start(window: str) -> time:
    hour, minute = window.split("-")[0].split(":")
    return time(int(hour), int(minute))


def load_plan(code: str, channels_dir: Path = CHANNELS_DIR) -> PublishPlan | None:
    import yaml

    raw = yaml.safe_load((channels_dir / f"{code}.yaml").read_text(encoding="utf-8")).get("publish")
    if raw is None:
        return None
    override = channels_dir / "analytics" / f"{code}.json"
    if override.is_file():
        data = json.loads(override.read_text(encoding="utf-8"))
        raw = {**raw, **{k: data[k] for k in ("long", "shorts") if k in data}, "source": f"analytics:{override.name}"}
    return PublishPlan.model_validate(raw)


def _same_day(a: datetime, b: datetime) -> bool:
    return a.date() == b.date()


def suggest(plan: PublishPlan, kind: str, now: datetime, taken: list[datetime], *, urgent: bool = False,
            horizon_days: int = 21) -> datetime:
    """Earliest allowed release after ``now`` that does not clash with ``taken`` (same channel, same kind)."""
    zone = ZoneInfo(plan.timezone)
    now = now.astimezone(zone)
    taken = [t.astimezone(zone) for t in taken]
    if kind == "long":
        if plan.long is None:
            raise ValueError("channel has no publish.long")
        for offset in range(horizon_days + 1):
            day = (now + timedelta(days=offset)).date()
            when = datetime.combine(day, _start(plan.long.window), tzinfo=zone)
            if WEEKDAYS[day.weekday()] in plan.long.days and when > now and not any(_same_day(when, t) for t in taken):
                return when
        raise ValueError(f"no long slot in the next {horizon_days} days")
    if plan.shorts is None:
        raise ValueError("channel has no publish.shorts")
    gap = timedelta(hours=plan.shorts.min_gap_hours)
    if urgent and plan.urgent_news_asap:
        when = (now + timedelta(minutes=15 - now.minute % 15)).replace(second=0, microsecond=0)
        while any(abs(when - t) < gap for t in taken) or sum(_same_day(when, t) for t in taken) >= plan.shorts.per_day:
            when += timedelta(minutes=15)
        return when
    for offset in range(horizon_days + 1):
        day = (now + timedelta(days=offset)).date()
        if WEEKDAYS[day.weekday()] not in plan.shorts.days:
            continue
        for window in plan.shorts.windows:
            when = datetime.combine(day, _start(window), tzinfo=zone)
            if when <= now or sum(_same_day(when, t) for t in taken) >= plan.shorts.per_day:
                continue
            if all(abs(when - t) >= gap for t in taken):
                return when
    raise ValueError(f"no Shorts slot in the next {horizon_days} days")


def taken_slots(root: Path, channel: str, kind: str, *, exclude: Path | None = None) -> list[datetime]:
    """Release times already given to other runs of this channel under ``root`` (output/)."""
    out = []
    for path in root.glob(f"*/{SCHEDULE_FILE}"):
        if exclude is not None and path.parent.resolve() == exclude.resolve():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("channel") == channel and data.get("kind", "long") == kind and data.get("publish_at"):
            out.append(datetime.fromisoformat(data["publish_at"]))
    return out


def peek(run_dir: Path, channel: str, kind: str, *, now: datetime) -> datetime | None:
    """The slot ``ensure_schedule`` would pick, without writing it (preview kits)."""
    path = run_dir / SCHEDULE_FILE
    if path.is_file() and json.loads(path.read_text(encoding="utf-8")).get("publish_at"):
        return datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["publish_at"])
    plan = load_plan(channel)
    if plan is None or (kind == "long" and plan.long is None) or (kind == "short" and plan.shorts is None):
        return None
    return suggest(plan, kind, now, taken_slots(run_dir.parent, channel, kind, exclude=run_dir))


def ensure_schedule(run_dir: Path, channel: str, kind: str, *, now: datetime, urgent: bool = False) -> datetime | None:
    """Keep a schedule someone set; otherwise write the suggested slot. None when the channel has no plan."""
    path = run_dir / SCHEDULE_FILE
    if path.is_file() and json.loads(path.read_text(encoding="utf-8")).get("publish_at"):
        return datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["publish_at"])
    plan = load_plan(channel)
    if plan is None:
        return None
    when = suggest(plan, kind, now, taken_slots(run_dir.parent, channel, kind, exclude=run_dir), urgent=urgent)
    path.write_text(json.dumps({"publish_at": when.isoformat(), "channel": channel, "kind": kind, "suggested": True,
                                "basis": plan.source or "channels yaml publish:"}, ensure_ascii=False), encoding="utf-8")
    return when
