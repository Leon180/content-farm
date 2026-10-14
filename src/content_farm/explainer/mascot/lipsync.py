"""Lip-sync: audio RMS envelope → ``ParamMouthOpenY`` per video frame.

Pipeline per frame: RMS over the frame's window → dBFS → noise gate →
normalise against the loud end of the voiced frames → asymmetric smoothing
(fast attack, slower release) → snap shut after a short silence.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16_000


class AudioError(RuntimeError):
    """Audio could not be decoded."""


@dataclass(frozen=True)
class LipSyncConfig:
    abs_gate_db: float = -50.0    # never open below this level
    rel_gate_db: float = 28.0     # ... or this far below the loud reference
    ref_percentile: float = 95.0  # "loud" = this percentile of voiced frames
    gamma: float = 0.8            # <1 opens the mouth a bit more on mid levels
    attack: float = 0.65          # 0..1 per frame toward a louder target
    release: float = 0.35         # 0..1 per frame toward a quieter target
    close_below: float = 0.06     # snap to 0 under this
    silence_frames: int = 2       # gated frames in a row => mouth fully shut


def decode_mono(path: Path, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Decode any ffmpeg-readable audio to mono float32 in [-1, 1]."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1",
             "-ar", str(sample_rate), "-"],
            capture_output=True, check=True, timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AudioError(f"cannot decode {path}: {exc}") from exc
    return np.frombuffer(result.stdout, dtype=np.float32)


def frame_rms_db(samples: np.ndarray, sample_rate: int, fps: float, n_frames: int) -> np.ndarray:
    """dBFS RMS of each video frame's window ``[i/fps, (i+1)/fps)``; -120 past the end."""
    out = np.full(n_frames, -120.0)
    for i in range(n_frames):
        lo = int(round(i * sample_rate / fps))
        hi = int(round((i + 1) * sample_rate / fps))
        window = samples[lo:hi]
        if window.size:
            rms = float(np.sqrt(np.mean(np.square(window, dtype=np.float64))))
            out[i] = 20 * np.log10(rms + 1e-9)
    return out


def mouth_envelope(db: Sequence[float], config: LipSyncConfig = LipSyncConfig()) -> np.ndarray:
    """Map per-frame dBFS to a smoothed 0..1 mouth opening."""
    levels = np.asarray(db, dtype=np.float64)
    if levels.size == 0:
        return np.zeros(0)
    voiced = levels[levels > config.abs_gate_db]
    if voiced.size == 0:
        return np.zeros(levels.size)
    ref = float(np.percentile(voiced, config.ref_percentile))
    gate = max(config.abs_gate_db, ref - config.rel_gate_db)
    span = max(ref - gate, 1e-6)
    target = np.clip((levels - gate) / span, 0.0, 1.0) ** config.gamma
    target[levels <= gate] = 0.0

    out = np.zeros(levels.size)
    value, quiet = 0.0, 0
    for i, goal in enumerate(target):
        quiet = quiet + 1 if goal == 0.0 else 0
        rate = config.attack if goal > value else config.release
        value += (goal - value) * rate
        if quiet >= config.silence_frames or value < config.close_below:
            value = 0.0
        out[i] = value
    return out


def envelope_for_scenes(
    scene_audio: Sequence[tuple[Path, float]],
    fps: float,
    n_frames: int,
    config: LipSyncConfig = LipSyncConfig(),
    decode=decode_mono,
) -> np.ndarray:
    """Envelope for the whole video from ``(scene audio, start seconds)`` pairs.

    Each scene's audio is placed at its own slide start, so per-slide timing
    (what the video shows) wins over any drift in a concatenated full.mp3.
    """
    db = np.full(n_frames, -120.0)
    for path, start in scene_audio:
        samples = decode(path)
        first = int(round(start * fps))
        count = int(np.ceil(samples.size / SAMPLE_RATE * fps))
        count = max(0, min(count, n_frames - first))
        if count:
            db[first:first + count] = frame_rms_db(samples, SAMPLE_RATE, fps, count)
    return mouth_envelope(db, config)


def envelope_for_track(
    path: Path, fps: float, n_frames: int, config: LipSyncConfig = LipSyncConfig(), decode=decode_mono,
) -> np.ndarray:
    """Envelope from one continuous track (``full.mp3``) starting at t=0."""
    return mouth_envelope(frame_rms_db(decode(path), SAMPLE_RATE, fps, n_frames), config)
