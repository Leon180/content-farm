"""Publish calendar and topic backlog per channel.

Slots: ``cadence.long_per_week`` / ``shorts_per_week`` may be fractional
(0.5 = every other ISO week); the count for week *w* is
``floor((w+1)·rate) − floor(w·rate)`` so the long-run average is exact and
deterministic. Topics: ``channels/backlog/<code>.yaml`` holds a list of
topics; ``plan_week`` fills each slot with the most urgent topic that is far
enough along to make its production start date (``publish − lead_days``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field

from content_farm.production.channels import CHANNELS_DIR, Channel

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
READY_ORDER = {"ready": 0, "researching": 1, "idea": 2}  # anything else is not schedulable


class Topic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern="^[a-z0-9][a-z0-9_-]{1,47}$")
    title: str
    kind: str = Field(default="long", pattern="^(long|short)$")
    status: str = Field(pattern="^(idea|researching|ready|in_production|published|dropped)$")
    priority: int = Field(default=3, ge=1, le=5)          # 5 = most important
    deadline: date | None = None                           # news-pegged topics
    category: str = ""
    notes: str = ""


class Backlog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    topics: tuple[Topic, ...] = ()


@dataclass(frozen=True)
class Slot:
    channel: str
    kind: str          # long | short
    publish_at: datetime
    start_by: date     # production must start by this day


@dataclass(frozen=True)
class Assignment:
    slot: Slot
    topic: Topic | None
    warning: str = ""


def _count(rate: float, week_ordinal: int) -> int:
    return math.floor((week_ordinal + 1) * rate + 1e-9) - math.floor(week_ordinal * rate + 1e-9)


def _week_ordinal(year: int, week: int) -> int:
    return date.fromisocalendar(year, week, 1).toordinal() // 7


def _spread_days(count: int) -> tuple[str, ...]:
    if count <= 0:
        return ()
    step = 7 / count
    return tuple(WEEKDAYS[int(i * step) % 7] for i in range(count))


def _days_for(days: tuple[str, ...], count: int) -> list[str]:
    pool = days or _spread_days(count)
    return [pool[i % len(pool)] for i in range(count)]


def slots_for_week(channel: Channel, year: int, week: int) -> list[Slot]:
    cadence = channel.cadence
    zone = ZoneInfo(cadence.timezone)
    hour, minute = (int(part) for part in cadence.publish_time.split(":"))
    ordinal = _week_ordinal(year, week)
    slots: list[Slot] = []
    for kind, rate, days in (("long", cadence.long_per_week, cadence.publish_days),
                             ("short", cadence.shorts_per_week, cadence.shorts_days)):
        for day in _days_for(days, _count(rate, ordinal)):
            when = date.fromisocalendar(year, week, WEEKDAYS.index(day) + 1)
            publish_at = datetime.combine(when, time(hour, minute), tzinfo=zone)
            slots.append(Slot(channel.code, kind, publish_at,
                              when - timedelta(days=cadence.lead_days if kind == "long" else 2)))
    return sorted(slots, key=lambda slot: slot.publish_at)


def load_backlog(code: str, channels_dir: Path = CHANNELS_DIR) -> Backlog:
    path = channels_dir / "backlog" / f"{code}.yaml"
    if not path.is_file():
        return Backlog(channel=code)
    backlog = Backlog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    if backlog.channel != code:
        raise ValueError(f"{path}: channel {backlog.channel!r} does not match file name")
    return backlog


def _urgency(topic: Topic) -> tuple:
    return (READY_ORDER[topic.status], topic.deadline or date.max, -topic.priority, topic.id)


def plan_week(channel: Channel, backlog: Backlog, year: int, week: int, today: date) -> list[Assignment]:
    """Fill the week's slots; a slot whose start date has passed only takes 'ready' topics."""
    pool = [t for t in backlog.topics if t.status in READY_ORDER]
    taken: set[str] = set()
    plan: list[Assignment] = []
    for slot in slots_for_week(channel, year, week):
        late = slot.start_by < today
        candidates = sorted(
            (t for t in pool if t.kind == slot.kind and t.id not in taken
             and (t.status == "ready" or not late)
             and (t.deadline is None or t.deadline >= slot.publish_at.date())),
            key=_urgency,
        )
        if not candidates:
            reason = "start date passed and nothing ready" if late else "backlog has no topic for this slot"
            plan.append(Assignment(slot, None, reason))
            continue
        topic = candidates[0]
        taken.add(topic.id)
        warning = "" if topic.status == "ready" else f"topic is only '{topic.status}'"
        plan.append(Assignment(slot, topic, warning))
    return plan
