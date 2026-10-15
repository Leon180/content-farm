"""Parameter timeline: lip-sync envelope, blink schedule, physics, pose transitions."""

from __future__ import annotations

import numpy as np
import pytest

from content_farm.explainer.mascot import idle, lipsync, physics
from content_farm.explainer.mascot.cues import SceneCue, build_cues, resolve_slide
from content_farm.explainer.mascot.motion import (
    TRANSITION_S, bubble_level, compose_frames, deadpan_blinks, pose_blend,
)
from content_farm.explainer.mascot.params import PARAM_NAMES, POSES, pose_vector

FPS = 30.0


class TestLipSync:
    def test_silence_keeps_mouth_shut(self) -> None:
        assert lipsync.mouth_envelope([-120.0] * 50).max() == 0.0

    def test_speech_opens_and_closes(self) -> None:
        db = [-120.0] * 10 + [-12.0] * 20 + [-120.0] * 10
        env = lipsync.mouth_envelope(db)
        assert env[:10].max() == 0.0
        assert env[15:30].min() > 0.8
        assert env[32:].max() == 0.0  # snapped shut within silence_frames

    def test_attack_faster_than_release(self) -> None:
        db = [-120.0] * 5 + [-12.0] * 10 + [-30.0] * 10
        env = lipsync.mouth_envelope(db)
        rise = env[5] / env[14]
        fall = (env[14] - env[15]) / env[14]
        assert rise > fall

    def test_quiet_noise_is_gated_relative_to_speech(self) -> None:
        db = [-12.0] * 20 + [-45.0] * 20  # -45 is above abs gate but 33 dB under speech
        env = lipsync.mouth_envelope(db)
        assert env[25:].max() == 0.0

    def test_envelope_in_unit_range(self) -> None:
        rng = np.random.default_rng(0)
        env = lipsync.mouth_envelope(rng.uniform(-80, 0, 500))
        assert env.min() >= 0.0 and env.max() <= 1.0

    def test_frame_rms_of_sine(self) -> None:
        sr = lipsync.SAMPLE_RATE
        t = np.arange(sr) / sr
        tone = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        db = lipsync.frame_rms_db(tone, sr, FPS, 30)
        assert db == pytest.approx(np.full(30, 20 * np.log10(0.5 / np.sqrt(2))), abs=0.2)

    def test_scenes_placed_at_their_start(self) -> None:
        sr = lipsync.SAMPLE_RATE
        burst = np.full(sr // 2, 0.3, dtype=np.float32)  # 0.5 s of "voice"
        env = lipsync.envelope_for_scenes(
            [("a", 0.0), ("b", 2.0)], FPS, 90, decode=lambda _p: burst)
        assert env[5] > 0 and env[30:59].max() == 0.0 and env[62] > 0


class TestBlinkSchedule:
    def test_deterministic_per_seed(self) -> None:
        assert idle.blink_schedule(120, 3) == idle.blink_schedule(120, 3)
        assert idle.blink_schedule(120, 3) != idle.blink_schedule(120, 4)

    @pytest.mark.parametrize("seed", range(10))
    def test_event_gaps_between_2_and_6_seconds(self, seed: int) -> None:
        events = idle.blink_events(idle.blink_schedule(300, seed))
        gaps = np.diff(events)
        assert len(events) > 40
        assert gaps.min() >= 2.0 and gaps.max() <= 6.0
        assert gaps.std() > 0.5  # jittered, not a metronome

    def test_closure_curve(self) -> None:
        blink = idle.Blink(1.0)
        assert idle.blink_closure(0.99, (blink,)) == 0.0
        assert idle.blink_closure(1.07, (blink,)) == 1.0
        assert idle.blink_closure(blink.end, (blink,)) == 0.0
        slow = idle.Blink(1.0, slow=True)
        assert slow.end - slow.start > 2 * (blink.end - blink.start)

    def test_breath_range(self) -> None:
        values = [idle.breath(i / FPS) for i in range(300)]
        assert min(values) >= 0.0 and max(values) <= 1.0 and max(values) > 0.99


class TestPhysics:
    def test_follower_settles_on_step(self) -> None:
        out = physics.follow([0.0] + [10.0] * 300, physics.EAR, 1 / FPS)
        assert out[-1] == pytest.approx(10.0, abs=0.05)

    def test_lag_swings_against_motion_then_settles(self) -> None:
        drive = [0.0] * 5 + [10.0] * 200
        lag = physics.lag(drive, physics.TAIL, 1 / FPS)
        assert lag[5] < -5  # left behind right after the jump
        assert abs(lag[-1]) < 0.1

    def test_kick_returns_to_rest(self) -> None:
        out = physics.follow([0.0] * 60, physics.TWITCH, 1 / FPS, {2: 300.0})
        assert max(out) > 3 and abs(out[-1]) < 0.05

    def test_springs_underdamped_but_stable(self) -> None:
        for spring in (physics.EAR, physics.TAIL, physics.TAIL_TIP, physics.CHIP):
            assert 0 < spring.damping_ratio < 1


def _cues(*poses: str, length: float = 2.0) -> tuple[SceneCue, ...]:
    return tuple(SceneCue(i + 1, i * length, (i + 1) * length, p) for i, p in enumerate(poses))


class TestPoses:
    def test_transition_takes_250ms(self) -> None:
        cues = _cues("idle", "point")
        assert pose_blend(cues, 2.0)["ArmR"] == pytest.approx(0.0)
        mid = pose_blend(cues, 2.0 + TRANSITION_S / 2)["ArmR"]
        assert 0.4 < mid / pose_vector("point")["ArmR"] < 0.6
        assert pose_blend(cues, 2.0 + TRANSITION_S)["ArmR"] == pytest.approx(pose_vector("point")["ArmR"])
        assert 0.2 <= TRANSITION_S <= 0.3

    def test_every_pose_has_full_targets(self) -> None:
        for pose in POSES:
            assert set(pose_vector(pose)) >= {"ArmR", "EyeOpen", "Sway"}

    def test_deadpan_is_half_lidded_and_still(self) -> None:
        dp = pose_vector("deadpan")
        assert 0.3 < dp["EyeOpen"] < 0.6 and dp["Sway"] == 0 and dp["MouthForm"] == -1

    def test_deadpan_slow_blinks_after_hold_and_punchline(self) -> None:
        cues = _cues("deadpan", length=5.0)
        mouth = np.zeros(150)
        mouth[30:60] = 0.5  # speech ends at 2.0 s, then 3 s of silence
        blinks = deadpan_blinks(cues, mouth, FPS)
        assert all(b.slow for b in blinks)
        assert [round(b.start, 2) for b in blinks] == [1.1, 2.2]

    def test_effects_belong_to_their_pose(self) -> None:
        for pose in POSES:
            v = pose_vector(pose)
            assert v["Sweat"] == (1.0 if pose == "deadpan" else 0.0), pose
            assert v["Burst"] == (1.0 if pose == "shocked" else 0.0), pose

    def test_effects_cross_fade_at_scene_change(self) -> None:
        frames = compose_frames(_cues("idle", "deadpan"), np.zeros(120), FPS, 120, seed=1)
        sweat = [f.params["ParamSweat"] for f in frames]
        assert sweat[30] == 0.0 and sweat[-1] == 1.0
        assert 0.0 < sweat[int((2.0 + TRANSITION_S / 2) * FPS)] < 1.0

    def test_bubble_fades_in_and_out(self) -> None:
        cue = SceneCue(1, 0.0, 10.0, "idle", "這個數字其實是…")
        assert bubble_level(cue, 0.1) == 0.0
        assert 0 < bubble_level(cue, 0.2) < 1
        assert bubble_level(cue, 1.0) == 1.0
        assert bubble_level(cue, 9.5) == 0.0
        assert bubble_level(SceneCue(1, 0, 10, "idle"), 1.0) == 0.0

    def test_resolve_slide(self) -> None:
        assert resolve_slide(None, "joke").pose == "deadpan"
        assert resolve_slide(None, None).pose == "idle"
        assert resolve_slide({"pose": "nope"}, None).pose == "idle"
        assert resolve_slide({"pose": "point", "position": "left"}, None).position == "right"
        assert resolve_slide({"pose": "wave", "say": "  "}, None).say is None


class TestCompose:
    def test_deterministic_and_complete(self) -> None:
        cues = build_cues([resolve_slide({"pose": p}, None) for p in ("wave", "point", "deadpan")],
                          [(0, 2), (2, 4), (4, 6)])
        mouth = np.abs(np.sin(np.arange(180) / 4))
        a = compose_frames(cues, mouth, FPS, 180, seed=1)
        b = compose_frames(cues, mouth, FPS, 180, seed=1)
        assert a == b
        assert len(a) == 180 and tuple(a[0].params) == PARAM_NAMES
        assert a[100].params["ParamArmR"] == pytest.approx(pose_vector("point")["ArmR"])
        assert a[0].params["ParamMouthOpenY"] == 0.0

    def test_ears_lag_head_motion(self) -> None:
        frames = compose_frames(_cues("idle", length=20.0), np.zeros(600), FPS, 600, seed=2)
        ears = np.array([f.params["ParamEarL"] for f in frames])
        assert ears.std() > 0.3  # they move without any pose change
