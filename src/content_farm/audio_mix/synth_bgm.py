"""Background music synthesized from scratch (numpy): no model download, no third-party audio.

Presets (``audio.synth_bgm`` in a channel yaml):
- ``wafu``: a slow, dark Japanese-scale (miyako-bushi on D) bed — low drone, soft pad, sparse
  koto-like plucks, a little wind, all through a long reverb. Deterministic and seamless: every
  sustained part is periodic in the loop length and the reverb is circular, so ``-stream_loop``
  in the mix has no seam.
- ``studio`` (cel): a warm, light C-major-pentatonic bed — soft pad, marimba-like plucks, a slow bass root.
- ``pulse`` (technews / chipcat without recorded tracks): a clean A-minor-pentatonic bed — airy pad and a very
  quiet, regular sine blip grid (75 bpm), nothing that competes with a voice reading figures.
- ``abyss`` (deepsea): a very low D drone, slow D-minor pad and rare distant sonar-like pings in a long reverb.
- ``hearth`` (fable): storytelling by a warm fire — F-major pentatonic music-box notes over a slow pad and a low drone.
Visual v4 (Leon 2026-10-24): each long channel has one local synthesized style, switched on or off with
``audio.enabled`` in its yaml; real ``audio.bgm`` files, when listed, win over the preset.
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


def _soft_pad(n: int, rng: np.random.Generator, scale: tuple[float, ...], step: float = 8.0) -> np.ndarray:
    """Slow overlapping two-note swells on the given scale (same shape as the wafu pad)."""
    out = np.zeros(n)
    length = int(1.15 * step * RATE)
    t = _time(length)
    envelope = np.sin(np.pi * np.clip(t / (1.15 * step), 0, 1)) ** 2
    for start in np.arange(0.0, LOOP_SECONDS, step):
        for hz in rng.choice(scale, size=2, replace=False):
            tone = np.sin(2 * np.pi * hz * t) + np.sin(2 * np.pi * hz * 1.003 * t + 0.9)
            _wrapped_add(out, int(start * RATE), tone * envelope * 0.35)
    return out


def _marimba(freq: float, seconds: float = 1.6) -> np.ndarray:
    n = int(seconds * RATE)
    t = _time(n)
    body = np.sin(2 * np.pi * freq * t) * np.exp(-t * 4.0) + 0.35 * np.sin(2 * np.pi * freq * 4.0 * t) * np.exp(-t * 14.0)
    return body * np.clip(t / 0.003, 0, 1)


def _sparse(n: int, rng: np.random.Generator, scale: tuple[float, ...], note, gap: tuple[float, float]) -> np.ndarray:
    out = np.zeros(n)
    t, degree = 1.5, len(scale) // 2
    while t < LOOP_SECONDS - 1:
        degree = int(np.clip(degree + rng.integers(-2, 3), 0, len(scale) - 1))
        _wrapped_add(out, int(t * RATE), note(scale[degree]) * rng.uniform(0.5, 1.0))
        t += rng.uniform(*gap)
    return out


_C_PENTA = tuple(261.63 * 2 ** (semi / 12) for semi in (0, 2, 4, 7, 9, 12, 14, 16))
_A_PENTA = tuple(220.0 * 2 ** (semi / 12) for semi in (0, 3, 5, 7, 10, 12, 15, 17))


def studio(seconds: float = LOOP_SECONDS, seed: int = SEED) -> np.ndarray:
    """Warm and light: C-major pentatonic marimba over a soft pad and a slow C/G bass."""
    n = int(round(seconds * RATE))
    rng = np.random.default_rng(seed + 1)
    t = _time(n)
    bass = sum(np.sin(2 * np.pi * _periodic(hz) * t) * (0.7 + 0.3 * np.sin(2 * np.pi * (4 + k) / LOOP_SECONDS * t))
               for k, hz in enumerate((65.41, 98.0)))
    pad = _soft_pad(n, rng, _C_PENTA[:6])
    plucks = _sparse(n, rng, _C_PENTA, _marimba, (1.2, 2.8))
    wet = _reverb(_normalised(pad) * 0.5 + _normalised(plucks), rng, seconds=1.8)
    return _normalised(0.35 * _normalised(bass) + 0.4 * _normalised(pad) + 0.55 * _normalised(plucks) + 0.45 * wet)


def pulse(seconds: float = LOOP_SECONDS, seed: int = SEED) -> np.ndarray:
    """Clean and unobtrusive: A-minor-pentatonic pad plus a quiet sine blip on a 75 bpm grid."""
    n = int(round(seconds * RATE))
    rng = np.random.default_rng(seed + 2)
    pad = _soft_pad(n, rng, _A_PENTA[:6], step=12.0)
    blips = np.zeros(n)
    beat = 60.0 / 75.0                           # 96 s = exactly 120 beats, so the grid wraps cleanly
    for k in range(int(LOOP_SECONDS / beat)):
        if rng.random() < 0.35:
            hz = _A_PENTA[int(rng.integers(0, len(_A_PENTA)))] * 2
            m = int(0.35 * RATE)
            tt = _time(m)
            _wrapped_add(blips, int(k * beat * RATE), np.sin(2 * np.pi * hz * tt) * np.exp(-tt * 9.0) * rng.uniform(0.4, 0.9))
    wet = _reverb(_normalised(blips), rng, seconds=1.2)
    return _normalised(0.7 * _normalised(pad) + 0.3 * _normalised(blips) + 0.3 * wet)


_D_MINOR = tuple(293.66 * 2 ** (semi / 12) for semi in (0, 3, 5, 7, 10, 12, 15))


def _ping(freq: float, seconds: float = 5.0) -> np.ndarray:
    """A soft sonar-like bell: pure tone, slow decay, a faint inharmonic partial."""
    n = int(seconds * RATE)
    t = _time(n)
    body = np.sin(2 * np.pi * freq * t) * np.exp(-t * 1.1) + 0.2 * np.sin(2 * np.pi * freq * 2.76 * t) * np.exp(-t * 3.0)
    return body * np.clip(t / 0.02, 0, 1)


def abyss(seconds: float = LOOP_SECONDS, seed: int = SEED) -> np.ndarray:
    """Deep sea: a very low D drone, a slow D-minor pad and rare, distant sonar pings in a long reverb."""
    n = int(round(seconds * RATE))
    rng = np.random.default_rng(seed + 3)
    t = _time(n)
    drone = sum(np.sin(2 * np.pi * _periodic(hz) * t) * (0.7 + 0.3 * np.sin(2 * np.pi * (3 + k) / LOOP_SECONDS * t + k))
                for k, hz in enumerate((36.71, 55.0)))
    pad = _soft_pad(n, rng, _D_MINOR[:5], step=14.0)
    pings = _sparse(n, rng, _D_MINOR, _ping, (7.0, 13.0))
    wet = _reverb(_normalised(pad) * 0.4 + _normalised(pings), rng, seconds=4.0)
    return _normalised(0.5 * _normalised(drone) + 0.4 * _normalised(pad) + 0.4 * _normalised(pings) + 0.7 * wet)


_F_PENTA = tuple(174.61 * 2 ** (semi / 12) for semi in (0, 2, 4, 7, 9, 12, 14, 16, 19, 21))


def _music_box(freq: float, seconds: float = 3.2) -> np.ndarray:
    """A tiny music-box tine: a clean fundamental, a bright short partial, a long soft decay."""
    n = int(seconds * RATE)
    t = _time(n)
    body = np.sin(2 * np.pi * freq * t) * np.exp(-t * 1.5) + 0.3 * np.sin(2 * np.pi * freq * 3.0 * t) * np.exp(-t * 6.0)
    return body * np.clip(t / 0.002, 0, 1)


def hearth(seconds: float = LOOP_SECONDS, seed: int = SEED) -> np.ndarray:
    """Storytelling by a warm fire (fable channel): F-major pentatonic music-box notes over a slow pad and a low F/C drone."""
    n = int(round(seconds * RATE))
    rng = np.random.default_rng(seed + 4)
    t = _time(n)
    drone = sum(np.sin(2 * np.pi * _periodic(hz) * t) * (0.7 + 0.3 * np.sin(2 * np.pi * (3 + k) / LOOP_SECONDS * t + k))
                for k, hz in enumerate((87.31, 130.81)))
    pad = _soft_pad(n, rng, _F_PENTA[:6], step=10.0)
    notes = _sparse(n, rng, _F_PENTA[3:], _music_box, (1.6, 3.6))
    wet = _reverb(_normalised(pad) * 0.4 + _normalised(notes), rng, seconds=2.6)
    return _normalised(0.3 * _normalised(drone) + 0.4 * _normalised(pad) + 0.5 * _normalised(notes) + 0.5 * wet)


PRESETS = {"wafu": wafu, "studio": studio, "pulse": pulse, "abyss": abyss, "hearth": hearth}
_SOURCE = {"wafu": "本機以 numpy 程式合成（audio_mix/synth_bgm.py 的 wafu 預設，和風音階 D 都節旋法）",
           "studio": "本機以 numpy 程式合成（audio_mix/synth_bgm.py 的 studio 預設，C 大調五聲音階、木琴與柔和和聲）",
           "pulse": "本機以 numpy 程式合成（audio_mix/synth_bgm.py 的 pulse 預設，A 小調五聲音階、低調節拍點）",
           "abyss": "本機以 numpy 程式合成（audio_mix/synth_bgm.py 的 abyss 預設，D 小調超低頻持續音、緩慢和聲與稀疏聲納鈴音）",
           "hearth": "本機以 numpy 程式合成（audio_mix/synth_bgm.py 的 hearth 預設，F 大調五聲音階、八音盒音色、柔和和聲與低音持續音）"}


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
