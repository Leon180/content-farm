"""Publish slots (fractional cadence) and backlog picking."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from content_farm.production.channels import load_channel
from content_farm.production.schedule import Backlog, Topic, _count, load_backlog, plan_week, slots_for_week


def test_fractional_cadence_averages_exactly() -> None:
    assert sum(_count(0.5, w) for w in range(100)) == 50
    assert sum(_count(1.0, w) for w in range(10)) == 10
    assert sum(_count(3.0, w) for w in range(4)) == 12
    assert all(_count(0.5, w) in (0, 1) for w in range(20))


def test_chipcat_week_has_one_long_two_shorts_in_taipei_time() -> None:
    slots = slots_for_week(load_channel("chipcat"), 2026, 43)
    kinds = sorted(slot.kind for slot in slots)
    assert kinds == ["long", "short", "short"]
    long_slot = next(slot for slot in slots if slot.kind == "long")
    assert long_slot.publish_at.isoformat() == "2026-10-22T19:00:00+08:00"
    assert long_slot.start_by == date(2026, 10, 15)


def test_half_rate_channel_alternates_weeks() -> None:
    yokai = load_channel("yokai")
    longs = [sum(s.kind == "long" for s in slots_for_week(yokai, 2026, w)) for w in range(40, 46)]
    assert sorted(set(longs)) == [0, 1] and sum(longs) == 3


def _topic(id_: str, status: str, **kw: object) -> Topic:
    return Topic(id=id_, title=id_, status=status, **kw)


def test_plan_prefers_ready_then_deadline_then_priority() -> None:
    chipcat = load_channel("chipcat")
    backlog = Backlog(channel="chipcat", topics=(
        _topic("idea-urgent", "idea", priority=5),
        _topic("ready-low", "ready", priority=1),
        _topic("ready-high", "ready", priority=5),
        _topic("done", "published"),
    ))
    plan = plan_week(chipcat, backlog, 2026, 43, today=date(2026, 10, 1))
    long_pick = next(a for a in plan if a.slot.kind == "long")
    assert long_pick.topic is not None and long_pick.topic.id == "ready-high"
    assert long_pick.warning == ""


def test_late_slot_only_takes_ready_topics() -> None:
    chipcat = load_channel("chipcat")
    backlog = Backlog(channel="chipcat", topics=(_topic("research", "researching"),))
    plan = plan_week(chipcat, backlog, 2026, 43, today=date(2026, 10, 20))
    long_pick = next(a for a in plan if a.slot.kind == "long")
    assert long_pick.topic is None and "start date passed" in long_pick.warning


def test_expired_deadline_is_skipped() -> None:
    chipcat = load_channel("chipcat")
    backlog = Backlog(channel="chipcat", topics=(
        _topic("stale-news", "ready", deadline=date(2026, 10, 1)),))
    plan = plan_week(chipcat, backlog, 2026, 43, today=date(2026, 9, 1))
    assert all(a.topic is None for a in plan)


def test_repo_backlog_loads(tmp_path: Path) -> None:
    backlog = load_backlog("chipcat")
    assert any(t.id == "cowos" for t in backlog.topics)
    assert any(t.id == "committee-money" for t in load_backlog("cel").topics)
    assert load_backlog("cel", channels_dir=tmp_path).topics == ()  # no file → empty backlog
