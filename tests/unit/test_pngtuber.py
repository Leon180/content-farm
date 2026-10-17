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


def test_committed_packs_load() -> None:
    for folder in sorted(p for p in pack.PACK_ROOT.iterdir() if p.is_dir()):
        loaded = pack.load_pack(folder.name)
        assert loaded.base.getchannel("A").getbbox() is not None
