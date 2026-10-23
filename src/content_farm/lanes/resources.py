"""Resource needs, machine probes and the admission decision (Leon 2026-10-18).

Every step — cloud lane included — declares what it needs (``channels/shared/heavy_work.json``
``steps``: ``mem_gb``, ``gpu`` exclusive|shared|none, ``cpu_cores``, ``locks``). Before a step
starts, :func:`decide` compares the need with a probe of the machine and the other jobs in the
queue and returns the reasons it must wait ([] = go). Pure function: every rule is unit-tested.

Rules (all from the 2026-10-18 prompt):
- the unit that waits is one video × one step; other videos keep moving;
- need > machine (mem_gb + margin > total) → impossible: fail now, never queue;
- free memory ≥ need + margin (memory recently promised to just-started jobs is subtracted),
  swap < max, load1 < factor × cores, memory pressure not critical;
- a higher-priority waiter that would also fit goes first; one that does not fit lets smaller
  jobs backfill — until it has waited ``starve_after_s``: then no new local job starts before it;
- CPU renders are budgeted by cores + memory, not a global render lock; cloud steps look at free
  memory only (2026-10-23); locks (gpu/render/local_tts) are all-or-nothing in a fixed order (queue.py).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[3] / "channels" / "shared" / "heavy_work.json"
GPU_MODES = ("none", "shared", "exclusive")
LOCK_ORDER = ("gpu", "render", "local_tts")
CPU_HEAVY_CORES = 2.0       # >= this many cores and no GPU/lock: a CPU render (assembly, mix, cut, slides)


@dataclass(frozen=True)
class Need:
    mem_gb: float = 0.5
    gpu: str = "none"           # none | shared | exclusive
    cpu_cores: float = 0.5
    locks: tuple[str, ...] = ()

    @property
    def local(self) -> bool:
        """Local heavy lane: uses the GPU, holds a lock, or is a CPU render (>= ``CPU_HEAVY_CORES``)."""
        return self.gpu != "none" or bool(self.locks) or self.cpu_cores >= CPU_HEAVY_CORES

    @property
    def light(self) -> bool:
        """Cloud-lane step (reviewer, producer agent): only free memory decides, never swap or load."""
        return not self.local


@dataclass(frozen=True)
class Probe:
    total_gb: float
    free_gb: float
    swap_pct: float
    load1: float
    cores: int
    critical: bool = False


@dataclass(frozen=True)
class Job:
    id: str
    job: str
    need: Need
    priority: tuple
    state: str                  # waiting | running
    since: float                # epoch seconds: enqueued (waiting) or started (running)
    fits: bool = True           # waiting jobs: does the machine fit it right now (last check)
    needs: str = ""             # a product this job cannot start without (e.g. "voice-ref:technews")
    provides: str = ""          # the product this job makes; never held back by a waiter that needs it


@dataclass(frozen=True)
class Config:
    margin_gb: float = 6.0
    margin_idle_gb: float = 3.0     # margin when no other local heavy job is running
    shortfall_after_s: float = 1200.0   # a wait this long names how many GB are missing
    swap_max_pct: float = 90.0
    load_factor: float = 1.5
    starve_after_s: float = 1200.0
    notify_after_s: float = 2700.0
    recent_start_s: float = 90.0
    reviewer_gb: float = 0.6
    max_parallel_reviewers: int = 8
    poll_seconds: float = 20.0
    max_wait_s: float = 21600.0
    steps: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


def load_config(path: Path = CONFIG) -> Config:
    data = json.loads(path.read_text(encoding="utf-8"))
    admission = data.get("admission", {})
    margin = admission.get("margin_gb", 6.0)
    return Config(margin_gb=margin, margin_idle_gb=min(margin, admission.get("margin_idle_gb", 3.0)),
                  shortfall_after_s=admission.get("shortfall_after_s", 1200.0),
                  swap_max_pct=admission.get("swap_max_pct", 90.0),
                  load_factor=admission.get("load_factor", 1.5),
                  starve_after_s=admission.get("starve_after_s", 1200.0),
                  notify_after_s=admission.get("notify_after_s", 2700.0),
                  reviewer_gb=admission.get("reviewer_gb", 0.6),
                  max_parallel_reviewers=admission.get("max_parallel_reviewers", 8),
                  poll_seconds=data.get("poll_seconds", 20), max_wait_s=data.get("max_wait_seconds", 21600),
                  steps=data.get("steps", {}), raw=data)


def need_for(step: str, config: Config, *, default: Need | None = None) -> Need:
    spec = config.steps.get(step)
    if spec is None:
        return default or Need()
    gpu = spec.get("gpu", "none")
    if gpu not in GPU_MODES:
        raise ValueError(f"heavy_work.json steps.{step}.gpu must be one of {GPU_MODES}")
    locks = tuple(spec.get("locks", ()))
    bad = [lock for lock in locks if lock not in LOCK_ORDER]
    if bad:
        raise ValueError(f"heavy_work.json steps.{step}.locks: unknown {bad}")
    return Need(float(spec.get("mem_gb", 0.5)), gpu, float(spec.get("cpu_cores", 0.5)), locks)


def impossible(need: Need, probe: Probe, config: Config) -> str:
    margin = min(config.margin_gb, config.margin_idle_gb)     # the margin an idle machine needs
    if need.mem_gb + margin > probe.total_gb:
        return (f"needs {need.mem_gb:g} GB + {margin:g} GB margin but the machine has "
                f"{probe.total_gb:.0f} GB: can never run here")
    if need.cpu_cores > probe.cores:
        return f"needs {need.cpu_cores:g} cores, the machine has {probe.cores}"
    return ""


def _machine(need: Need, probe: Probe, promised_gb: float, config: Config, *, margin_gb: float | None = None,
             waited_s: float = 0.0) -> list[str]:
    reasons = []
    margin = config.margin_gb if margin_gb is None else margin_gb
    free = probe.free_gb - promised_gb
    if free < need.mem_gb + margin:
        missing = f"，差 {need.mem_gb + margin - free:.1f} GB" if waited_s >= config.shortfall_after_s else ""
        reasons.append(f"memory: {free:.1f} GB free (after {promised_gb:.1f} GB promised to just-started jobs) "
                       f"< {need.mem_gb:g} + {margin:g} GB{missing}")
    if need.light:          # cloud lane: actual free memory (margin_gb) only (Leon 2026-10-23)
        return reasons
    if probe.swap_pct >= config.swap_max_pct:
        reasons.append(f"swap {probe.swap_pct:.0f}% ≥ {config.swap_max_pct:g}%")
    if probe.load1 >= config.load_factor * probe.cores and need.cpu_cores >= 1:
        reasons.append(f"load {probe.load1:.1f} ≥ {config.load_factor:g}×{probe.cores} cores")
    if probe.critical:
        reasons.append("memory pressure critical: new steps paused, running ones finish")
    return reasons


def _cpu_budget(need: Need, running: list[Job], probe: Probe) -> list[str]:
    """Core budget for CPU renders: running jobs' cores + mine must fit the machine; an idle
    machine always admits one (``impossible`` already rejects a need above the core count)."""
    if need.cpu_cores < 1:
        return []
    busy = sum(j.need.cpu_cores for j in running if j.need.cpu_cores >= 1)
    if busy > 0 and busy + need.cpu_cores > probe.cores:
        return [f"cpu: {busy:g} of {probe.cores} cores in use, needs {need.cpu_cores:g}"]
    return []


def decide(me: Job, others: list[Job], probe: Probe, config: Config, now: float) -> list[str]:
    """Why ``me`` must wait now ([] = start). ``others``: every other live job."""
    promised = sum(j.need.mem_gb for j in others if j.state == "running" and now - j.since < config.recent_start_s)
    running = [j for j in others if j.state == "running"]
    alone = me.need.local and not any(j.need.local for j in running)   # local step on a quiet machine: smaller margin
    reasons = _machine(me.need, probe, promised, config, waited_s=now - me.since,
                       margin_gb=min(config.margin_idle_gb, config.margin_gb) if alone else config.margin_gb)
    reasons += _cpu_budget(me.need, running, probe)
    if me.need.gpu == "exclusive" and any(j.need.gpu != "none" for j in running):
        reasons.append("gpu: another job is using the GPU")
    if me.need.gpu == "shared" and any(j.need.gpu == "exclusive" for j in running):
        reasons.append("gpu: an exclusive GPU job is running")
    busy_locks = {lock for j in running for lock in j.need.locks}
    taken = [lock for lock in me.need.locks if lock in busy_locks]
    if taken:
        reasons.append(f"lock {', '.join(taken)} held by {', '.join(j.job for j in running if set(j.need.locks) & set(taken))}")
    waiting = [j for j in others if j.state == "waiting"]
    if me.need.local:
        feeds = [j for j in waiting if me.provides and j.needs == me.provides]    # my output unblocks them
        starving = [j for j in waiting if j.need.local and now - j.since >= config.starve_after_s
                    and (j.priority < me.priority or now - j.since > now - me.since) and j not in feeds]
        if starving:
            reasons.append(f"reserved for {starving[0].job} (waiting {int(now - starving[0].since)} s, anti-starvation)")
        ahead = [j for j in waiting if j.need.local and j.fits and j.priority < me.priority
                 and j not in feeds]
        if ahead and not starving:
            reasons.append(f"priority: {ahead[0].job} goes first")
    return reasons


def reviewer_parallelism(probe: Probe, config: Config, wanted: int) -> int:
    """How many claude -p reviewers may run at once given free memory (0 = wait)."""
    room = probe.free_gb - config.margin_gb
    fit = int(room // config.reviewer_gb) if room > 0 else 0
    return max(0, min(wanted, config.max_parallel_reviewers, fit))


# --- probes (macOS) ---------------------------------------------------------------------------

_FREE = re.compile(r"free percentage:\s*(\d+)%")
_SWAP = re.compile(r"total = ([\d.]+)M\s+used = ([\d.]+)M")


def _run(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, check=False, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def probe_machine() -> Probe:
    total = int(_run(["sysctl", "-n", "hw.memsize"]).strip() or 0) / 2**30 or 32.0
    free_match = _FREE.search(_run(["memory_pressure", "-Q"]))
    free_pct = int(free_match.group(1)) if free_match else 100
    swap = _SWAP.search(_run(["sysctl", "-n", "vm.swapusage"]))
    swap_pct = 100 * float(swap.group(2)) / float(swap.group(1)) if swap and float(swap.group(1)) else 0.0
    level = _run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]).strip()
    return Probe(total_gb=round(total, 1), free_gb=round(total * free_pct / 100, 1), swap_pct=round(swap_pct, 1),
                 load1=os.getloadavg()[0], cores=os.cpu_count() or 1, critical=level == "4")


def foreign_heavy(patterns: list[str], ours: set[int]) -> list[tuple[int, str]]:
    """Heavy processes (by ``heavy_work.json`` process patterns) that are not descendants of a
    queued job (``ours`` = pids of running tickets) and not shells merely mentioning a pattern."""
    rows = []
    for line in _run(["ps", "-Ao", "pid=,ppid=,command="]).splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[0].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
    parent = {pid: ppid for pid, ppid, _ in rows}

    def owned(pid: int) -> bool:
        seen = set()
        while pid and pid not in seen:
            if pid in ours or pid == os.getpid():
                return True
            seen.add(pid)
            pid = parent.get(pid, 0)
        return False

    compiled = [re.compile(p) for p in patterns]
    shells = ("sh", "bash", "zsh", "pgrep", "grep", "timeout", "tail")
    return [(pid, cmd[:80]) for pid, _, cmd in rows
            if any(c.search(cmd) for c in compiled) and Path(cmd.split(" ", 1)[0]).name not in shells
            and not owned(pid)]
