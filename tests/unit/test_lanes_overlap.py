"""Unlocked render lane (2026-10-23): A's GPU step no longer blocks B's CPU render or a cloud review."""

from __future__ import annotations

import fcntl
from pathlib import Path

from content_farm.lanes import queue as q
from content_farm.lanes import resources as res

CONFIG = res.load_config()
ROOMY = res.Probe(total_gb=32, free_gb=26, swap_pct=10, load1=3, cores=10)
NOW = 10_000.0


def job(video: str, step: str, *, state="waiting", since=NOW - 600) -> res.Job:
    return res.Job(f"{video}:{step}", f"{video}:{step}", res.need_for(step, CONFIG), (1, 0.0, f"t{since}"), state, since)


def can_start(me: res.Job, running: list[res.Job], probe: res.Probe = ROOMY) -> bool:
    return res.decide(me, running, probe, CONFIG, NOW) == []


def test_no_step_shares_the_global_render_lock():
    for step, spec in CONFIG.steps.items():
        if step.startswith("_") or step == "heavy_default":
            continue
        assert "render" not in res.need_for(step, CONFIG).locks, step


def test_exclusive_gpu_does_not_imply_render_lock(tmp_path: Path):
    plan = q._lock_plan(res.need_for("illustrate", CONFIG), tmp_path)
    assert [mode for _, mode in plan] == [fcntl.LOCK_EX]            # heavy.lock only
    assert len(q._lock_plan(q.EXCLUSIVE, tmp_path)) == 2   # default stays conservative


def test_b_assembly_and_mix_overlap_a_illustrate_and_cloud_review_runs():
    a_illustrate = job("A", "illustrate", state="running")
    assert can_start(job("B", "assembly"), [a_illustrate])
    both = [a_illustrate, job("B", "assembly", state="running")]
    assert not any("lock" in r for r in res.decide(job("B", "mix"), both, ROOMY, CONFIG, NOW))
    assert can_start(job("C", "gate_deck"), both)


def test_two_gpu_jobs_still_exclude_each_other():
    reasons = res.decide(job("B", "illustrate"), [job("A", "voice", state="running")], ROOMY, CONFIG, NOW)
    assert any("gpu" in r for r in reasons)


def test_cpu_budget_holds_a_render_that_would_oversubscribe():
    small = res.Probe(32, 26, 10, 3, 8)
    running = [job("A", "assembly", state="running")]                # 6 of 8 cores
    reasons = res.decide(job("B", "cut"), running, small, CONFIG, NOW)
    assert any(r.startswith("cpu:") for r in reasons)
    assert can_start(job("B", "cut"), [], small)                     # an idle machine always admits one


def test_cloud_step_ignores_swap_and_load_but_not_memory():
    stressed = res.Probe(32, 26, 97, 40, 10, critical=True)
    assert can_start(job("A", "gate_final"), [], stressed)
    low = res.Probe(32, 6.0, 10, 1, 10)
    assert any(r.startswith("memory:") for r in res.decide(job("A", "gate_final"), [], low, CONFIG, NOW))


def test_cpu_render_still_respects_swap():
    stressed = res.Probe(32, 26, 97, 3, 10)
    assert any("swap" in r for r in res.decide(job("B", "assembly"), [], stressed, CONFIG, NOW))
