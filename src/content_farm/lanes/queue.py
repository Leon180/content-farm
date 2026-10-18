"""One machine-wide queue in front of every step (Leon 2026-10-18), shared by every channel,
worker and ``scripts/heavy`` caller.

A ticket = one video × one step (``job``) with its resource need (``lanes.resources.Need``).
``slot(ticket, need)`` waits until ``resources.decide`` says go, then — for local work — takes
its locks all-or-nothing in the fixed order gpu → render → local_tts (``heavy.lock`` shared or
exclusive for the GPU; the legacy ``render.lock`` / ``local_tts.lock`` at their old paths, so
branches without this queue still see the machine as busy and their holders make us wait), and
checks no heavy process outside the queue is running. Cloud-lane work only waits for memory.

While waiting the ticket records why (``reason``); ``status()`` / ``scripts/heavy --status`` /
``produce.py queue`` show it. A need larger than the machine fails at once (``ImpossibleNeed``);
a wait longer than ``notify_after_s`` sends one orch-mail to the orchestrator.
The holder exports ``CF_HEAVY_SLOT`` so its children (TTS worker, render scripts) never re-queue.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from content_farm import paths
from content_farm.lanes import resources as res

SLOT_ENV = "CF_HEAVY_SLOT"


def default_queue_dir() -> Path:
    """Resolved per call (``CF_HEAVY_QUEUE_DIR``), so tests can redirect it after import."""
    return paths.heavy_queue_dir()


class QueueTimeout(RuntimeError):
    """Waited longer than ``max_wait_s``."""


class ImpossibleNeed(RuntimeError):
    """The need can never be met on this machine."""


@dataclass(frozen=True)
class Ticket:
    job: str                    # "<channel>/<run>:<step>" or a scripts/heavy --label
    kind: str = "long"          # short | long | other (priority: short, then long closest to done)
    progress: float = 0.0
    pid: int = field(default_factory=os.getpid)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    enqueued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def priority(self) -> tuple[int, float, str]:
        return ({"short": 0, "long": 1}.get(self.kind, 2), -self.progress, self.enqueued_at)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _ticket_fields() -> set[str]:
    return set(Ticket.__dataclass_fields__)


def records(queue_dir: Path | None = None, *, alive: Callable[[int], bool] = _alive) -> list[dict]:
    """Live ticket records (ticket fields + state, reason, need, since); dead ones are removed."""
    out = []
    for path in sorted((queue_dir or default_queue_dir()).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            Ticket(**{k: v for k, v in data.items() if k in _ticket_fields()})
        except (OSError, ValueError, TypeError):
            path.unlink(missing_ok=True)
            continue
        if not alive(int(data["pid"])):
            path.unlink(missing_ok=True)
            continue
        out.append(data)
    return sorted(out, key=lambda d: Ticket(**{k: v for k, v in d.items() if k in _ticket_fields()}).priority())


def tickets(queue_dir: Path | None = None, *, alive: Callable[[int], bool] = _alive) -> list[Ticket]:
    return [Ticket(**{k: v for k, v in d.items() if k in _ticket_fields()}) for d in records(queue_dir, alive=alive)]


def status(queue_dir: Path | None = None, now: float | None = None) -> list[dict]:
    now = now or time.time()
    queue_dir = queue_dir or default_queue_dir()
    return [{**r, "holding": r.get("state") == "running", "waited_s": int(now - r.get("since", now))}
            for r in records(queue_dir)]


def _write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _as_job(record: dict) -> res.Job:
    need = res.Need(**{**record.get("need", {}), "locks": tuple(record.get("need", {}).get("locks", ()))})
    ticket = Ticket(**{k: v for k, v in record.items() if k in _ticket_fields()})
    return res.Job(record["id"], record["job"], need, ticket.priority(), record.get("state", "waiting"),
                   float(record.get("since", time.time())), bool(record.get("fits", True)))


# --- locks: all or nothing, fixed order -------------------------------------------------------

def legacy_locks() -> tuple[Path, ...]:
    """runner.render_lock (``render.lock``) and voice.local_worker (``local_tts.lock``) before the queue."""
    return (paths.render_lock_path(), paths.local_tts_lock_path())


def _lock_plan(need: res.Need, queue_dir: Path) -> list[tuple[Path, int]]:
    render, local_tts = legacy_locks()
    plan: list[tuple[Path, int]] = []
    if need.gpu != "none":
        plan.append((queue_dir / "heavy.lock", fcntl.LOCK_EX if need.gpu == "exclusive" else fcntl.LOCK_SH))
    if "render" in need.locks or need.gpu == "exclusive":
        plan.append((render, fcntl.LOCK_EX))
    if "local_tts" in need.locks:
        plan.append((local_tts, fcntl.LOCK_EX))
    return plan          # already in LOCK_ORDER: gpu, render, local_tts


def _release(handles: list[IO[str]]) -> None:
    for handle in handles:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def take_locks(plan: list[tuple[Path, int]]) -> list[IO[str]] | None:
    held: list[IO[str]] = []
    for path, mode in plan:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a")
        try:
            fcntl.flock(handle, mode | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            _release(held)
            return None
        held.append(handle)
    return held


# --- environment (injectable for tests) ------------------------------------------------------

@dataclass
class Env:
    probe: Callable[[], res.Probe] = res.probe_machine
    foreign: Callable[[set[int]], list[tuple[int, str]]] | None = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.time
    notify: Callable[[str, str], None] | None = None
    config: res.Config | None = None


def default_foreign(config: res.Config) -> Callable[[set[int]], list[tuple[int, str]]]:
    patterns = [p["pattern"] for p in config.raw.get("processes", [])]
    return lambda ours: res.foreign_heavy(patterns, ours)


def orch_mail(summary: str, body: str) -> None:
    """One report to the orchestrator's personal pointer store; never raises."""
    script = paths.orch_mail_script()
    if not script.is_file():
        return
    note = default_queue_dir() / f"stall-{uuid.uuid4().hex[:8]}.md"
    note.write_text(f"## TL;DR\n{summary}\n\n{body}\n", encoding="utf-8")
    try:
        subprocess.run(["python3", str(script), "put", "--kind", "report", "--from", "heavy-queue",
                        "--to", "orchestrator", "--summary", summary[:100], "--file", str(note)],
                       env={**os.environ, "ORCH_MAIL_DIR": str(paths.orch_mail_dir())}, capture_output=True, timeout=30,
                       check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _wait_reasons(me: dict, queue_dir: Path, env: Env, config: res.Config) -> tuple[list[str], bool, list]:
    others = [r for r in records(queue_dir) if r["id"] != me["id"]]
    probe = env.probe()
    job = _as_job(me)
    reasons = res.decide(job, [_as_job(r) for r in others], probe, config, env.clock())
    fits = not any(r.startswith(("memory", "swap", "load", "memory pressure")) for r in reasons)
    if reasons or not job.need.local:
        return reasons, fits, []
    handles = take_locks(_lock_plan(job.need, queue_dir))
    if handles is None:
        return ["a lock (gpu/render/local_tts) is held, possibly by a branch without this queue"], fits, []
    ours = {int(r["pid"]) for r in others if r.get("state") == "running"}
    busy = (env.foreign or default_foreign(config))(ours)
    if busy:
        _release(handles)
        return [f"heavy process outside the queue: {busy[0][1]} (pid {busy[0][0]})"], fits, []
    return [], fits, handles


def _unit_test_bypass() -> bool:
    """Unit tests of other modules must not depend on this machine's load (tests of the queue pass
    an ``Env``). Honoured only inside pytest, so production code cannot switch admission off."""
    return os.environ.get("CF_ADMISSION_UNIT_TEST") == "1" and "PYTEST_CURRENT_TEST" in os.environ


@contextmanager
def slot(ticket: Ticket, need: res.Need, log: Callable[[str], None] = print, *, env: Env | None = None,
         queue_dir: Path | None = None) -> Iterator[float]:
    """Wait for admission (and locks for local work); yields the seconds waited."""
    if need.local and os.environ.get(SLOT_ENV):        # a parent holds the local slot for us
        yield 0.0
        return
    if env is None and _unit_test_bypass():
        yield 0.0
        return
    env = env or Env()
    queue_dir = queue_dir or default_queue_dir()
    config = env.config or res.load_config()
    why = res.impossible(need, env.probe(), config)
    if why:
        raise ImpossibleNeed(f"{ticket.job}: {why}")
    queue_dir.mkdir(parents=True, exist_ok=True)
    path = queue_dir / f"{ticket.id}.json"
    started = env.clock()
    me = {**asdict(ticket), "need": {**asdict(need), "locks": list(need.locks)}, "state": "waiting",
          "since": started, "reason": "", "fits": True}
    _write(path, me)
    handles: list[IO[str]] = []
    notified, last = False, ""
    try:
        while True:
            reasons, fits, handles = _wait_reasons(me, queue_dir, env, config)
            if not reasons:
                break
            reason = "；".join(reasons)
            me = {**me, "reason": reason, "fits": fits}
            _write(path, me)
            waited = env.clock() - started
            if reason != last:
                log(f"⏳ {ticket.job}: {reason}")
                last = reason
            if not notified and waited >= config.notify_after_s:
                (env.notify or orch_mail)(f"{ticket.job} 排隊 {int(waited // 60)} 分：{reason[:60]}",
                                          json.dumps(status(queue_dir), ensure_ascii=False, indent=1, default=str))
                notified = True
            if waited > config.max_wait_s:
                raise QueueTimeout(f"{ticket.job}: waited {waited:.0f}s ({reason})")
            env.sleep(config.poll_seconds)
        waited = round(env.clock() - started, 1)
        me = {**me, "state": "running", "since": env.clock(), "reason": "", "waited_s": waited}
        _write(path, me)
        if need.local:
            os.environ[SLOT_ENV] = ticket.id
        _record(queue_dir, ticket, "start", waited)
        yield waited
    finally:
        if handles or (need.local and os.environ.get(SLOT_ENV) == ticket.id):
            os.environ.pop(SLOT_ENV, None)
        _release(handles)
        if me.get("state") == "running":
            _record(queue_dir, ticket, "end", round(env.clock() - started, 1))
        path.unlink(missing_ok=True)


EXCLUSIVE = res.Need(mem_gb=8.0, gpu="exclusive", cpu_cores=4, locks=("render",))


@contextmanager
def heavy_slot(ticket: Ticket, log: Callable[[str], None] = print, *, need: res.Need | None = None,
               env: Env | None = None, queue_dir: Path | None = None) -> Iterator[float]:
    """The old single-slot API: exclusive local work (default need ``EXCLUSIVE``)."""
    with slot(ticket, need or EXCLUSIVE, log, env=env, queue_dir=queue_dir) as waited:
        yield waited


def _record(queue_dir: Path, ticket: Ticket, event: str, seconds: float) -> None:
    with (queue_dir / "history.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event,
                              "job": ticket.job, "kind": ticket.kind, "seconds": seconds}) + "\n")
