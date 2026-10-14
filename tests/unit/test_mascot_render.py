"""Rig rendering: 3 s end-to-end smoke, layout clearance, determinism (real Chromium + ffmpeg)."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("playwright")
if shutil.which("ffmpeg") is None:
    pytest.skip("ffmpeg not installed", allow_module_level=True)

from content_farm.explainer.mascot.motion import Frame  # noqa: E402
from content_farm.explainer.mascot.overlay import FORBIDDEN, ORIGIN, Rect  # noqa: E402
from content_farm.explainer.mascot.params import PARAM_DEFAULTS, POSES, pose_vector  # noqa: E402
from content_farm.explainer.mascot.render import CANVAS_H, CANVAS_W, capture_pngs  # noqa: E402
from content_farm.explainer.mascot.run import probe_video, run_overlay  # noqa: E402


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, timeout=120)


def _extreme(pose: str, **extra: float) -> Frame:
    """A frame with ``pose`` fully applied and everything pushed outward."""
    v = pose_vector(pose)
    params = {**PARAM_DEFAULTS, "ParamArmR": v["ArmR"], "ParamArmRWave": v["WaveAmp"],
              "ParamAngleX": v["AngleX"] - 8, "ParamAngleZ": v["AngleZ"] - 10,
              "ParamBodyAngleX": v["BodyAngleX"] - 3, "ParamBodyY": v["BodyY"],
              "ParamEyeLOpen": v["EyeOpen"], "ParamEyeROpen": v["EyeOpen"],
              "ParamMouthOpenY": 1.0, "ParamTailPuff": v["TailPuff"], "ParamTail": 1.0,
              "ParamTail2": -1.0, "ParamEarL": 25, "ParamEarR": 25, "ParamBreath": 1.0,
              "ParamBubble": 1.0, **extra}
    return Frame(params=params, say="這個數字其實是十個字喔")


def _alpha(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))[:, :, 3]


def test_cat_never_covers_subtitles_or_meta_row() -> None:
    frames = [_extreme(p) for p in POSES] + [_extreme("wave", ParamArmRWave=-14)]
    for frame, png in zip(frames, capture_pngs(frames)):
        alpha = _alpha(png)
        assert alpha.shape == (CANVAS_H, CANVAS_W)
        assert alpha.max() == 255  # something was drawn
        # control: the same mapping does find the cat's own body (frame coords)
        body = Rect(1700, 950, 1800, 1050).to_canvas(ORIGIN)
        assert alpha[body.y0:body.y1, body.x0:body.x1].min() == 255
        for name, rect in FORBIDDEN.items():
            r = rect.to_canvas(ORIGIN).clip(CANVAS_W, CANVAS_H)
            if r is not None:
                assert alpha[r.y0:r.y1, r.x0:r.x1].max() == 0, f"cat overlaps {name}"


def test_cat_height_is_30_to_40_percent_of_frame() -> None:
    png = list(capture_pngs([Frame(params=dict(PARAM_DEFAULTS), say=None)]))[0]
    rows = np.nonzero(_alpha(png).max(axis=1) > 128)[0]
    assert 0.30 <= (rows[-1] - rows[0]) / 1080 <= 0.40


def test_same_params_same_pixels() -> None:
    """Separate browser sessions, different history before the frame → identical pixels."""
    frame = _extreme("point")
    first = list(capture_pngs([frame]))[0]
    second = list(capture_pngs([_extreme("shocked"), frame]))[1]
    assert np.array_equal(np.asarray(Image.open(io.BytesIO(first))),
                          np.asarray(Image.open(io.BytesIO(second))))


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    """3 s run: two scenes (point, deadpan) with tone audio and a flat draft."""
    (tmp_path / "audio").mkdir()
    (tmp_path / "assembly").mkdir()
    for i, dur in ((1, 1.5), (2, 1.5)):
        _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=300:duration={dur}", "-af", "volume=0.5",
                str(tmp_path / "audio" / f"scene_{i:03d}.mp3"))
    _ffmpeg("-f", "lavfi", "-i", "color=c=0x15171c:s=1920x1080:r=30:d=3", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(tmp_path / "assembly" / "draft.mp4"))
    script = {"scenes": [
        {"scene_number": 1, "mascot": {"pose": "point", "say": "看這裡"}},
        {"scene_number": 2, "mascot": {"pose": "deadpan"}},
    ]}
    (tmp_path / "script.json").write_text(json.dumps(script), encoding="utf-8")
    return tmp_path


def test_three_second_smoke(run_dir: Path) -> None:
    result = run_overlay(run_dir, workers=2)
    assert result.rendered_frames == 90
    alpha = probe_video(result.alpha_video)
    assert alpha.frames == 90 and (alpha.width, alpha.height) == (CANVAS_W, CANVAS_H)
    pix = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=pix_fmt", "-of", "csv=p=0", str(result.alpha_video)],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert pix.startswith("yuva")
    final = probe_video(result.final)
    assert final.frames == 90 and (final.width, final.height) == (1920, 1080)
    assert (run_dir / "assembly" / "draft.mp4").is_file()
