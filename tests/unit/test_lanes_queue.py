"""The machine-wide queue loop: waiting state, release, legacy locks, children, timeout, notification."""

from __future__ import annotations

import fcntl
import json
import os
import threading
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from content_farm.lanes import queue as q
from content_farm.lanes import resources as res

CFG = res.Config(margin_gb=6, poll_seconds=0.01, max_wait_s=5, notify_after_s=1000)
ROOMY = res.Probe(32, 28, 10, 2, 10)
VOICE = res.Need(18, "exclusive", 2, ("local_tts",))


@pytest.fixture(autouse=True)
def _real_queue(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(q.SLOT_ENV, raising=False)
    legacy = (tmp_path / "legacy" / "render.lock", tmp_path / "legacy" / "local_tts.lock")
    monkeypatch.setattr(q, "legacy_locks", lambda: legacy)


def env(probe=ROOMY, foreign=lambda ours: [], **kw) -> q.Env:
    return q.Env(probe=lambda: probe if not callable(probe) else probe(), foreign=foreign,
                 config=kw.pop("config", CFG), **kw)


def _write(queue_dir: Path, ticket: q.Ticket, need: res.Need, state: str = "waiting", since: float | None = None):
    queue_dir.mkdir(parents=True, exist_ok=True)
    record = {**asdict(ticket), "need": {**asdict(need), "locks": list(need.locks)}, "state": state,
              "since": since or time.time(), "fits": True}
    (queue_dir / f"{ticket.id}.json").write_text(json.dumps(record), encoding="utf-8")


def test_unit_test_bypass_needs_pytest(monkeypatch):
    monkeypatch.setenv("CF_ADMISSION_UNIT_TEST", "1")
    assert q._unit_test_bypass()
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    assert not q._unit_test_bypass()                  # the flag alone never switches admission off


def test_priority_order_of_records(tmp_path):
    for name, kind, progress in (("long-early", "long", 0.2), ("long-late", "long", 0.8), ("hn", "short", 0.0),
                                 ("misc", "other", 0.9)):
        _write(tmp_path, q.Ticket(name, kind, progress), res.Need())
    assert [t.job for t in q.tickets(tmp_path)] == ["hn", "long-late", "long-early", "misc"]


def test_dead_tickets_are_pruned(tmp_path):
    _write(tmp_path, q.Ticket("ghost", pid=999_999_999), res.Need())
    assert q.tickets(tmp_path) == [] and not list(tmp_path.glob("*.json"))


def test_local_slot_sets_env_and_cloud_slot_does_not(tmp_path):
    with q.slot(q.Ticket("a:voice"), VOICE, lambda _: None, env=env(), queue_dir=tmp_path) as waited:
        assert os.environ[q.SLOT_ENV] and waited == 0
        assert q.status(tmp_path)[0]["holding"]
    assert q.SLOT_ENV not in os.environ and q.status(tmp_path) == []
    with q.slot(q.Ticket("a:gate_deck"), res.Need(0.6), lambda _: None, env=env(), queue_dir=tmp_path):
        assert q.SLOT_ENV not in os.environ
    assert (tmp_path / "history.jsonl").read_text(encoding="utf-8").count('"start"') == 2


def test_child_reentry_does_not_deadlock(tmp_path):
    with q.slot(q.Ticket("parent"), VOICE, lambda _: None, env=env(), queue_dir=tmp_path):
        with q.slot(q.Ticket("child"), VOICE, lambda _: None, env=env(config=res.Config(max_wait_s=0)),
                    queue_dir=tmp_path) as waited:
            assert waited == 0.0


def test_impossible_need_fails_without_queueing(tmp_path):
    with pytest.raises(q.ImpossibleNeed, match="can never run here"):
        with q.slot(q.Ticket("x"), res.Need(40), lambda _: None, env=env(), queue_dir=tmp_path):
            pass
    assert not list(tmp_path.glob("*.json"))


def test_waits_with_reason_then_runs_when_memory_returns(tmp_path):
    probes = iter([res.Probe(32, 10, 10, 2, 10)] * 3 + [ROOMY] * 10)
    logs = []
    with q.slot(q.Ticket("a:voice"), VOICE, logs.append, env=env(probe=lambda: next(probes)), queue_dir=tmp_path):
        pass
    assert any("memory" in m for m in logs)


def test_outside_heavy_process_holds_local_work(tmp_path):
    calls = iter([[(123, "ffmpeg -i x")], []])
    logs = []
    with q.slot(q.Ticket("a:assembly"), res.Need(2, locks=("render",)), logs.append,
                env=env(foreign=lambda ours: next(calls)), queue_dir=tmp_path):
        pass
    assert any("outside the queue: ffmpeg" in m for m in logs)


def test_legacy_lock_holder_blocks_and_slot_holds_legacy_locks(tmp_path):
    render, local_tts = q.legacy_locks()
    render.parent.mkdir(parents=True, exist_ok=True)
    old_code = render.open("w")                      # a branch without the queue: runner.render_lock
    fcntl.flock(old_code, fcntl.LOCK_EX)
    with pytest.raises(q.QueueTimeout, match="branch without this queue"):
        with q.slot(q.Ticket("new"), res.Need(2, locks=("render",)), lambda _: None,
                    env=env(config=res.Config(poll_seconds=0.01, max_wait_s=0.05)), queue_dir=tmp_path / "queue"):
            pass
    fcntl.flock(old_code, fcntl.LOCK_UN)
    old_code.close()
    holder = res.Need(18, "exclusive", 2, ("render", "local_tts"))       # GPU-exclusive no longer implies render
    with q.slot(q.Ticket("new"), holder, lambda _: None, env=env(), queue_dir=tmp_path / "queue"):
        for path in (render, local_tts):             # old code now sees the machine as busy
            probe = path.open("a")
            with pytest.raises(BlockingIOError):
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            probe.close()


def test_locks_all_or_nothing(tmp_path):
    render, local_tts = q.legacy_locks()
    local_tts.parent.mkdir(parents=True, exist_ok=True)
    holder = local_tts.open("w")
    fcntl.flock(holder, fcntl.LOCK_EX)
    plan = [(tmp_path / "heavy.lock", fcntl.LOCK_EX), (render, fcntl.LOCK_EX), (local_tts, fcntl.LOCK_EX)]
    assert q.take_locks(plan) is None
    probe = render.open("a")                           # the render lock it got first was given back
    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
    probe.close()
    holder.close()


def test_long_wait_sends_one_notification(tmp_path):
    clock = iter(range(0, 10_000, 100))
    sent = []
    probes = iter([res.Probe(32, 5, 10, 2, 10)] * 6 + [ROOMY] * 10)
    config = res.Config(poll_seconds=0, notify_after_s=250, max_wait_s=10_000)
    with q.slot(q.Ticket("a:voice"), VOICE, lambda _: None, queue_dir=tmp_path,
                env=env(probe=lambda: next(probes), clock=lambda: float(next(clock)), config=config,
                        notify=lambda summary, body: sent.append(summary), sleep=lambda s: None)):
        pass
    assert len(sent) == 1 and "a:voice" in sent[0]


def test_one_video_waiting_locally_does_not_stop_another_videos_cloud_step(tmp_path):
    release = threading.Event()
    order = []

    def video_a():
        with q.slot(q.Ticket("a:voice"), VOICE, lambda _: None, env=env(), queue_dir=tmp_path):
            order.append("a-voice")
            release.wait(2)

    thread = threading.Thread(target=video_a)
    thread.start()
    while "a-voice" not in order:
        time.sleep(0.01)
    q.os.environ.pop(q.SLOT_ENV, None)               # process-wide flag; this is "another video"
    with q.slot(q.Ticket("b:gate_deck"), res.Need(0.6), lambda _: None, env=env(), queue_dir=tmp_path):
        order.append("b-review")                       # cloud lane: runs while a holds the GPU
    release.set()
    thread.join()
    assert order == ["a-voice", "b-review"]


def test_tickets_carry_needs_and_provides_into_the_job(tmp_path):
    _write(tmp_path, q.Ticket("technews:voice", "short", needs="voice-ref:technews"), res.Need(1))
    record = q.records(tmp_path)[0]
    job = q._as_job(record)
    assert job.needs == "voice-ref:technews" and job.provides == ""


def test_voice_design_runs_past_a_starving_voice_ticket(tmp_path):
    starving = q.Ticket("technews/a:voice", "short", needs="voice-ref:technews")
    _write(tmp_path, starving, VOICE, since=time.time() - 3000)
    design = q.Ticket("technews:voice-design", provides="voice-ref:technews")
    with q.slot(design, res.Need(19.5, "exclusive", 2, ("local_tts",)), lambda m: None, env=env(), queue_dir=tmp_path):
        pass
    stranger = q.Ticket("yokai:illustrate")
    with pytest.raises(q.QueueTimeout):
        with q.slot(stranger, res.Need(7, "exclusive", 2), lambda m: None, env=env(), queue_dir=tmp_path):
            pass
