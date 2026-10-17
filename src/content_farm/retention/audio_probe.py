"""Sound-side metrics (ffmpeg ebur128 + numpy; no extra packages).

- loudness: integrated / LRA / true peak and momentary loudness every 100 ms (ffmpeg ebur128);
- pitch: autocorrelation F0 on 40 ms frames → semitone spread per window (monotony);
- energy: RMS dB spread per window; pauses: runs well below the speech level;
- clipping: samples at full scale.

Thresholds are 🟡 (research §5.3–5.4: -14 LUFS / ≤ -1.5 dBTP master, voice -16, BGM 12–18 dB
under the voice); they describe, they do not decide.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RATE = 16000
FRAME = 640            # 40 ms
FFT = 1024
F0_MIN, F0_MAX = 75.0, 450.0
PAUSE_MIN = 0.25       # s

_FRAMELOG = re.compile(r"t:\s*([\d.]+)\s+TARGET:.*?M:\s*(-?[\d.]+|-inf)\s+S:\s*(-?[\d.]+|-inf)")
_INTEGRATED = re.compile(r"Integrated loudness:\s*\n\s*I:\s*(-?[\d.]+) LUFS")
_LRA = re.compile(r"Loudness range:\s*\n\s*LRA:\s*([\d.]+) LU")
_PEAK = re.compile(r"True peak:\s*\n\s*Peak:\s*(-?[\d.]+|-inf) dBFS")


@dataclass(frozen=True)
class Loudness:
    integrated: float
    lra: float
    true_peak: float
    momentary: np.ndarray      # LUFS every 0.1 s (-inf → -120)


def _num(text: str) -> float:
    return -120.0 if text == "-inf" else float(text)


def loudness(media: Path) -> Loudness:
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-v", "verbose", "-i", str(media), "-vn",
           "-af", "ebur128=framelog=verbose:peak=true", "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if out.returncode != 0:
        raise RuntimeError(f"ebur128 failed on {media.name}: {out.stderr[-400:]}")
    err = out.stderr
    momentary = np.array([_num(m) for _, m, _ in _FRAMELOG.findall(err)], dtype=np.float64)
    found = [_INTEGRATED.search(err), _LRA.search(err), _PEAK.search(err)]
    if not all(found) or momentary.size == 0:
        raise RuntimeError(f"could not parse ebur128 summary for {media.name}")
    return Loudness(float(found[0].group(1)), float(found[1].group(1)), _num(found[2].group(1)), momentary)


def decode(media: Path, rate: int = RATE) -> np.ndarray:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(media), "-vn", "-ac", "1",
           "-ar", str(rate), "-f", "f32le", "-"]
    out = subprocess.run(cmd, capture_output=True, timeout=3600)
    if out.returncode != 0:
        raise RuntimeError(f"decode failed on {media.name}: {out.stderr.decode(errors='replace')[-300:]}")
    return np.frombuffer(out.stdout, dtype=np.float32).copy()


def clipped_samples(media: Path) -> int:
    """Samples at (or within 0.1 % of) digital full scale, at 48 kHz, any channel."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(media), "-vn", "-ar", "48000",
           "-f", "f32le", "-"]
    out = subprocess.run(cmd, capture_output=True, timeout=3600)
    if out.returncode != 0:
        raise RuntimeError(f"decode failed on {media.name}")
    pcm = np.frombuffer(out.stdout, dtype=np.float32)
    return int((np.abs(pcm) >= 0.999).sum())


def frames_of(signal: np.ndarray, size: int = FRAME) -> np.ndarray:
    n = len(signal) // size
    return signal[: n * size].reshape(n, size)


def frame_db(signal: np.ndarray) -> np.ndarray:
    """RMS level (dBFS) of each 40 ms frame."""
    frames = frames_of(signal)
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-6))


def pitch_track(signal: np.ndarray) -> np.ndarray:
    """F0 (Hz) per 40 ms frame, NaN when unvoiced. Autocorrelation via FFT, batched."""
    frames = frames_of(signal).astype(np.float64)
    frames = frames - frames.mean(axis=1, keepdims=True)
    window = np.hanning(FRAME)
    spectrum = np.fft.rfft(frames * window, n=FFT, axis=1)
    acf = np.fft.irfft(np.abs(spectrum) ** 2, n=FFT, axis=1)[:, : FRAME]
    lag_lo, lag_hi = int(RATE / F0_MAX), int(RATE / F0_MIN)
    energy = acf[:, 0]
    region = acf[:, lag_lo:lag_hi]
    best = region.argmax(axis=1)
    peak = region[np.arange(len(region)), best] / np.maximum(energy, 1e-12)
    f0 = RATE / (best + lag_lo)
    loud = frame_db(signal) > (np.percentile(frame_db(signal), 90) - 30)
    voiced = (peak > 0.45) & loud
    return np.where(voiced, f0, np.nan)


def semitone_spread(f0: np.ndarray) -> float:
    voiced = f0[~np.isnan(f0)]
    if voiced.size < 10:
        return 0.0
    semis = 12 * np.log2(voiced / np.median(voiced))
    # robust spread (p90−p10)/2.56 ≈ σ for a normal curve; octave errors of the tracker barely move it
    return round(float((np.percentile(semis, 90) - np.percentile(semis, 10)) / 2.56), 2)


def pauses(db: np.ndarray) -> list[tuple[float, float]]:
    """Runs ≥ PAUSE_MIN well below the speech level (frame times in seconds)."""
    speech_level = np.percentile(db, 75)
    quiet = db < speech_level - 25
    hop = FRAME / RATE
    runs, start = [], None
    for i, value in enumerate(np.append(quiet, False)):
        if value and start is None:
            start = i
        elif not value and start is not None:
            if (i - start) * hop >= PAUSE_MIN:
                runs.append((round(start * hop, 2), round(i * hop, 2)))
            start = None
    return runs


def energy_mean_lufs(values: np.ndarray) -> float:
    """Power-mean of LUFS readings (how ebur128 itself averages)."""
    if values.size == 0:
        return -120.0
    power = np.mean(10 ** (np.maximum(values, -120.0) / 10))
    return round(float(10 * np.log10(max(power, 1e-12))), 1)
