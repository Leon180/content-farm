"""One retention report per run (``qc/retention.json``): content beats, picture, sound, dead zones.

A *dead zone* is any stretch longer than ``DEAD_ZONE`` seconds with no visual event, no audio
event (stinger / SFX — speech itself does not count, it never stops) and no narration hook
(research §5.5, 🟡). Long videos must ship with zero.
"""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.retention.audio_report import audio_windows
from content_farm.retention.beats import lint, slide_beats
from content_farm.retention.screen_text import DENSE_CHARS, density, slide_texts, sync_findings
from content_farm.retention.timing import load_scenes, sentence_timeline, speech_rate
from content_farm.retention.video_probe import STILL_MAX, probe_video

DEAD_ZONE = 10.0
REPORT = Path("qc") / "retention.json"


def upload_video(run_dir: Path) -> Path | None:
    """What gets uploaded: the mixed release, else the host final, else the draft."""
    for name in ("release.mp4", "final.mp4", "draft.mp4"):
        path = run_dir / "assembly" / name
        if path.is_file():
            return path
    return None


def dead_zones(duration: float, *event_lists: list[float], limit: float = DEAD_ZONE) -> list[dict]:
    points = sorted({0.0, float(duration), *(float(t) for events in event_lists for t in events)})
    return [{"start": round(a, 1), "end": round(b, 1), "seconds": round(b - a, 1)}
            for a, b in zip(points, points[1:]) if b - a > limit]


LEGACY_SUBTITLE = {"font_px": 52, "frame_h": 1080, "box": False}   # assembly before 2026-10-17 v3


def subtitle_style(run_dir: Path, vertical: bool) -> dict:
    """What assembly burned in (``assembly/subtitle_style.json``); older runs did not record it, so
    they are reported with the pre-v3 landscape style and ``recorded: false``."""
    path = run_dir / "assembly" / "subtitle_style.json"
    if path.is_file():
        style, recorded = json.loads(path.read_text(encoding="utf-8")), True
    elif vertical:
        from content_farm.assembly.timeline_assembly import PORTRAIT_PRESET as p

        style, recorded = {"font_px": p.subtitle_font_size, "frame_h": p.height, "box": p.subtitle_box}, False
    else:
        style, recorded = dict(LEGACY_SUBTITLE), False
    return {**style, "height_pct": round(100 * style["font_px"] / style["frame_h"], 1), "recorded": recorded}


def speech_errors(run_dir: Path) -> dict:
    path = run_dir / "audio" / "speech_check.json"
    if not path.is_file():
        return {"available": False}
    checks = json.loads(path.read_text(encoding="utf-8"))
    current = {p.name for p in (run_dir / "audio").glob("scene_*.mp3")}
    checks = {k: v for k, v in checks.items() if k in current}
    if not checks:
        return {"available": False}
    worst = max(checks.items(), key=lambda kv: kv[1].get("cer", 0))
    pinyin = [c.get("pinyin_cer") for c in checks.values() if c.get("pinyin_cer") is not None]
    return {"available": True, "scenes": len(checks), "mean_cer": round(sum(c["cer"] for c in checks.values()) / len(checks), 3),
            "worst_scene": worst[0], "worst_cer": worst[1]["cer"],
            "mean_pinyin_cer": round(sum(pinyin) / len(pinyin), 3) if pinyin else None,
            "flagged": [f"{k}: {'、'.join(v.get('missing_terms') or []) or v.get('status')}" for k, v in checks.items()
                        if v.get("status") != "ok"],
            "tone_only": [f"{k}: {'、'.join(v['tone_errors'])}" for k, v in checks.items() if v.get("tone_errors")]}


def build_report(run_dir: Path, *, vertical: bool = False, with_audio: bool = True) -> dict:
    video = upload_video(run_dir)
    if video is None:
        raise FileNotFoundError(f"{run_dir}/assembly has no video")
    scenes = load_scenes(run_dir)
    sentences = sentence_timeline(run_dir, scenes)
    beats = lint(scenes, sentences, slide_beats(run_dir))
    picture = probe_video(video, vertical=vertical)
    texts = slide_texts(run_dir)
    sound = audio_windows(run_dir, video, sentences) if with_audio else {"windows": []}
    cue_times = [c["t"] for c in _cues(run_dir)]
    zones = dead_zones(picture.duration, picture.events, cue_times, [h.t for h in beats.hooks])
    dens = density(texts)
    return {
        "video": video.relative_to(run_dir).as_posix(),
        "duration": picture.duration,
        "content": {**beats.as_dict(), "speech_rate": speech_rate(run_dir, scenes)},
        "visual": {**picture.as_dict(), "subtitle": subtitle_style(run_dir, vertical),
                   "sync": sync_findings(scenes, sentences, texts),
                   "density": {"max": max(dens.values(), default=0), "dense_pages": [k for k, v in dens.items() if v > DENSE_CHARS],
                               "per_slide": dens},
                   "still_max": STILL_MAX},
        "audio": {**sound, "speech_check": speech_errors(run_dir)},
        "dead_zones": zones,
        "slides": [{"id": s.slide_id, "start": s.start, "end": s.end, "chapter": s.chapter} for s in scenes],
    }


def _cues(run_dir: Path) -> list[dict]:
    path = run_dir / "audio" / "mix" / "mix_report.json"
    return json.loads(path.read_text(encoding="utf-8")).get("cues", []) if path.is_file() else []


def write_report(run_dir: Path, data: dict, out: Path | None = None) -> Path:
    path = out or run_dir / REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
