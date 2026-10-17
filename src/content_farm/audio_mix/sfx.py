"""Small sound effects synthesized from scratch (numpy): no third-party audio, nothing to licence.

Deterministic (fixed seeds), 48 kHz mono 16-bit WAV. Kinds:
- ``whoosh``: band-swept noise, 0.45 s — slide turns / teases;
- ``pop``: short pitched blip, 0.12 s — joke punchlines;
- ``ding``: two-partial bell, 0.9 s — a number reversal lands;
- ``stinger``: rising three-note arpeggio + whoosh tail, 1.8 s — chapter change (fallback when
  the channel has no music stinger).
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

RATE = 48000
KINDS = ("whoosh", "pop", "ding", "stinger")


def _env(n: int, attack: float, release: float) -> np.ndarray:
    t = np.arange(n) / RATE
    rise = np.clip(t / max(attack, 1e-4), 0, 1)
    fall = np.exp(-np.maximum(t - attack, 0) / max(release, 1e-4))
    return rise * fall


def whoosh(seconds: float = 0.45, seed: int = 7) -> np.ndarray:
    n = int(seconds * RATE)
    noise = np.random.default_rng(seed).standard_normal(n)
    spectrum = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n, 1 / RATE)
    centre = 2500.0
    spectrum *= np.exp(-((np.log2(np.maximum(freqs, 20) / centre)) ** 2) / 1.2)
    shaped = np.fft.irfft(spectrum, n)
    t = np.linspace(0, 1, n)
    swell = np.sin(np.pi * t) ** 2
    return shaped * swell


def pop(seconds: float = 0.12) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    freq = 900 * np.exp(-t * 18) + 380
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    return np.sin(phase) * _env(n, 0.004, 0.03)


def ding(seconds: float = 0.9) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    tone = np.sin(2 * np.pi * 1318.5 * t) + 0.45 * np.sin(2 * np.pi * 2637 * t) + 0.2 * np.sin(2 * np.pi * 3951 * t)
    return tone * _env(n, 0.003, 0.25)


def stinger(seconds: float = 1.8) -> np.ndarray:
    n = int(seconds * RATE)
    out = np.zeros(n)
    for k, (freq, start) in enumerate(((523.25, 0.0), (659.25, 0.16), (783.99, 0.32), (1046.5, 0.48))):
        a = int(start * RATE)
        m = n - a
        t = np.arange(m) / RATE
        note = (np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * 2 * freq * t)) * _env(m, 0.005, 0.35 + 0.1 * k)
        out[a:] += note * (0.8 if k < 3 else 1.0)
    tail = whoosh(0.9, seed=11)
    out[int(0.55 * RATE):int(0.55 * RATE) + len(tail)] += 0.6 * tail[: n - int(0.55 * RATE)]
    return out


GENERATORS = {"whoosh": whoosh, "pop": pop, "ding": ding, "stinger": stinger}


def write_wav(samples: np.ndarray, path: Path, peak_db: float = -6.0) -> Path:
    """Normalise to ``peak_db`` and write 16-bit mono."""
    peak = float(np.max(np.abs(samples))) or 1.0
    scaled = samples / peak * (10 ** (peak_db / 20))
    pcm = np.clip(np.round(scaled * 32767), -32768, 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(pcm.tobytes())
    return path


def ensure_sfx(directory: Path) -> dict[str, Path]:
    """Write every kind once into ``directory`` (idempotent); returns kind → path."""
    paths = {}
    for kind, make in GENERATORS.items():
        path = directory / f"{kind}.wav"
        if not path.is_file():
            write_wav(make(), path)
        paths[kind] = path
    return paths
