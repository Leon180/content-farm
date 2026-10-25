"""Static-shot detection on a finished cut (quality v5 item 2).

The final video is sampled at a few frames per second as tiny grey pictures. Hard cuts split it into shots; each shot is
classified from how its frames change:

* ``static``  - almost nothing changes (a held picture; a changing subtitle line or a blinking mascot does not count)
* ``pan``     - the whole picture slides one way (a camera move over a still: parallax, Ken Burns, a pan)
* ``motion``  - anything else that moves (footage, Wan clips, diagrams, zooms)

A ``static`` shot longer than :data:`DEAD_ZONE_SECONDS` is a *dead zone*: ten seconds of nothing moving is where a viewer
leaves. The idea (per-shot static / pan / motion labels) comes from ffmpeg-skill's shot analysis; this implementation is
ours (numpy over ffmpeg's raw grey frames, FFT phase correlation for the pan test).

``scan`` is the only function that runs ffmpeg; ``classify`` works on a frame array and is what the tests exercise.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPORT = Path("qc") / "static_scan.json"
SAMPLE_FPS = 4
FRAME_SIZE = (96, 54)               # width, height of the grey samples
CUT_DIFF = 14.0                     # mean grey-level change between samples that marks a hard cut
CALM_STEP = 0.2                     # grey-level change between neighbouring samples below this: nothing moves
                                    # (measured: a text page 0.001, a parallax picture 0.4, a mascot-only page ~0.1)
BLIP_SAMPLES = 3                # a subtitle line changing is a short bump inside a calm stretch
BLIP_MAX_DIFF = 10.0
MIN_STATIC_SECONDS = 2.0
PAN_EXPLAINED = 0.5                 # share of the frame-to-frame change a single global slide must explain to be a pan
PAN_SHIFT = 0.15                    # median shift in samples-pixels per step needed for a pan
DEAD_ZONE_SECONDS = 10.0
MIN_SHOT_SAMPLES = 3


@dataclass(frozen=True)
class Shot:
    start: float
    end: float
    kind: str            # static | pan | motion
    energy: float        # median grey-level change per sample step

    @property
    def seconds(self) -> float:
        return self.end - self.start

    def to_json(self) -> dict:
        return {"start": round(self.start, 2), "end": round(self.end, 2), "seconds": round(self.seconds, 2),
                "kind": self.kind, "energy": round(self.energy, 3)}


def _step_diffs(frames: np.ndarray) -> np.ndarray:
    return np.abs(np.diff(frames.astype(np.float32), axis=0)).mean(axis=(1, 2))


def _shift_and_explained(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Global translation magnitude (pixels) between two grey frames and how much of their difference that shift explains
    (1 = the second frame is the first one slid; 0 = sliding does not help, e.g. only one object moved)."""
    fa, fb = np.fft.fft2(a - a.mean()), np.fft.fft2(b - b.mean())
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-9
    corr = np.fft.ifft2(cross).real
    y, x = np.unravel_index(int(np.argmax(corr)), corr.shape)
    h, w = corr.shape
    dy, dx = (y - h if y > h // 2 else y), (x - w if x > w // 2 else x)
    margin = 6
    inner = (slice(margin, h - margin), slice(margin, w - margin))
    raw = float(np.abs(a - b)[inner].mean())
    if raw < 1e-6:
        return 0.0, 0.0
    slid = min(float(np.abs(np.roll(a, (sy * dy, sx * dx), axis=(0, 1)) - b)[inner].mean())
               for sy, sx in ((1, 1), (-1, -1)))
    return float(np.hypot(dx, dy)), max(0.0, 1.0 - slid / raw)


def _moving_kind(frames: np.ndarray) -> str:
    """``pan`` when the whole picture slides one way (a camera move), else ``motion``."""
    stride = max(1, SAMPLE_FPS // 2)           # half a second apart: a slow pan shows up as a clear shift
    pairs = [_shift_and_explained(frames[i].astype(np.float32), frames[i + stride].astype(np.float32))
             for i in range(0, len(frames) - stride, stride)]
    if not pairs:
        return "motion"
    shifts, explained = zip(*pairs)
    if float(np.median(explained)) >= PAN_EXPLAINED and float(np.median(shifts)) >= PAN_SHIFT:
        return "pan"
    return "motion"


def _calm_mask(step: np.ndarray) -> np.ndarray:
    """True where nothing moves; short blips (a subtitle line changing) between calm stretches are absorbed."""
    calm = step < CALM_STEP
    n = len(calm)
    i = 0
    while i < n:
        if calm[i]:
            i += 1
            continue
        j = i
        while j < n and not calm[j]:
            j += 1
        if 0 < i and j < n and j - i <= BLIP_SAMPLES and float(step[i:j].max()) < BLIP_MAX_DIFF:
            calm[i:j] = True
        i = j
    return calm


def _runs(mask: np.ndarray) -> list[tuple[int, int, bool]]:
    runs: list[tuple[int, int, bool]] = []
    start = 0
    for i in range(1, len(mask) + 1):
        if i == len(mask) or mask[i] != mask[start]:
            runs.append((start, i, bool(mask[start])))
            start = i
    return runs


def classify(frames: np.ndarray, fps: float = SAMPLE_FPS, offset: float = 0.0) -> list[Shot]:
    """Split ``frames`` (n, h, w grey, sampled at ``fps``) into shots and label each.

    A shot ends at a hard cut or where the picture settles into a calm stretch (a count-up that finished, a still
    image after its entrance); calm stretches of at least ``MIN_STATIC_SECONDS`` become ``static`` shots."""
    if len(frames) < 2:
        return []
    step = _step_diffs(frames)
    calm = _calm_mask(step)
    cut_at = {int(i) + 1 for i in np.flatnonzero(step > CUT_DIFF)}
    pieces: list[tuple[int, int, str | None]] = []
    for run_start, run_end, is_calm in _runs(calm):
        begin = run_start
        for cut in sorted(c for c in cut_at if run_start < c < run_end) + [run_end]:
            if cut - begin >= MIN_SHOT_SAMPLES:
                long_enough = (cut - begin) / fps >= MIN_STATIC_SECONDS
                pieces.append((begin, cut, "static" if is_calm and long_enough else None))
            begin = cut
    shots: list[Shot] = []
    for begin, end, kind in _join_moving(pieces, cut_at):
        inner = step[begin:end - 1]
        label = kind or _moving_kind(frames[begin:end])
        shots.append(Shot(offset + begin / fps, offset + end / fps, label, float(np.median(inner))))
    return shots


def _join_moving(pieces: list[tuple[int, int, str | None]], cut_at: set[int]) -> list[tuple[int, int, str | None]]:
    """Touching not-static pieces with no hard cut between them are one moving shot (a parallax turn-around is not a cut)."""
    out: list[tuple[int, int, str | None]] = []
    for begin, end, kind in pieces:
        if out and kind is None and out[-1][2] is None and out[-1][1] == begin and begin not in cut_at:
            out[-1] = (out[-1][0], end, None)
        else:
            out.append((begin, end, kind))
    return out


def dead_zones(shots: list[Shot], limit: float = DEAD_ZONE_SECONDS) -> list[Shot]:
    return [s for s in shots if s.kind == "static" and s.seconds > limit]


def read_frames(video: Path, fps: int = SAMPLE_FPS) -> np.ndarray:
    """Decode ``video`` to (n, h, w) uint8 grey samples."""
    width, height = FRAME_SIZE
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video), "-an", "-vf",
         f"fps={fps},scale={width}:{height}:flags=area,format=gray", "-f", "rawvideo", "-"],
        capture_output=True, timeout=3600)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg could not sample {video.name}: {proc.stderr.decode(errors='replace')[-300:]}")
    data = np.frombuffer(proc.stdout, dtype=np.uint8)
    n = data.size // (width * height)
    return data[: n * width * height].reshape(n, height, width)


def scan(video: Path) -> list[Shot]:
    return classify(read_frames(video))


def summary(shots: list[Shot]) -> dict:
    total = sum(s.seconds for s in shots) or 1.0
    by_kind = {k: round(sum(s.seconds for s in shots if s.kind == k), 1) for k in ("static", "pan", "motion")}
    zones = dead_zones(shots)
    return {"shots": len(shots), "seconds_by_kind": by_kind, "static_share": round(by_kind["static"] / total, 3),
            "dead_zones": [z.to_json() for z in zones], "dead_zone_seconds": round(sum(z.seconds for z in zones), 1),
            "limit_seconds": DEAD_ZONE_SECONDS}


def write_report(run_dir: Path, video: Path, shots: list[Shot]) -> dict:
    data = {"video": video.name, "sample_fps": SAMPLE_FPS, **summary(shots), "all_shots": [s.to_json() for s in shots]}
    path = run_dir / REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data
