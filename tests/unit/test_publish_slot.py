"""Suggested release times from channels/<code>.yaml publish:."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from content_farm.production.channels import load_all
from content_farm.production.publish_slot import (
    LongSlots, PublishPlan, ShortSlots, ensure_schedule, load_plan, suggest, taken_slots,
)

TPE = ZoneInfo("Asia/Taipei")
PLAN = PublishPlan(long=LongSlots(days=("thu",), window="20:00-21:00"),
                   shorts=ShortSlots(windows=("12:00-13:00", "20:00-21:00"), per_day=2, min_gap_hours=4),
                   urgent_news_asap=True)
MON = datetime(2026, 10, 19, 9, 0, tzinfo=TPE)      # a Monday


def test_every_channel_has_a_valid_publish_plan():
    for channel in load_all():
        assert load_plan(channel.code) is not None, channel.code


def test_long_goes_on_the_channel_day_at_window_start():
    assert suggest(PLAN, "long", MON, []) == datetime(2026, 10, 22, 20, 0, tzinfo=TPE)


def test_no_two_long_videos_same_day():
    first = datetime(2026, 10, 22, 20, 0, tzinfo=TPE)
    assert suggest(PLAN, "long", MON, [first]) == datetime(2026, 10, 29, 20, 0, tzinfo=TPE)


def test_shorts_per_day_and_gap():
    noon = datetime(2026, 10, 19, 12, 0, tzinfo=TPE)
    assert suggest(PLAN, "short", MON, []) == noon
    assert suggest(PLAN, "short", MON, [noon]) == datetime(2026, 10, 19, 20, 0, tzinfo=TPE)
    evening = datetime(2026, 10, 19, 20, 0, tzinfo=TPE)
    assert suggest(PLAN, "short", MON, [noon, evening]).date().day == 20      # per_day reached


def test_urgent_news_asap_respects_gap():
    now = datetime(2026, 10, 19, 15, 7, tzinfo=TPE)
    assert suggest(PLAN, "short", now, [], urgent=True) == datetime(2026, 10, 19, 15, 15, tzinfo=TPE)
    recent = datetime(2026, 10, 19, 14, 0, tzinfo=TPE)
    assert suggest(PLAN, "short", now, [recent], urgent=True) == datetime(2026, 10, 19, 18, 0, tzinfo=TPE)


def test_bad_plan_rejected():
    with pytest.raises(ValidationError):
        LongSlots(days=("someday",), window="20:00-21:00")
    with pytest.raises(ValidationError):
        ShortSlots(windows=("8pm",), per_day=1, min_gap_hours=1)


def test_ensure_schedule_writes_and_avoids_taken(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    (other / "production.schedule.json").write_text(json.dumps(
        {"publish_at": "2026-10-22T20:00:00+08:00", "channel": "chipcat", "kind": "long"}))
    run = tmp_path / "new"
    run.mkdir()
    when = ensure_schedule(run, "chipcat", "long", now=MON)
    assert when == datetime(2026, 10, 29, 20, 0, tzinfo=TPE)
    data = json.loads((run / "production.schedule.json").read_text(encoding="utf-8"))
    assert data["suggested"] and data["channel"] == "chipcat"
    assert ensure_schedule(run, "chipcat", "long", now=MON) == when             # kept once written
    assert len(taken_slots(tmp_path, "chipcat", "long")) == 2


def test_analytics_override(tmp_path):
    import shutil

    from content_farm.production.channels import CHANNELS_DIR

    shutil.copy(CHANNELS_DIR / "yokai.yaml", tmp_path / "yokai.yaml")
    (tmp_path / "analytics").mkdir()
    (tmp_path / "analytics" / "yokai.json").write_text(json.dumps({"long": {"days": ["sun"], "window": "10:00-12:00"}}))
    plan = load_plan("yokai", channels_dir=tmp_path)
    assert plan.long.days == ("sun",) and plan.source == "analytics:yokai.json"
