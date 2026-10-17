"""Per-10-second audio metrics and a one-line description a viewer-persona can read.

Reads the uploaded video's audio (release.mp4 → final.mp4 → draft.mp4) and, when the mix step
ran, its stems (``audio/mix/voice.wav`` / ``bgm.wav`` / ``fx.wav``) and cue list.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from content_farm.retention import audio_probe as ap
from content_farm.retention.timing import Sentence, normalise

WINDOW = 10.0
RATE_FAST, RATE_SLOW = 5.8, 3.8          # 字/秒 while speaking, pauses excluded (🟡 comfort band)
MONOTONE_ST, LIVELY_ST = 1.5, 5.0        # F0 spread in semitones; normal expressive speech ≈ 2–4 (🟡)
SPEECH_GATE = -40.0                      # momentary LUFS above which the voice stem "speaks"


def _window_values(values: np.ndarray, per_second: float, start: float, end: float) -> np.ndarray:
    return values[int(start * per_second): int(end * per_second)]


def _rate_in(sentences: list[Sentence], start: float, end: float) -> float | None:
    chars, seconds = 0, 0.0
    for s in sentences:
        overlap = min(s.end, end) - max(s.start, start)
        if overlap > 0 and s.end > s.start:
            chars += len(normalise(s.text)) * overlap / (s.end - s.start)
            seconds += overlap
    return round(chars / seconds, 1) if seconds >= 2 else None


def describe(row: dict) -> str:
    parts = []
    rate = row.get("rate")
    if rate is None:
        parts.append("沒有旁白")
    else:
        pace = "偏快" if rate > RATE_FAST else "偏慢" if rate < RATE_SLOW else "適中"
        parts.append(f"語速 {rate} 字/秒{pace}")
    spread = row.get("pitch_spread_st")
    if spread is not None and rate is not None:
        parts.append("語調平" if spread < MONOTONE_ST else "語調起伏大" if spread > LIVELY_ST else "語調有起伏")
    under = row.get("bgm_under_voice_db")
    if under is None:
        parts.append("無 BGM")
    else:
        parts.append("BGM 偏大聲" if under < 10 else "BGM 很小聲" if under > 22 else "BGM 低")
    cues = row.get("cues") or []
    parts.append("音效：" + "、".join(cues) if cues else "無音效")
    if row.get("silence_share", 0) > 0.4:
        parts.append("停頓多")
    return "、".join(parts)


def _stem(run_dir: Path, name: str) -> Path | None:
    path = run_dir / "audio" / "mix" / f"{name}.wav"
    return path if path.is_file() else None


def _cue_names(run_dir: Path) -> list[dict]:
    path = run_dir / "audio" / "mix" / "mix_report.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("cues", [])


CUE_LABEL = {"stinger": "章節轉場音", "whoosh": "咻聲", "pop": "啵聲", "ding": "叮聲"}


def audio_windows(run_dir: Path, video: Path, sentences: list[Sentence]) -> dict:
    full = ap.loudness(video)
    voice_path, bgm_path = _stem(run_dir, "voice"), _stem(run_dir, "bgm")
    voice_m = ap.loudness(voice_path).momentary if voice_path else None
    bgm_m = ap.loudness(bgm_path).momentary if bgm_path else None
    if bgm_m is not None and ap.energy_mean_lufs(bgm_m) < -60:   # stem exists but the channel has no bed
        bgm_m = None
    speech = ap.decode(voice_path or video)
    db = ap.frame_db(speech)
    f0 = ap.pitch_track(speech)
    pauses = ap.pauses(db)
    cues = _cue_names(run_dir)
    duration = len(full.momentary) / 10.0
    rows = []
    for k in range(int(np.ceil(duration / WINDOW))):
        start, end = k * WINDOW, min((k + 1) * WINDOW, duration)
        row = {"t0": start, "t1": round(end, 1),
               "lufs": ap.energy_mean_lufs(_window_values(full.momentary, 10, start, end)),
               "rate": _rate_in(sentences, start, end),
               "pitch_spread_st": ap.semitone_spread(_window_values(f0, 25, start, end)),
               "energy_spread_db": round(float(np.std(_window_values(db, 25, start, end))), 1),
               "silence_share": round(sum(max(0.0, min(b, end) - max(a, start)) for a, b in pauses) / (end - start), 2),
               "cues": [CUE_LABEL.get(c["kind"], c["kind"]) for c in cues if start <= c["t"] < end]}
        if voice_m is not None and bgm_m is not None:
            v = _window_values(voice_m, 10, start, end)
            b = _window_values(bgm_m, 10, start, end)
            speaking = v > SPEECH_GATE
            if speaking.any():
                row["bgm_under_voice_db"] = round(ap.energy_mean_lufs(v[speaking]) - ap.energy_mean_lufs(b[speaking]), 1)
        row["describe"] = describe(row)
        rows.append(row)
    return {"windows": rows, "integrated": full.integrated, "lra": full.lra, "true_peak": full.true_peak,
            "pauses": _pause_stats(pauses), "pitch_spread_st": ap.semitone_spread(f0),
            "ducking_db": _ducking(voice_m, bgm_m), "clipped_samples": ap.clipped_samples(video),
            "dead_air": [p for p in pauses if p[1] - p[0] >= 2.0]}


def _pause_stats(pauses: list[tuple[float, float]]) -> dict:
    lengths = np.array([b - a for a, b in pauses]) if pauses else np.array([0.0])
    return {"count": len(pauses), "median_s": round(float(np.median(lengths)), 2),
            "p90_s": round(float(np.percentile(lengths, 90)), 2), "max_s": round(float(lengths.max()), 2)}


def _ducking(voice_m: np.ndarray | None, bgm_m: np.ndarray | None) -> float | None:
    """BGM level in speech-free moments minus BGM level under speech (dB); None without stems."""
    if voice_m is None or bgm_m is None:
        return None
    n = min(len(voice_m), len(bgm_m))
    v, b = voice_m[:n], bgm_m[:n]
    speaking, quiet = v > SPEECH_GATE, v < SPEECH_GATE - 15
    if not speaking.any() or not quiet.any() or ap.energy_mean_lufs(b) < -70:
        return None
    return round(ap.energy_mean_lufs(b[quiet]) - ap.energy_mean_lufs(b[speaking]), 1)
