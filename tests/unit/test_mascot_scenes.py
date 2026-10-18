"""Scene-local mascot motion: frames depend only on their own scene (incremental render)."""

from __future__ import annotations

import numpy as np

from content_farm.explainer.mascot.cues import SceneCue
from content_farm.explainer.mascot.motion import SceneSpan, compose_scene, edge_envelope
from content_farm.explainer.mascot.params import pose_vector
from content_farm.explainer.mascot.scenes import scene_identity, scene_seed, spans

FPS = 30.0


def _cues(*poses: str, length: float = 3.0) -> tuple[SceneCue, ...]:
    return tuple(SceneCue(index=i + 1, start=i * length, end=(i + 1) * length, pose=p) for i, p in enumerate(poses))


def test_spans_partition_the_video() -> None:
    cues = (SceneCue(1, 0.0, 2.517, "idle"), SceneCue(2, 2.517, 5.2, "point"), SceneCue(3, 5.2, 9.0, "smug"))
    out = spans(cues, FPS, 270, seed=7, keys=["a", "b", "c"])
    assert [s.first for s in out] == [0, 76, 156]
    assert sum(s.used for s in out) == 270          # slots partition the video
    assert [s.count for s in out] == [77, 82, 115]   # rendered: own length + 1 spare frame
    assert out[1].previous_pose == "idle" and out[0].previous_pose is None
    assert out[1].offset == 0.0   # snapped to the frame grid: position never leaks into identity


def test_frames_do_not_depend_on_position_in_the_video() -> None:
    cue = SceneCue(4, 0.0, 3.0, "think", say="嗯")
    a = SceneSpan(cue=cue, previous_pose="idle", first=0, count=90, offset=0.0, seed=scene_seed(7, "s04"))
    b = SceneSpan(cue=SceneCue(9, 80.0, 83.0, "think", say="嗯"), previous_pose="idle", first=2400,
                  count=90, offset=0.0, seed=scene_seed(7, "s04"))
    mouth = np.linspace(0, 1, 90)
    assert compose_scene(a, mouth, FPS) == compose_scene(b, mouth, FPS)


def test_scene_edges_settle_to_the_pose_so_neighbours_meet() -> None:
    cues = _cues("idle", "point")
    first, second = spans(cues, FPS, 180, seed=3, keys=["s1", "s2"])
    end_a = compose_scene(first, np.zeros(90), FPS)[-1].params
    start_b = compose_scene(second, np.zeros(90), FPS)[0].params
    pose = pose_vector("idle")
    # the last frame of scene 1 is (nearly) at rest in its pose ...
    assert abs(end_a["ParamAngleX"] - pose["AngleX"]) < 0.05
    assert abs(end_a["ParamTail"]) < 0.02 and abs(end_a["ParamBreath"]) < 0.02
    # ... and scene 2 starts from the same pose (its 0.25 s blend starts at idle)
    for key in ("ParamAngleX", "ParamAngleZ", "ParamArmR", "ParamTail", "ParamEarL", "ParamEyeLOpen"):
        assert abs(end_a[key] - start_b[key]) < 0.35, key


def test_edge_envelope_shape() -> None:
    assert edge_envelope(0.0, 3.0) == 0.0 and edge_envelope(3.0, 3.0) == 0.0
    assert edge_envelope(1.5, 3.0) == 1.0
    assert 0 < edge_envelope(0.2, 3.0) < 1


def test_identity_follows_content_not_position(tmp_path) -> None:
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    cue = SceneCue(2, 10.0, 13.0, "smug")
    span = SceneSpan(cue=cue, previous_pose="idle", first=300, count=90, offset=0.0, seed=1)
    moved = SceneSpan(cue=SceneCue(5, 40.0, 43.0, "smug"), previous_pose="idle", first=1200, count=90,
                      offset=0.0, seed=1)
    key = scene_identity(span, audio, FPS, render="r", code="c")
    assert scene_identity(moved, audio, FPS, render="r", code="c") == key
    audio.write_bytes(b"y")
    assert scene_identity(span, audio, FPS, render="r", code="c") != key
    other_prev = SceneSpan(cue=cue, previous_pose="shocked", first=300, count=90, offset=0.0, seed=1)
    assert scene_identity(other_prev, None, FPS, render="r", code="c") != scene_identity(span, None, FPS,
                                                                                     render="r", code="c")


def test_a_scene_that_only_moves_keeps_its_identity() -> None:
    before = spans((SceneCue(1, 0.0, 4.0, "idle"), SceneCue(2, 4.0, 7.517, "point")), FPS, 226, seed=7, keys=["a", "b"])
    after = spans((SceneCue(1, 0.0, 4.013, "idle"), SceneCue(2, 4.013, 7.53, "point")), FPS, 226, seed=7, keys=["a", "b"])
    key = [scene_identity(s, None, FPS, render="r", code="c") for s in (before[1], after[1])]
    assert key[0] == key[1]
    assert compose_scene(before[1], np.zeros(before[1].count), FPS) == compose_scene(after[1], np.zeros(after[1].count), FPS)
