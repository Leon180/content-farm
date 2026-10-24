"""Static / pan / motion shot labels and dead zones (quality v5 item 2), on synthetic frames."""

from __future__ import annotations

import json

import numpy as np

from content_farm.production import static_scan
from content_farm.review import score_ledger

H, W = 54, 96
FPS = static_scan.SAMPLE_FPS


def _texture(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, size=(H, W * 2)).astype(np.float32)
    kernel = np.ones(15, dtype=np.float32) / 15        # smooth, so a one-pixel slide is a small change
    smooth = np.apply_along_axis(lambda row: np.convolve(row, kernel, mode="same"), 1, base)
    return np.apply_along_axis(lambda col: np.convolve(col, kernel, mode="same"), 0, smooth)


def _hold(seconds: float, seed: int = 1) -> np.ndarray:
    return np.repeat(_texture(seed)[None, :, :W], int(seconds * FPS), axis=0)


def _pan(seconds: float, seed: int = 2, speed: float = 1.0) -> np.ndarray:
    tex = _texture(seed)
    return np.stack([tex[:, int(i * speed):int(i * speed) + W] for i in range(int(seconds * FPS))])


def _noise(seconds: float, seed: int = 3) -> np.ndarray:
    """A bright block sweeping over a held background: something moves, the camera does not."""
    background = _texture(seed)[:, :W]
    frames = np.repeat(background[None], int(seconds * FPS), axis=0).copy()
    for i in range(len(frames)):
        x = (i * 5) % (W - 16)
        frames[i, 10:26, x:x + 16] = 255.0
    return frames


def _kinds(frames: np.ndarray) -> list[tuple[str, float]]:
    return [(s.kind, round(s.seconds)) for s in static_scan.classify(frames.astype(np.uint8))]


def test_a_held_picture_is_static_and_over_ten_seconds_is_a_dead_zone() -> None:
    shots = static_scan.classify(_hold(14).astype(np.uint8))
    assert [s.kind for s in shots] == ["static"]
    zones = static_scan.dead_zones(shots)
    assert len(zones) == 1 and zones[0].seconds > static_scan.DEAD_ZONE_SECONDS


def test_ten_seconds_or_less_is_not_a_dead_zone() -> None:
    assert static_scan.dead_zones(static_scan.classify(_hold(8).astype(np.uint8))) == []


def test_a_sliding_picture_is_a_pan_and_noise_is_motion() -> None:
    assert _kinds(_pan(8)) == [("pan", 8)]
    assert _kinds(_noise(6))[0][0] == "motion"


def test_a_hard_cut_splits_shots_and_each_is_labelled() -> None:
    frames = np.concatenate([_hold(5, seed=4), _noise(5, seed=5), _hold(12, seed=6)])
    kinds = [s.kind for s in static_scan.classify(frames.astype(np.uint8))]
    assert kinds == ["static", "motion", "static"]


def test_a_changing_subtitle_line_does_not_break_a_held_picture() -> None:
    frames = _hold(16).copy()
    for start in (20, 40):                              # two caption swaps: a few samples of a small bright patch change
        frames[start:start + 2, 40:50, 20:70] += 60
    shots = static_scan.classify(np.clip(frames, 0, 255).astype(np.uint8))
    assert [s.kind for s in shots] == ["static"] and static_scan.dead_zones(shots)


def test_summary_and_report_and_ledger_entry(tmp_path) -> None:
    frames = np.concatenate([_noise(4), _hold(13, seed=7)]).astype(np.uint8)
    shots = static_scan.classify(frames)
    data = static_scan.write_report(tmp_path, tmp_path / "release.mp4", shots)
    assert data["dead_zone_seconds"] > 10 and data["seconds_by_kind"]["static"] > 10
    assert json.loads((tmp_path / static_scan.REPORT).read_text(encoding="utf-8"))["dead_zones"]
    score_ledger.record_qc(tmp_path, "static_scan", {k: v for k, v in data.items() if k != "all_shots"})
    ledger = score_ledger.load(tmp_path)
    assert ledger["qc"]["static_scan"]["dead_zones"] and "stages" in ledger


def test_record_qc_keeps_scores_already_in_the_ledger(tmp_path) -> None:
    card = {"round": 1, "verdict": {"scores": {"x": 1}, "pass": True, "reasons": [], "issues": []}}
    score_ledger.record(tmp_path, "deck", "deck", card)
    score_ledger.record_qc(tmp_path, "static_scan", {"dead_zones": []})
    ledger = score_ledger.load(tmp_path)
    assert ledger["stages"]["deck"]["scores"] == {"x": 1} and ledger["qc"]["static_scan"]["dead_zones"] == []
