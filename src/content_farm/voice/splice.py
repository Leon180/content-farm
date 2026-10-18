"""Sentence-window re-voicing: replace a few sentences inside an existing scene take.

A scene take is one TTS call for the whole slide narration. When an edit touches some
sentences, only a *window* (the changed sentences plus ``radius`` neighbours on each
side, never past the scene) is synthesized again and spliced into the old take at the
pauses between sentences, keeping the original pause lengths on both sides.

Also the measurements used to pick the default radius (seam pitch / loudness / rate
jumps), see scripts/voice_window_experiment.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 44_100            # takes are 44.1 kHz mono MP3 (voice.local_clone)
HOP_S = 0.01
MIN_PAUSE_S = 0.06
SILENCE_DB_BELOW = 35.0  # a frame is "pause" when this far below the take's loud level
FADE_S = 0.012


class SpliceError(ValueError):
    """The take cannot be cut at the sentence boundaries (pauses not found)."""


def decode(path: Path, sr: int = SR) -> np.ndarray:
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                            capture_output=True, check=True, timeout=300)
    return np.frombuffer(result.stdout, dtype=np.float32).copy()


def encode(samples: np.ndarray, out: Path, sr: int = SR) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-",
                    "-codec:a", "libmp3lame", "-b:a", "192k", str(out)],
                   input=samples.astype(np.float32).tobytes(), check=True, timeout=300)
    return out


def frame_db(samples: np.ndarray, sr: int = SR, hop_s: float = HOP_S) -> np.ndarray:
    hop = int(sr * hop_s)
    n = len(samples) // hop
    if n == 0:
        return np.zeros(0)
    frames = samples[: n * hop].reshape(n, hop).astype(np.float64)
    return 20 * np.log10(np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-9)


@dataclass(frozen=True)
class Pause:
    start: float
    end: float

    @property
    def mid(self) -> float:
        return (self.start + self.end) / 2


def pauses(samples: np.ndarray, sr: int = SR) -> list[Pause]:
    db = frame_db(samples, sr)
    if db.size == 0:
        return []
    loud = float(np.percentile(db, 95))
    quiet = db < loud - SILENCE_DB_BELOW
    out, start = [], None
    for i, q in enumerate(np.append(quiet, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * HOP_S >= MIN_PAUSE_S:
                out.append(Pause(start * HOP_S, i * HOP_S))
            start = None
    return out


def voiced_span(samples: np.ndarray, sr: int = SR) -> tuple[float, float]:
    """First and last voiced instant (seconds)."""
    db = frame_db(samples, sr)
    if db.size == 0:
        return 0.0, 0.0
    voiced = np.nonzero(db >= float(np.percentile(db, 95)) - SILENCE_DB_BELOW)[0]
    if voiced.size == 0:
        return 0.0, len(samples) / sr
    return voiced[0] * HOP_S, (voiced[-1] + 1) * HOP_S


def sentence_cuts(samples: np.ndarray, weights: Sequence[int], sr: int = SR) -> list[float]:
    """Boundaries [0, b1, ..., end] between ``len(weights)`` sentences (weights = spoken chars).

    Each inner boundary is the middle of the pause nearest the character-proportional guess,
    pauses used in order and each once; the longest pauses win ties. Raises SpliceError when
    there are fewer pauses than boundaries."""
    total = len(samples) / sr
    if len(weights) <= 1:
        return [0.0, total]
    lo, hi = voiced_span(samples, sr)
    inner = [p for p in pauses(samples, sr) if lo < p.mid < hi]
    if len(inner) < len(weights) - 1:
        raise SpliceError(f"{len(inner)} pauses for {len(weights) - 1} sentence boundaries")
    cuts = [0.0]
    used = -1
    acc = 0
    whole = max(sum(weights), 1)
    for k, weight in enumerate(weights[:-1]):
        acc += weight
        guess = lo + (hi - lo) * acc / whole
        remaining = len(weights) - 2 - k   # boundaries still to place after this one
        choices = range(used + 1, len(inner) - remaining)
        best = min(choices, key=lambda j: abs(inner[j].mid - guess) - 0.15 * (inner[j].end - inner[j].start))
        cuts.append(inner[best].mid)
        used = best
    cuts.append(total)
    return cuts


def _fade(x: np.ndarray, sr: int, head: bool, tail: bool) -> np.ndarray:
    n = min(int(FADE_S * sr), len(x) // 2)
    out = x.copy()
    if n:
        ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
        if head:
            out[:n] *= ramp
        if tail:
            out[-n:] *= ramp[::-1]
    return out


def splice(old: np.ndarray, cuts: Sequence[float], first: int, last: int, new: np.ndarray,
           sr: int = SR) -> np.ndarray:
    """``old`` with sentences ``first..last`` (inclusive, indices into ``cuts``) replaced by the
    voiced part of ``new``; the pauses around the window keep their old length."""
    a, b = int(cuts[first] * sr), int(cuts[last + 1] * sr)
    seg = old[a:b]
    o_lo, o_hi = voiced_span(seg, sr)
    n_lo, n_hi = voiced_span(new, sr)
    lead = np.zeros(int(o_lo * sr), dtype=np.float32) if first > 0 else seg[: int(o_lo * sr)] * 0
    tail_len = len(seg) - int(o_hi * sr)
    trail = np.zeros(max(tail_len, 0), dtype=np.float32)
    body = _fade(new[int(n_lo * sr): int(n_hi * sr)], sr, head=True, tail=True)
    return np.concatenate([_fade(old[:a], sr, head=False, tail=a > 0), lead, body, trail,
                           _fade(old[b:], sr, head=b < len(old), tail=False)]).astype(np.float32)


# --- seam measurements -----------------------------------------------------------------------

def f0_track(samples: np.ndarray, sr: int = 16_000, hop_s: float = HOP_S, fmin: float = 80.0,
             fmax: float = 450.0) -> np.ndarray:
    """Per-hop F0 (Hz, NaN when unvoiced) by normalised autocorrelation."""
    win, hop = int(0.04 * sr), int(hop_s * sr)
    lo, hi = int(sr / fmax), int(sr / fmin)
    out = []
    for start in range(0, max(len(samples) - win, 0), hop):
        x = samples[start:start + win].astype(np.float64)
        x = x - x.mean()
        energy = np.dot(x, x)
        if energy < 1e-6:
            out.append(np.nan)
            continue
        ac = np.correlate(x, x, mode="full")[win - 1:]
        lag = lo + int(np.argmax(ac[lo:hi]))
        out.append(sr / lag if ac[lag] / energy > 0.45 else np.nan)
    return np.asarray(out)


@dataclass(frozen=True)
class SeamJump:
    at: float
    pitch_semitones: float   # |median F0 after - before| in semitones (voiced 0.5 s each side)
    loudness_db: float       # |RMS dB after - before| over voiced frames 0.5 s each side

    def to_json(self) -> dict:
        return {"at": round(self.at, 3), "pitch_st": round(self.pitch_semitones, 2),
                "loudness_db": round(self.loudness_db, 2)}


def seam_jump(samples: np.ndarray, at: float, sr: int = SR, span: float = 0.5) -> SeamJump:
    """Jump across a boundary at ``at`` seconds: the voiced speech just before vs just after
    (the pause itself excluded)."""
    mono16 = samples[:: max(1, sr // 16_000)] if sr != 16_000 else samples
    sr16 = sr / max(1, sr // 16_000) if sr != 16_000 else 16_000
    db = frame_db(samples, sr)
    loud = float(np.percentile(db, 95)) if db.size else 0.0
    i = int(at / HOP_S)
    voiced = np.nonzero(db >= loud - 25)[0]
    before = voiced[voiced < i][-int(span / HOP_S):]
    after = voiced[voiced >= i][: int(span / HOP_S)]
    f0 = f0_track(mono16, int(sr16))

    def med(idx: np.ndarray) -> float:
        vals = f0[idx[idx < f0.size]] if idx.size else np.array([])
        vals = vals[~np.isnan(vals)]
        return float(np.median(vals)) if vals.size else np.nan

    fb, fa = med(before), med(after)
    pitch = abs(12 * np.log2(fa / fb)) if fb > 0 and fa > 0 else float("nan")
    loudness = abs(float(np.mean(db[after])) - float(np.mean(db[before]))) if before.size and after.size else float("nan")
    return SeamJump(at, pitch, loudness)


def speech_rate(samples: np.ndarray, chars: int, sr: int = SR) -> float:
    """Spoken characters per voiced second (pauses excluded)."""
    db = frame_db(samples, sr)
    voiced = (db >= float(np.percentile(db, 95)) - SILENCE_DB_BELOW).sum() * HOP_S if db.size else 0.0
    return chars / voiced if voiced else 0.0
