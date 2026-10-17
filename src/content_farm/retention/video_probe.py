"""Picture-side retention metrics from the rendered video (no model, ffmpeg + numpy).

The frame is sampled at ``FPS`` frames per second, greyscale, downscaled, and cropped to the
*content* area: the host (bottom-right), the meta row and the burned subtitles are left out,
because a talking mascot or a new subtitle line must not count as "the picture changed".

Outputs per run:
- visual events: times where the content area changes (cut, reveal, push-in step);
- still stretches: content area unchanged for > ``STILL_MAX`` seconds;
- blank frames: near-uniform content (an empty transition card);
- held blends (殘影): a still that is a mix of the picture before and after it;
- contrast: share of frames with low RMS contrast.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

FPS = 4
SIZE = (156, 83)                       # content crop 1560x830 of a 1920x1080 frame, /10
CROP_16x9 = "crop=1560:830:0:0"        # leaves out host column (x≥1560) and rows y≥830
CROP_9x16 = "crop=1080:1220:0:0"       # vertical: above the subtitle band
STILL_DIFF = 0.6        # mean |Δ| (0–255) below which two samples are "the same picture"
EVENT_DIFF = 4.0        # mean |Δ| above which a sample counts as a visual event
STILL_MAX = 8.0         # 🟡 research §5.2: long videos, longest static shot ≤ 8 s
BLANK_STD = 4.0         # content std below this = blank / single-colour frame
LOW_CONTRAST_STD = 18.0


@dataclass(frozen=True)
class Span:
    start: float
    end: float

    @property
    def seconds(self) -> float:
        return round(self.end - self.start, 2)


@dataclass(frozen=True)
class VideoReport:
    duration: float
    events: list[float]
    stills: list[Span]                 # every still ≥ 2 s (for the timeline)
    long_stills: list[Span]            # > STILL_MAX
    longest_still: float
    blanks: list[Span]
    held_blends: list[Span]
    cuts_per_minute: float
    low_contrast_share: float

    def as_dict(self) -> dict:
        data = asdict(self)
        for key in ("stills", "long_stills", "blanks", "held_blends"):
            data[key] = [{"start": s.start, "end": s.end, "seconds": s.seconds} for s in getattr(self, key)]
        return data


def sample_frames(video: Path, *, vertical: bool = False) -> np.ndarray:
    """(n, h, w) uint8 greyscale samples of the content area."""
    crop, size = (CROP_9x16, (108, 122)) if vertical else (CROP_16x9, SIZE)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video), "-an",
           "-vf", f"fps={FPS},{crop},scale={size[0]}:{size[1]}:flags=area,format=gray",
           "-f", "rawvideo", "-"]
    out = subprocess.run(cmd, capture_output=True, timeout=3600)
    if out.returncode != 0:
        raise RuntimeError(f"ffmpeg frame sampling failed: {out.stderr.decode(errors='replace')[-400:]}")
    frame = size[0] * size[1]
    count = len(out.stdout) // frame
    if count == 0:
        raise RuntimeError(f"no frames decoded from {video}")
    return np.frombuffer(out.stdout[: count * frame], dtype=np.uint8).reshape(count, size[1], size[0])


def _runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """[start, end) index runs where mask is True and the run is ≥ min_len long."""
    runs, start = [], None
    for i, value in enumerate(np.append(mask, False)):
        if value and start is None:
            start = i
        elif not value and start is not None:
            if i - start >= min_len:
                runs.append((start, i))
            start = None
    return runs


def _span(a: int, b: int) -> Span:
    return Span(round(a / FPS, 2), round(b / FPS, 2))


def _held_blends(frames: np.ndarray, diffs: np.ndarray, still_runs: list[tuple[int, int]]) -> list[Span]:
    """A still whose picture is ~halfway between the stills either side of it (stuck cross-fade)."""
    found = []
    for (a, b) in still_runs:
        if a < 3 or b + 3 >= len(frames) or (b - a) < FPS:   # ≥ 1 s hold, with room either side
            continue
        before = frames[a - 3].astype(np.float32)
        after = frames[b + 2].astype(np.float32)
        held = frames[(a + b) // 2].astype(np.float32)
        if np.abs(before - after).mean() < 12:     # neighbours alike: nothing to blend between
            continue
        blend_err = np.abs(held - (before + after) / 2).mean()
        nearest = min(np.abs(held - before).mean(), np.abs(held - after).mean())
        if blend_err < 0.5 * nearest:
            found.append(_span(a, b))
    return found


def analyse_frames(frames: np.ndarray) -> VideoReport:
    as_float = frames.astype(np.int16)
    diffs = np.abs(np.diff(as_float, axis=0)).mean(axis=(1, 2))
    duration = round(len(frames) / FPS, 2)
    events = [round((i + 1) / FPS, 2) for i in np.flatnonzero(diffs > EVENT_DIFF)]
    # collapse an event burst (a cross-fade lasts several samples) into its first sample
    collapsed: list[float] = []
    for t in events:
        if not collapsed or t - collapsed[-1] > 0.5:
            collapsed.append(t)
    still_runs = _runs(diffs < STILL_DIFF, min_len=2 * FPS)
    stills = [_span(a, b + 1) for a, b in still_runs]
    long_stills = [s for s in stills if s.seconds > STILL_MAX]
    stds = frames.reshape(len(frames), -1).std(axis=1)
    blanks = [_span(a, b) for a, b in _runs(stds < BLANK_STD, min_len=FPS)]   # ≥ 1 s
    cuts = len([t for t in collapsed])
    return VideoReport(
        duration=duration, events=collapsed, stills=stills, long_stills=long_stills,
        longest_still=max((s.seconds for s in stills), default=0.0), blanks=blanks,
        held_blends=_held_blends(frames, diffs, still_runs),
        cuts_per_minute=round(cuts / (duration / 60), 1) if duration else 0.0,
        low_contrast_share=round(float((stds < LOW_CONTRAST_STD).mean()), 3),
    )


def probe_video(video: Path, *, vertical: bool = False) -> VideoReport:
    return analyse_frames(sample_frames(video, vertical=vertical))


def frame_at(video: Path, seconds: float, out: Path, width: int = 640) -> Path:
    """One full frame (not cropped) as JPEG, for contact sheets."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{seconds:.2f}", "-i", str(video),
           "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", str(out)]
    result = subprocess.run(cmd, capture_output=True, timeout=120)
    if result.returncode != 0 or not out.is_file():
        raise RuntimeError(f"frame grab at {seconds:.1f}s failed: {result.stderr.decode(errors='replace')[-300:]}")
    return out
