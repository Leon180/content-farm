"""One machine-wide priority queue for heavy local work, replacing the separate render lock,
``local_tts.lock`` and per-tool pgrep gates (Leon 2026-10-18).

Every heavy job — any channel, any worker — writes a ticket into ``QUEUE_DIR`` and waits until
1. it is first by priority among live tickets: HN Shorts / Shorts first, then the long video
   closest to done (``progress``), then first come;
2. it holds ``heavy.lock`` (flock — released by the OS if the holder dies);
3. no heavy process outside the queue is running (``BUSY_PATTERN``) and free memory is ≥ 50 %.

The holder exports ``CF_HEAVY_SLOT=<ticket>`` to its children, so a child (the TTS worker, a
render script) that asks for the slot again gets it at once instead of deadlocking.
``status()`` / ``produce.py queue`` show the queue.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

QUEUE_DIR = Path(os.environ.get("CF_HEAVY_QUEUE_DIR", Path.home() / ".cache" / "content-farm" / "heavy-queue"))
SLOT_ENV = "CF_HEAVY_SLOT"
# "ace" alone (as first drafted) matches unrelated processes (workspace, interface…); name ACE-Step exactly.
BUSY_PATTERN = "mlx_video|mflux|ffmpeg|qwen3-tts|qwen3_tts|voxcpm|ACE-Step|acestep"
MIN_FREE_PCT = 50
POLL_SECONDS = 20
MAX_WAIT_SECONDS = 6 * 3600


@dataclass(frozen=True)
class Ticket:
    job: str                    # e.g. "chipcat/cowos-v3:voice"
    kind: str = "long"          # short | long | other
    progress: float = 0.0       # share of the run's steps already done (long: closest to done first)
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


def tickets(queue_dir: Path = QUEUE_DIR, *, alive: Callable[[int], bool] = _alive) -> list[Ticket]:
    """Live tickets in priority order; tickets of dead processes are removed."""
    out = []
    for path in sorted(queue_dir.glob("*.json")):
        try:
            ticket = Ticket(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            path.unlink(missing_ok=True)
            continue
        if not alive(ticket.pid):
            path.unlink(missing_ok=True)
            continue
        out.append(ticket)
    return sorted(out, key=Ticket.priority)


def _holder(queue_dir: Path) -> str:
    path = queue_dir / "holder"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def _holder_job(queue_dir: Path) -> str:
    holder = _holder(queue_dir)
    path = queue_dir / f"{holder}.json"
    if holder and path.is_file():
        return str(json.loads(path.read_text(encoding="utf-8")).get("job", holder))
    return "another job"


def status(queue_dir: Path = QUEUE_DIR) -> list[dict]:
    holder = _holder(queue_dir)
    return [{**asdict(t), "holding": t.id == holder} for t in tickets(queue_dir)]


@dataclass
class Gate:
    busy: Callable[[str], list[int]]
    free: Callable[[], int | None]
    sleep: Callable[[float], None] = time.sleep
    min_free_pct: int = MIN_FREE_PCT
    max_wait_s: int = MAX_WAIT_SECONDS


def default_gate() -> Gate:
    from content_farm.voice.local_worker import busy_pids, free_memory_pct

    return Gate(busy=busy_pids, free=free_memory_pct)


class QueueTimeout(RuntimeError):
    """Waited longer than ``max_wait_s`` for the heavy slot."""


def _try_lock(queue_dir: Path) -> IO[str] | None:
    handle = (queue_dir / "heavy.lock").open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def _not_first(ticket: Ticket, queue_dir: Path) -> str:
    live = tickets(queue_dir)
    if live and live[0].id != ticket.id:
        return f"queue: {live[0].job} ({live[0].kind}) goes first; {len(live)} waiting"
    return ""


def _resources(gate: Gate) -> str:
    busy = gate.busy(BUSY_PATTERN)
    if busy:
        return f"heavy process outside the queue running (pids {busy[:5]})"
    free = gate.free()
    if free is not None and free < gate.min_free_pct:
        return f"free memory {free}% < {gate.min_free_pct}%"
    return ""


@contextmanager
def heavy_slot(ticket: Ticket, log: Callable[[str], None] = print, *, gate: Gate | None = None,
               queue_dir: Path = QUEUE_DIR) -> Iterator[float]:
    """Hold the machine's one heavy slot; yields the seconds waited."""
    if os.environ.get(SLOT_ENV):                       # a parent already holds it for us
        yield 0.0
        return
    gate = gate or default_gate()
    queue_dir.mkdir(parents=True, exist_ok=True)
    path = queue_dir / f"{ticket.id}.json"
    path.write_text(json.dumps(asdict(ticket)), encoding="utf-8")
    started, handle, last = time.monotonic(), None, ""
    try:
        while True:
            why = _not_first(ticket, queue_dir)
            if not why:
                handle = _try_lock(queue_dir)
                why = "" if handle else f"slot held by {_holder_job(queue_dir)}"
                if handle and (late := _resources(gate)):    # checked with the slot held: nothing of ours runs
                    fcntl.flock(handle, fcntl.LOCK_UN)
                    handle.close()
                    handle, why = None, late
            if handle:
                break
            waited = time.monotonic() - started
            if waited > gate.max_wait_s:
                raise QueueTimeout(f"{ticket.job}: waited {waited:.0f}s for the heavy slot ({why})")
            if why != last:
                log(f"⏳ {ticket.job}: {why}")
                last = why
            gate.sleep(POLL_SECONDS)
        (queue_dir / "holder").write_text(ticket.id, encoding="utf-8")
        os.environ[SLOT_ENV] = ticket.id
        waited = round(time.monotonic() - started, 1)
        _record(queue_dir, ticket, "start", waited)
        yield waited
    finally:
        if handle:
            os.environ.pop(SLOT_ENV, None)
            (queue_dir / "holder").unlink(missing_ok=True)
            _record(queue_dir, ticket, "end", round(time.monotonic() - started, 1))
            fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()
        path.unlink(missing_ok=True)


def _record(queue_dir: Path, ticket: Ticket, event: str, seconds: float) -> None:
    with (queue_dir / "history.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event,
                              "job": ticket.job, "kind": ticket.kind, "seconds": seconds}) + "\n")
