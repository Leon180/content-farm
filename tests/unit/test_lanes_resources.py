"""Admission decisions (lanes/resources.decide): every rule of the 2026-10-18 prompt."""

from __future__ import annotations

import pytest

from content_farm.lanes import resources as res

CFG = res.Config(margin_gb=6, swap_max_pct=90, load_factor=1.5, starve_after_s=1200, recent_start_s=90,
                 reviewer_gb=0.6, max_parallel_reviewers=8)
ROOMY = res.Probe(total_gb=32, free_gb=28, swap_pct=10, load1=3, cores=10)
NOW = 10_000.0
VOICE = res.Need(18, "exclusive", 2, ("local_tts",))
VIDEO = res.Need(21, "exclusive", 2, ("render",))
ASSEMBLY = res.Need(2, "none", 6, ("render",))
REVIEW = res.Need(0.6)


def job(name, need, *, state="waiting", since=NOW - 10, kind=1, progress=0.0, fits=True):
    return res.Job(name, name, need, (kind, -progress, f"t{since}"), state, since, fits)


def test_cloud_lane_moves_while_another_video_waits_for_the_gpu():
    waiting_voice = job("chipcat/a:voice", VOICE, fits=False)
    probe = res.Probe(32, 9, 10, 3, 10)                      # not enough for voice, plenty for a reviewer
    assert res.decide(job("yokai/b:gate_deck", REVIEW), [waiting_voice], probe, CFG, NOW) == []


def test_memory_swap_load_and_critical_pressure_hold_a_step():
    tight = res.Probe(32, 7, 95, 20, 10, critical=True)
    reasons = res.decide(job("x:media", res.Need(4, "shared", 4, ("render",))), [], tight, CFG, NOW)
    assert any(r.startswith("memory:") for r in reasons) and any("swap 95%" in r for r in reasons)
    assert any("load 20.0" in r for r in reasons) and any("critical" in r for r in reasons)


def test_memory_promised_to_just_started_jobs_counts():
    started = job("a:media", res.Need(10, "none", 1), state="running", since=NOW - 5)
    assert res.decide(job("b:mascot", res.Need(13, "none", 1)), [started], ROOMY, CFG, NOW)   # 28-10 < 13+6
    old = job("a:media", res.Need(10, "none", 1), state="running", since=NOW - 600)
    assert res.decide(job("b:mascot", res.Need(13, "none", 1)), [old], ROOMY, CFG, NOW) == []


def test_impossible_need_fails_now():
    assert "can never run here" in res.impossible(res.Need(40), ROOMY, CFG)
    assert res.impossible(VOICE, ROOMY, CFG) == ""


def test_backfill_small_job_while_big_one_does_not_fit():
    probe = res.Probe(32, 12, 10, 3, 10)
    big = job("a:mlx_video", VIDEO, kind=0, fits=False, since=NOW - 300)           # higher priority, does not fit
    assert res.decide(job("b:assembly", ASSEMBLY, kind=1), [big], probe, CFG, NOW) == []


def test_anti_starvation_reserves_for_a_big_job():
    probe = res.Probe(32, 12, 10, 3, 10)
    starving = job("a:mlx_video", VIDEO, fits=False, since=NOW - 1300)
    reasons = res.decide(job("b:assembly", ASSEMBLY, since=NOW - 5), [starving], probe, CFG, NOW)
    assert reasons and "anti-starvation" in reasons[0]
    assert res.decide(job("c:gate_title", REVIEW), [starving], probe, CFG, NOW) == []        # cloud still moves


def test_priority_hn_short_before_long_closest_to_done_before_other():
    short = job("hn:voice", VOICE, kind=0)
    long_late = job("chipcat:voice", VOICE, kind=1, progress=0.8)
    long_early = job("yokai:voice", VOICE, kind=1, progress=0.2)
    assert "priority" in res.decide(long_late, [short], ROOMY, CFG, NOW)[0]
    assert "priority" in res.decide(long_early, [long_late], ROOMY, CFG, NOW)[0]
    assert res.decide(short, [long_late, long_early], ROOMY, CFG, NOW) == []


def test_gpu_and_lock_conflicts():
    running_voice = job("a:voice", VOICE, state="running", since=NOW - 600)
    assert any("gpu" in r for r in res.decide(job("b:media", res.Need(4, "shared", 1, ("render",))),
                                              [running_voice], ROOMY, CFG, NOW))
    running_mix = job("a:mix", res.Need(1.5, "none", 2, ("render",)), state="running", since=NOW - 600)
    assert any("lock render" in r for r in res.decide(job("b:assembly", ASSEMBLY), [running_mix], ROOMY, CFG, NOW))


def test_reviewer_parallelism_follows_free_memory():
    assert res.reviewer_parallelism(res.Probe(32, 8.4, 0, 1, 10), CFG, 9) == 4      # (8.4-6)/0.6
    assert res.reviewer_parallelism(ROOMY, CFG, 9) == 8                              # capped
    assert res.reviewer_parallelism(res.Probe(32, 5, 0, 1, 10), CFG, 9) == 0


def test_step_needs_from_config():
    config = res.load_config()
    assert res.need_for("voice", config).gpu == "exclusive" and "local_tts" in res.need_for("voice", config).locks
    assert not res.need_for("gate_deck", config).local
    with pytest.raises(ValueError):
        res.need_for("x", res.Config(steps={"x": {"gpu": "maybe"}}))
