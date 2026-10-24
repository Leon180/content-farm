"""Admission decisions (lanes/resources.decide): every rule of the 2026-10-18 prompt."""

from __future__ import annotations

import pytest

from content_farm.lanes import resources as res

CFG = res.Config(margin_gb=6, margin_idle_gb=6, swap_max_pct=90, load_factor=1.5, starve_after_s=1200, recent_start_s=90,
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
    busy = job("r:render", ASSEMBLY, state="running", since=NOW - 500)        # something running that may free memory
    reasons = res.decide(job("b:assembly", ASSEMBLY, since=NOW - 5), [starving, busy], probe, CFG, NOW)
    assert any("anti-starvation" in r for r in reasons)
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


# --- 2026-10-23 lanes deadlock -----------------------------------------------------------------

VOICE_DESIGN = res.Need(19.5, "exclusive", 2, ("local_tts",))
IDLE_CFG = res.Config(margin_gb=6, margin_idle_gb=3, starve_after_s=1200)
IDLE_MAC = res.Probe(total_gb=32, free_gb=23.0, swap_pct=10, load1=3, cores=10)       # measured 22.7–23.7 GB free


def test_waiter_does_not_reserve_against_the_job_that_feeds_it():
    starving = res.Job("technews:voice", "technews:voice", VOICE, (0, 0.0, "a"), "waiting", NOW - 1300, False,
                       needs="voice-ref:technews")
    design = res.Job("d", "technews:voice-design", VOICE_DESIGN, (2, 0.0, "b"), "waiting", NOW - 5,
                     provides="voice-ref:technews")
    assert res.decide(design, [starving], IDLE_MAC, IDLE_CFG, NOW) == []
    stranger = res.Job("s", "yokai:illustrate", VOICE_DESIGN, (2, 0.0, "c"), "waiting", NOW - 5)
    busy = res.Job("r", "x:render", ASSEMBLY, (1, 0.0, "r"), "running", NOW - 500, True)
    assert any("anti-starvation" in r for r in res.decide(stranger, [starving, busy], IDLE_MAC, IDLE_CFG, NOW))


def test_fresh_higher_priority_waiter_does_not_go_first_over_its_feeder():
    short_voice = res.Job("v", "technews:voice", VOICE, (0, 0.0, "a"), "waiting", NOW - 10, True,
                          needs="voice-ref:technews")
    design = res.Job("d", "technews:voice-design", VOICE_DESIGN, (2, 0.0, "b"), "waiting", NOW - 5,
                     provides="voice-ref:technews")
    assert res.decide(design, [short_voice], IDLE_MAC, IDLE_CFG, NOW) == []


def test_idle_machine_takes_the_smaller_margin():
    cfg = res.Config(margin_gb=6, margin_idle_gb=3)
    assert res.decide(job("x:voice_design", VOICE_DESIGN), [], IDLE_MAC, cfg, NOW) == []      # 23.0 ≥ 19.5+3
    busy = job("y:media", res.Need(4, "shared", 4, ("render",)), state="running", since=NOW - 600)
    reasons = res.decide(job("x:voice_design", VOICE_DESIGN), [busy], IDLE_MAC, cfg, NOW)
    assert any(r.startswith("memory:") for r in reasons)                                      # needs the full 6 GB


def test_cloud_job_running_does_not_count_as_local_work():
    cfg = res.Config(margin_gb=6, margin_idle_gb=3)
    reviewer = job("y:gate_deck", REVIEW, state="running", since=NOW - 600)
    assert res.decide(job("x:voice_design", VOICE_DESIGN), [reviewer], IDLE_MAC, cfg, NOW) == []


def test_reason_names_the_shortfall_after_twenty_minutes():
    cfg = res.Config(margin_gb=6, margin_idle_gb=3, shortfall_after_s=1200)
    tight = res.Probe(32, 20.0, 10, 3, 10)
    early = res.decide(job("x:voice_design", VOICE_DESIGN, since=NOW - 60), [], tight, cfg, NOW)
    late = res.decide(job("x:voice_design", VOICE_DESIGN, since=NOW - 1300), [], tight, cfg, NOW)
    assert "差" not in early[0] and "差 2.5 GB" in late[0]                                      # 19.5+3−20


def test_voice_steps_use_increments_over_idle_and_a_machine_ceiling():
    config = res.load_config()
    assert res.need_for("voice", config).mem_gb == 16.7 and res.need_for("voice_design", config).mem_gb == 19.5
    assert config.margin_idle_gb == 3 and config.margin_gb == 6
    assert res.impossible(res.need_for("voice_design", config), IDLE_MAC, config) == ""
    assert "can never run here" in res.impossible(res.Need(30), IDLE_MAC, config)              # 30+3 > 32


def test_reservations_never_form_a_ring_and_need_a_running_job_to_wait_for():
    a = job("a:slides", ASSEMBLY, since=NOW - 1500, fits=True)
    b = job("b:slides", ASSEMBLY, since=NOW - 1400, fits=True)
    c = job("c:voice", VOICE, since=NOW - 2300, fits=False)
    # the deepsea/chipcat/voice-design ring (2026-10-24): only the oldest ticket is waited for, nobody waits on a younger one
    assert not any("anti-starvation" in r for r in res.decide(c, [a, b], ROOMY, CFG, NOW))
    busy = job("r:render", ASSEMBLY, state="running", since=NOW - 500)
    assert any("anti-starvation" in r for r in res.decide(a, [b, c, busy], ROOMY, CFG, NOW))      # c is older than a
    assert not any("anti-starvation" in r for r in res.decide(c, [a, b, busy], ROOMY, CFG, NOW))
    # nothing running: holding back would free nothing, so the oldest waiter's shortfall does not block the others
    assert not any("anti-starvation" in r for r in res.decide(a, [b, c], ROOMY, CFG, NOW))
