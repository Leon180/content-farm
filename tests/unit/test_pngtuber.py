"""PNGtuber hosts: pack format, frame state, placement clearance, pack building, channel wiring."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from content_farm.explainer.mascot.cues import SceneCue
from content_farm.explainer.pngtuber import build, motion, pack, render

SIZE = (200, 240)


def _figure(face: str = "neutral") -> Image.Image:
    """A white-background test character: green body, a face that changes per state. Strokes are
    >= 5 px like real generated faces (build.py drops changes thinner than its opening kernel)."""
    img = Image.new("RGB", SIZE, "white")
    d = ImageDraw.Draw(img)
    d.ellipse((30, 40, 170, 230), fill=(120, 170, 140), outline="black", width=5)
    eyes = {"blink": "line", "surprised": "big"}.get(face, "dot")
    for x in (80, 120):
        if eyes == "line":
            d.line((x - 9, 100, x + 9, 100), fill="black", width=6)
        else:
            r = 10 if eyes == "big" else 6
            d.ellipse((x - r, 100 - r, x + r, 100 + r), fill="black")
    mouth = {"mouth_half": 8, "mouth_open": 16, "surprised": 12}.get(face, 0)
    if mouth:
        d.ellipse((88, 128, 112, 128 + mouth), fill=(110, 30, 50))
    else:
        d.line((90, 134, 110, 134), fill="black", width=5)
    if face == "smug":
        d.line((68, 86, 92, 92), fill="black", width=6)
    if face == "speechless":
        d.ellipse((150, 60, 162, 76), fill=(140, 200, 255))
    return img


@pytest.fixture()
def pack_root(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    for state in ("base", *pack.LAYERS):
        _figure("neutral" if state == "base" else state).save(src / f"{state}.png")
    root = tmp_path / "packs"
    build.build_pack(src, root / "testy", "testy", "測試", pose_map={"think": "smug"})
    return root


def test_build_pack_writes_patches_on_one_canvas(pack_root: Path) -> None:
    manifest = json.loads((pack_root / "testy" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["size"] == list(SIZE)
    assert all(manifest["silhouette_iou"][s] > 0.99 for s in pack.LAYERS)
    assert all(manifest["changed_px"][s] > 0 for s in pack.LAYERS)
    blink = Image.open(pack_root / "testy" / "blink.png")
    alpha = np.asarray(blink.getchannel("A"))
    assert alpha[100, 80] > 0                     # eye area is in the patch
    assert alpha[200, 100] == 0                   # body far from the face is not


def test_build_pack_refuses_frames_that_never_change(tmp_path: Path) -> None:
    for state in ("base", *pack.LAYERS):
        _figure().save(tmp_path / f"{state}.png")
    with pytest.raises(ValueError, match="nothing to animate"):
        build.build_pack(tmp_path, tmp_path / "out", "same", "same")


def test_load_pack_and_pose_map(pack_root: Path) -> None:
    p = pack.load_pack("pngtuber/testy", root=pack_root)
    assert p.name == "測試"
    assert p.expression_for("shocked") == "surprised"     # default map
    assert p.expression_for("think") == "smug"            # manifest override
    assert p.expression_for("unknown") == "neutral"


@pytest.mark.parametrize("ref", ["pngtuber/", "pngtuber/../x", "a/b", ".hidden"])
def test_pack_dir_rejects_bad_refs(ref: str, tmp_path: Path) -> None:
    with pytest.raises(pack.PackError):
        pack.pack_dir(ref, tmp_path)


def test_load_pack_reports_missing_layers(pack_root: Path) -> None:
    (pack_root / "testy" / "smug.png").unlink()
    with pytest.raises(pack.PackError, match="smug"):
        pack.load_pack("testy", root=pack_root)


def test_load_pack_rejects_unknown_expression(pack_root: Path) -> None:
    path = pack_root / "testy" / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["pose_map"] = {"idle": "angry"}
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(pack.PackError, match="angry"):
        pack.load_pack("testy", root=pack_root)


def test_mouth_levels_threshold_and_hold() -> None:
    env = np.array([0, 0.2, 0.0, 0.0, 0.6, 0.6, 0.6, 0.1, 0.0, 0.0])
    levels = motion.mouth_levels(env, hold=2)
    # a shape holds >= 2 frames: the 1-frame dip at i=2 stays half, the reopen at i=4 waits a frame
    assert levels.tolist() == [0, 1, 1, 0, 0, 2, 2, 0, 0, 0]


def test_host_frames_follow_cues_and_skip_blinks_when_surprised(pack_root: Path) -> None:
    p = pack.load_pack("testy", root=pack_root)
    cues = (SceneCue(1, 0.0, 30.0, "shocked"), SceneCue(2, 30.0, 60.0, "deadpan"))
    fps, n = 10.0, 600
    frames = motion.host_frames(cues, np.zeros(n), fps, n, p, seed=3)
    assert {f.expression for f in frames[:300]} == {"surprised"}
    assert {f.expression for f in frames[300:]} == {"speechless"}
    assert not any(f.blink for f in frames[:300])
    assert any(f.blink for f in frames[300:])                 # 30 s always holds a blink
    assert all(abs(f.angle) <= motion.SWAY_DEG + 1e-9 for f in frames)
    assert all(1.0 <= f.stretch <= 1.0 + motion.BREATH_SCALE + 1e-9 for f in frames)


@pytest.mark.parametrize("placement", [render.LANDSCAPE, render.VERTICAL])
def test_placement_keeps_the_host_out_of_forbidden_zones(pack_root: Path, placement: render.Placement) -> None:
    p = pack.load_pack("testy", root=pack_root)
    composer = render.Composer(p, placement)
    worst = [motion.HostFrame("neutral", 2, False, 1.0 + motion.BREATH_SCALE, a, motion.BOUNCE_PX)
             for a in (-motion.SWAY_DEG, motion.SWAY_DEG)]
    for frame in worst:
        layer = Image.new("RGBA", placement.frame, (0, 0, 0, 0))
        layer.alpha_composite(composer.canvas(frame), placement.origin)
        alpha = np.asarray(layer.getchannel("A"))
        assert alpha.any()
        for name, r in placement.forbidden.items():
            assert not (alpha[r.y0:r.y1, r.x0:r.x1] > 8).any(), f"{placement.name} host enters {name}"


def test_clearance_check_catches_a_bad_placement(pack_root: Path) -> None:
    """Control for the test above: shifted left into the subtitle band, pixels are found."""
    from dataclasses import replace

    bad = replace(render.LANDSCAPE, margin_x=400)
    layer = Image.new("RGBA", bad.frame, (0, 0, 0, 0))
    layer.alpha_composite(render.Composer(pack.load_pack("testy", root=pack_root), bad).canvas(
        motion.HostFrame("neutral", 0, False, 1.0, 0.0, 0.0)), bad.origin)
    r = bad.forbidden["subtitles"]
    assert (np.asarray(layer.getchannel("A"))[r.y0:r.y1, r.x0:r.x1] > 8).any()


def test_composer_caches_one_face_per_state(pack_root: Path) -> None:
    composer = render.Composer(pack.load_pack("testy", root=pack_root), render.LANDSCAPE)
    for angle in (0.0, 0.5, 1.0):
        composer.canvas(motion.HostFrame("smug", 1, False, 1.0, angle, 0.0))
    assert len(composer._faces) == 1


def test_channel_mascot_pngtuber_needs_a_pack_ref() -> None:
    from content_farm.production.channels import Mascot

    assert Mascot(name="x", ref="pngtuber/frog-scribe", rig_ready=True, host="pngtuber").host == "pngtuber"
    assert Mascot(name="x", ref="chipcat").host == "rig"
    with pytest.raises(ValueError, match="pngtuber/"):
        Mascot(name="x", ref="frog", host="pngtuber")


def test_small_o_mouth_is_drawn_at_the_original_mouth(pack_root: Path) -> None:
    folder = pack_root / "testy"
    build.apply_mouth_mode(folder, "small_o", center=(100, 134), cover=(30, 12), o_sizes=((8, 9), (11, 13)))
    p = pack.load_pack("testy", root=pack_root)
    assert p.mouth_mode == "small_o"
    alpha = np.asarray(p.layers["mouth_open"].getchannel("A"))
    ys, xs = np.nonzero(alpha > 128)
    assert abs(xs.mean() - 100) < 2 and abs(ys.mean() - 134) < 2     # centred on the original mouth
    assert alpha[200, 100] == 0 and alpha[100, 80] == 0                # body and eyes untouched


def test_mouth_mode_none_keeps_the_mouth_still(pack_root: Path) -> None:
    build.apply_mouth_mode(pack_root / "testy", "none")
    composer = render.Composer(pack.load_pack("testy", root=pack_root), render.LANDSCAPE)
    closed = np.asarray(composer.face("neutral", 0, False))
    talking = np.asarray(composer.face("neutral", 2, False))
    assert np.array_equal(closed, talking)


def test_mouth_mode_is_validated(pack_root: Path) -> None:
    with pytest.raises(ValueError, match="mouth mode"):
        build.apply_mouth_mode(pack_root / "testy", "wide")
    with pytest.raises(ValueError, match="center"):
        build.apply_mouth_mode(pack_root / "testy", "small_o")


def _make_25d(pack_root: Path) -> None:
    """Depth: a dome, nearest in the middle of the body, 0 outside it."""
    folder = pack_root / "testy"
    alpha = np.asarray(Image.open(folder / "base.png").getchannel("A")) > 128
    yy, xx = np.mgrid[0:SIZE[1], 0:SIZE[0]]
    dome = np.clip(1 - ((xx - 100) / 70.0) ** 2 - ((yy - 135) / 95.0) ** 2, 0, 1) * alpha
    Image.fromarray((dome * 65535).astype(np.uint16)).save(folder / "depth.png")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    manifest["motion"] = "2.5d"
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_depth_warp_moves_near_pixels_more_than_far_ones() -> None:
    img = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((18, 0, 21, 19), fill=(255, 0, 0, 255))   # a red bar in the middle
    near, far = np.ones((20, 40), np.float32), np.zeros((20, 40), np.float32)
    shifted = np.asarray(render.depth_warp(img, near, dx=8, dy=0).getchannel("A"))
    behind = np.asarray(render.depth_warp(img, far, dx=8, dy=0).getchannel("A"))
    assert np.nonzero(shifted[10] > 128)[0].mean() == pytest.approx(19.5 + 4, abs=0.6)   # +dx·½
    assert np.nonzero(behind[10] > 128)[0].mean() == pytest.approx(19.5 - 4, abs=0.6)    # -dx·½


def test_25d_pack_needs_its_depth_map(pack_root: Path) -> None:
    _make_25d(pack_root)
    assert pack.load_pack("testy", root=pack_root).depth is not None
    (pack_root / "testy" / "depth.png").unlink()
    with pytest.raises(pack.PackError, match="depth.png"):
        pack.load_pack("testy", root=pack_root)


@pytest.mark.parametrize("placement", [render.LANDSCAPE, render.VERTICAL])
def test_25d_worst_case_stays_out_of_forbidden_zones(pack_root: Path, placement: render.Placement) -> None:
    _make_25d(pack_root)
    composer = render.Composer(pack.load_pack("testy", root=pack_root), placement)
    for yaw in (-1.0, 1.0):
        frame = motion.HostFrame("neutral", 2, False, 1.0 + motion.BREATH_SCALE, motion.SWAY_DEG * yaw,
                                 motion.BOUNCE_PX, yaw=yaw, nod=-yaw, squash=motion.TALK_SQUASH)
        layer = Image.new("RGBA", placement.frame, (0, 0, 0, 0))
        layer.alpha_composite(composer.canvas(frame), placement.origin)
        alpha = np.asarray(layer.getchannel("A"))
        for name, r in placement.forbidden.items():
            assert not (alpha[r.y0:r.y1, r.x0:r.x1] > 8).any(), f"2.5D host enters {name}"


FX = {"kind": "bubbles", "emit": [100, 150], "surface_y": 60, "x_range": [40, 160]}


def test_bubbles_follow_the_voice_and_stay_in_the_water() -> None:
    fps, n = 30.0, 600
    loud = motion.bubble_track(np.full(n, 0.9), fps, n, FX, seed=1)
    quiet = motion.bubble_track(np.zeros(n), fps, n, FX, seed=1)
    assert motion.bubble_track(np.full(n, 0.9), fps, n, FX, seed=1) == loud          # deterministic
    count = lambda track: sum(len(f) for f in track)  # noqa: E731
    assert count(loud) > 5 * count(quiet) > 0                                         # idle: now and then one
    assert max(b[2] for f in loud for b in f) > max(b[2] for f in quiet for b in f)    # louder → bigger
    for frame in loud + quiet:
        for x, y, r, a in frame:
            assert y - r > FX["surface_y"] and FX["x_range"][0] <= x - r and x + r <= FX["x_range"][1]
            assert 0 < a <= 1


def test_speech_fx_is_validated(pack_root: Path) -> None:
    build.set_manifest(pack_root / "testy", speech_fx=FX)
    assert pack.load_pack("testy", root=pack_root).speech_fx == FX
    build.set_manifest(pack_root / "testy", speech_fx={"kind": "sparkles"})
    with pytest.raises(pack.PackError, match="speech_fx"):
        pack.load_pack("testy", root=pack_root)


def test_erase_mouth_removes_it_everywhere_and_keeps_the_silhouette(pack_root: Path) -> None:
    folder = pack_root / "testy"
    iou = build.erase_mouth(folder, [((100, 134), (34, 16)), ((100, 136), (30, 22))])
    assert iou["base_before_vs_after"] == 1.0
    p = pack.load_pack("testy", root=pack_root)
    assert p.mouth_mode == "none"
    for state in ("neutral", "surprised", "smug"):
        img = p.base.copy()
        if state != "neutral":
            img.alpha_composite(p.layers[state])
        rgb = np.asarray(img.convert("RGB"), dtype=int)
        assert rgb[128:144, 90:111].min() > 60, f"{state}: dark mouth pixels left"   # the mouth is gone
        assert rgb[100, 80].max() < 60                                                 # the eye is not


def test_committed_packs_load() -> None:
    for folder in sorted(p for p in pack.PACK_ROOT.iterdir() if p.is_dir()):
        loaded = pack.load_pack(folder.name)
        assert loaded.base.getchannel("A").getbbox() is not None


def test_legacy_profile_is_the_shipped_motion() -> None:
    from content_farm.explainer.pngtuber.profiles import LEGACY, get_profile

    assert get_profile(None) is LEGACY and get_profile("legacy") is LEGACY
    assert (LEGACY.mouth_half_at, LEGACY.mouth_open_at, LEGACY.mouth_hold) == (0.12, 0.45, 2)
    assert (LEGACY.bounce_px, LEGACY.sway_deg, LEGACY.breath_scale) == (6.0, 1.4, 0.018)
    with pytest.raises(ValueError, match="unknown motion profile"):
        get_profile("nope")


def test_mouth_open_max_eases_a_long_vowel_to_half() -> None:
    levels = motion.mouth_levels(np.ones(20), hold=2, half_at=0.2, open_at=0.6, open_max=5)
    assert levels.tolist()[:10] == [2, 2, 2, 2, 2, 1, 1, 2, 2, 2]
    assert 1 in levels.tolist()
    assert 1 not in motion.mouth_levels(np.ones(20), hold=2).tolist()[2:]    # legacy: stays wide open


def test_beat_track_hops_once_per_onset_and_lands_with_a_squash() -> None:
    env = np.zeros(40)
    env[10:] = 0.9                       # one sharp onset at frame 10
    hop, stretch = motion.beat_track(env)
    assert hop[:10].max() == 0 and hop[10:10 + motion.BEAT_FRAMES].min() > 0
    assert stretch[10 + motion.BEAT_FRAMES:10 + motion.BEAT_FRAMES + motion.BEAT_LAND_FRAMES].max() < 0
    assert (np.diff((hop > 0).astype(int)) == 1).sum() == 1


def test_head_warp_pins_the_feet() -> None:
    img = Image.new("RGBA", (40, 60), (200, 50, 50, 255))
    out = np.asarray(render.head_warp(img, 0.0, 6.0))
    assert out[-1, 20, 3] == 255 and tuple(out[-1, 20, :3]) == (200, 50, 50)    # bottom row unchanged
    shifted = np.asarray(render.head_warp(Image.fromarray(np.tile(np.arange(60, dtype=np.uint8)[:, None, None] * 4,
                                                                     (1, 40, 4))), 0.0, 6.0))
    assert shifted[0, 0, 0] == 0 and shifted[1, 0, 0] < 8                      # head rows moved ~dy down, edge-held
    assert shifted[-1, 0, 0] == 59 * 4                                          # feet row identical


def test_mascot_motion_profile_is_validated() -> None:
    from content_farm.production.channels import Mascot

    assert Mascot(name="x", ref="pngtuber/x", host="pngtuber").motion_profile == "legacy"
    assert Mascot(name="x", ref="pngtuber/x", host="pngtuber", motion_profile="calm").motion_profile == "calm"
    with pytest.raises(ValueError, match="motion_profile"):
        Mascot(name="x", ref="pngtuber/x", host="pngtuber", motion_profile="wobble")
