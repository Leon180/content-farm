"""Machine-wide heavy queue: priority order, dead tickets, resource gate, re-entry for children."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from content_farm.lanes import queue as q


@pytest.fixture(autouse=True)
def _real_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(q.SLOT_ENV, raising=False)
    monkeypatch.setattr(q, "POLL_SECONDS", 0.01)


def idle_gate(**kw) -> q.Gate:
    return q.Gate(busy=lambda pattern: [], free=lambda: 90, sleep=time.sleep, **kw)


def _write(queue_dir: Path, ticket: q.Ticket) -> None:
    import json
    from dataclasses import asdict

    queue_dir.mkdir(parents=True, exist_ok=True)
    (queue_dir / f"{ticket.id}.json").write_text(json.dumps(asdict(ticket)), encoding="utf-8")


def test_priority_shorts_then_closest_to_done(tmp_path):
    a = q.Ticket("long-early", "long", 0.2, enqueued_at="2026-10-18T01:00:00+00:00")
    b = q.Ticket("long-late", "long", 0.8, enqueued_at="2026-10-18T02:00:00+00:00")
    c = q.Ticket("hn-short", "short", 0.0, enqueued_at="2026-10-18T03:00:00+00:00")
    d = q.Ticket("misc", "other", 0.9, enqueued_at="2026-10-18T00:00:00+00:00")
    for t in (a, b, c, d):
        _write(tmp_path, t)
    assert [t.job for t in q.tickets(tmp_path)] == ["hn-short", "long-late", "long-early", "misc"]


def test_dead_tickets_are_pruned(tmp_path):
    _write(tmp_path, q.Ticket("ghost", pid=999_999_999))
    assert q.tickets(tmp_path) == []
    assert not list(tmp_path.glob("*.json"))


def test_slot_sets_env_and_records_history(tmp_path):
    with q.heavy_slot(q.Ticket("job1"), lambda _: None, gate=idle_gate(), queue_dir=tmp_path) as waited:
        assert os.environ[q.SLOT_ENV] and waited >= 0
        assert q.status(tmp_path)[0]["holding"]
    assert q.SLOT_ENV not in os.environ and q.status(tmp_path) == []
    assert (tmp_path / "history.jsonl").read_text(encoding="utf-8").count('"job1"') == 2


def test_child_reentry_does_not_deadlock(tmp_path):
    with q.heavy_slot(q.Ticket("parent"), lambda _: None, gate=idle_gate(), queue_dir=tmp_path):
        with q.heavy_slot(q.Ticket("child"), lambda _: None, gate=idle_gate(max_wait_s=0), queue_dir=tmp_path) as w:
            assert w == 0.0


def test_waits_for_outside_heavy_process_and_memory(tmp_path):
    states = iter([[123], [], [], []])
    frees = iter([30, 80, 80])
    logs = []
    gate = q.Gate(busy=lambda p: next(states), free=lambda: next(frees), sleep=lambda s: None)
    with q.heavy_slot(q.Ticket("job"), logs.append, gate=gate, queue_dir=tmp_path):
        pass
    assert any("outside the queue" in m for m in logs) and any("free memory 30%" in m for m in logs)


def test_times_out(tmp_path):
    gate = q.Gate(busy=lambda p: [1], free=lambda: 90, sleep=lambda s: None, max_wait_s=-1)
    with pytest.raises(q.QueueTimeout):
        with q.heavy_slot(q.Ticket("job"), lambda _: None, gate=gate, queue_dir=tmp_path):
            pass
    assert not list(tmp_path.glob("*.json"))


def test_second_job_waits_for_the_holder_then_runs(tmp_path):
    order: list[str] = []
    release = threading.Event()

    def holder():
        with q.heavy_slot(q.Ticket("first"), lambda _: None, gate=idle_gate(), queue_dir=tmp_path):
            order.append("first-start")
            release.wait(2)
            order.append("first-end")

    thread = threading.Thread(target=holder)
    thread.start()
    while "first-start" not in order:
        time.sleep(0.01)
    q.os.environ.pop(q.SLOT_ENV, None)          # the thread's env flag is process-wide; this is "another process"
    threading.Timer(0.1, release.set).start()
    with q.heavy_slot(q.Ticket("second"), lambda _: None, gate=idle_gate(), queue_dir=tmp_path):
        order.append("second-start")
    thread.join()
    assert order == ["first-start", "first-end", "second-start"]
