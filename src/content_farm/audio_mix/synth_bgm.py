"""Background music synthesized from scratch (numpy): no model download, no third-party audio.

Presets (``audio.synth_bgm`` in a channel yaml):
- ``wafu``: a slow, dark Japanese-scale (miyako-bushi on D) bed — low drone, soft pad, sparse
  koto-like plucks, a little wind, all through a long reverb. Deterministic and seamless: every
  sustained part is periodic in the loop length and the reverb is circular, so ``-stream_loop``
  in the mix has no seam.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from content_farm.audio_mix.sfx import RATE, write_wav
from content_farm.production.channels import AudioMix, AudioTrack

LOOP_SECONDS = 96.0
SEED = 20261023
# miyako-bushi on D: D Eb G A Bb, two octaves (Hz)
_SCALE_HZ = tuple(146.83 * 2 ** (semi / 12) for semi in (0, 1, 5, 7, 8, 12, 13, 17, 19, 20, 24))
_DRONE_HZ = (73.42, 110.0)


def _periodic(freq: float) -> float:
    """Nearest frequency that completes a whole number of cycles in the loop (seamless phase)."""
    return round(freq * LOOP_SECONDS) / LOOP_SECONDS


def _time(n: int) -> np.ndarray:
    return np.arange(n) / RATE


def _drone(n: int) -> np.ndarray:
    t = _time(n)
    out = np.zeros(n)
    for k, hz in enumerate(_DRONE_HZ):
        f = _periodic(hz)
        tone = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t + 0.7)
        swell = 0.65 + 0.35 * np.sin(2 * np.pi * (6 + 2 * k) / LOOP_SECONDS * t + k)
        out += tone * swell
    return out


def _wrapped_add(buffer: np.ndarray, start: int, signal: np.ndarray) -> None:
    """Add ``signal`` at ``start``, wrapping past the end back to the beginning."""
    n = len(buffer)
    start %= n
    first = min(len(signal), n - start)
    buffer[start:start + first] += signal[:first]
    rest = len(signal) - first
    while rest > 0:
        chunk = min(rest, n)
        buffer[:chunk] += signal[len(signal) - rest:len(signal) - rest + chunk]
        rest -= chunk


def _pluck(freq: float, seconds: float = 4.0) -> np.ndarray:
    """Koto-like: a bright attack, slightly stretched partials, higher partials fade faster."""
    n = int(seconds * RATE)
    t = _time(n)
    out = np.zeros(n)
    for k, weight in enumerate((1.0, 0.55, 0.3, 0.18, 0.1), start=1):
        partial = freq * k * (1 + 0.0007 * k * k)
        out += weight * np.sin(2 * np.pi * partial * t) * np.exp(-t * (1.1 + 1.6 * (k - 1)))
    attack = np.clip(t / 0.004, 0, 1)
    return out * attack


def _plucks(n: int, rng: np.random.Generator) -> np.ndarray:
    out = np.zeros(n)
    t, degree = 2.0, 4
    while t < LOOP_SECONDS - 1:
        degree = int(np.clip(degree + rng.integers(-2, 3), 0, len(_SCALE_HZ) - 1))
        _wrapped_add(out, int(t * RATE), _pluck(_SCALE_HZ[degree] * 2) * rng.uniform(0.5, 1.0))
        t += rng.uniform(3.5, 8.0)
    return out


def _pad(n: int, rng: np.random.Generator) -> np.ndarray:
    out = np.zeros(n)
    length = int(9 * RATE)
    t = _time(length)
    envelope = np.sin(np.pi * np.clip(t / 9, 0, 1)) ** 2
    for start in np.arange(0.0, LOOP_SECONDS, 8.0):
        for hz in rng.choice(_SCALE_HZ[:7], size=2, replace=False):
            f = hz * rng.choice((1.0, 2.0))
            tone = np.sin(2 * np.pi * f * t) + np.sin(2 * np.pi * f * 1.004 * t + 1.3)
            _wrapped_add(out, int(start * RATE), tone * envelope * 0.35)
    return out


def _wind(n: int, rng: np.random.Generator) -> np.ndarray:
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / RATE)
    spectrum *= np.exp(-((np.log2(np.maximum(freqs, 20) / 700.0)) ** 2) / 0.8)
    noise = np.fft.irfft(spectrum, n)
    swell = 0.5 + 0.5 * np.sin(2 * np.pi * 5 / LOOP_SECONDS * _time(n) + 2.0)
    return noise / (np.max(np.abs(noise)) or 1.0) * swell


def _reverb(dry: np.ndarray, rng: np.random.Generator, seconds: float = 3.0) -> np.ndarray:
    """Circular convolution with a decaying-noise impulse: the tail wraps, so the loop stays seamless."""
    n = len(dry)
    m = int(seconds * RATE)
    impulse = np.zeros(n)
    impulse[:m] = rng.standard_normal(m) * np.exp(-np.arange(m) / RATE * 2.4)
    wet = np.fft.irfft(np.fft.rfft(dry) * np.fft.rfft(impulse), n)
    return wet / (np.max(np.abs(wet)) or 1.0) * (np.max(np.abs(dry)) or 1.0)


def _normalised(x: np.ndarray) -> np.ndarray:
    return x / (np.max(np.abs(x)) or 1.0)


def wafu(seconds: float = LOOP_SECONDS, seed: int = SEED) -> np.ndarray:
    """One seamless loop of the Japanese-scale bed (``seconds`` must stay the loop length)."""
    n = int(round(seconds * RATE))
    rng = np.random.default_rng(seed)
    drone = _normalised(_drone(n))
    body = _normalised(_pad(n, rng)) * 0.5 + _normalised(_plucks(n, rng)) * 0.9
    wet = _reverb(body, rng)
    air = _wind(n, rng)
    return _normalised(0.55 * drone + 0.45 * body + 0.55 * wet + 0.12 * air)


PRESETS = {"wafu": wafu}
_SOURCE = {"wafu": "本機以 numpy 程式合成（audio_mix/synth_bgm.py 的 wafu 預設，和風音階 D 都節旋法）"}


def with_synth_bgm(config: AudioMix, directory: Path) -> AudioMix:
    """The channel's AudioMix with its synthesized bed written to ``directory`` and listed as the BGM
    track (credits then name it as self-made). No-op when no preset is set or real BGM is configured."""
    if config.synth_bgm is None or config.bgm:
        return config
    path = directory / f"{config.synth_bgm}.wav"
    if not path.is_file():
        write_wav(PRESETS[config.synth_bgm](), path, peak_db=-6.0)
    track = AudioTrack(path=str(path), title=f"合成配樂（{config.synth_bgm}）", source=_SOURCE[config.synth_bgm],
                       license="自製，無第三方素材、無外部模型")
    return config.model_copy(update={"bgm": (track,)})
