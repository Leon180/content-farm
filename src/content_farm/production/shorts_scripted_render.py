"""Render a scripted Short (:mod:`shorts_scripted`) after the voice step.

Inputs in the run-dir: ``short_source.json`` (beats), ``script.json`` with the
measured per-beat durations, ``audio/scene_NNN.mp3`` and ``subtitles/subtitles.srt``
from the voice step. Output: ``assembly/final.mp4`` (1080x1920) plus
``short/beat_report.json`` (how long each visual holds, read by QC).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

from content_farm.explainer import ffmpeg_ops
from content_farm.explainer.brands import brand_css_path
from content_farm.production import shorts_cut as cut
from content_farm.production.channels import Channel
from content_farm.production.shorts_scripted import MAX_STEP_SECONDS, ShortBeat
from content_farm.script_gen.schemas import Script

TEMPLATES = Path(__file__).parent / "templates"
BEAT_REPORT = Path("short") / "beat_report.json"
CARD_MM = (85.6, 54.0)          # ISO ID-1 (悠遊卡 / credit card), the on-screen size reference
WAFER_MM, EDGE_MM = 300.0, 3.0
STAGE_W = 880


@dataclass(frozen=True)
class ScriptedResult:
    video: Path
    seconds: float
    beats: int
    longest_hold: float


def _multiplier(item: str) -> float:
    match = re.search(r"\d+(?:\.\d+)?", item)
    return float(match.group(0)) if match else 1.0


def grow_sizes(items: tuple[str, ...], largest_px: int = 700) -> list[int]:
    """Block side per step, area proportional to the step's number (1× → 9× reticle)."""
    values = [_multiplier(item) for item in items]
    top = max(values)
    return [max(40, round(largest_px * math.sqrt(v / top))) for v in values]


def wafer_slots(side_mm: float, count: int, px_per_mm: float) -> list[tuple[int, int]]:
    """Centres (px, relative to the wafer centre) of ``count`` squares packed in rows on a wafer."""
    radius = WAFER_MM / 2 - EDGE_MM
    best: list[tuple[float, float]] = []
    for step in range(200):
        y, slots = -radius + side_mm * step / 200, []
        while y + side_mm <= radius:
            edge = max(abs(y), abs(y + side_mm))
            n = int(2 * math.sqrt(max(0.0, radius**2 - edge**2)) // side_mm)
            slots += [((i - (n - 1) / 2) * side_mm, y + side_mm / 2) for i in range(n)]
            y += side_mm
        if len(slots) > len(best):
            best = slots
    order = sorted(best, key=lambda p: (abs(p[1]), p[0]))[:count]
    return [(round(x * px_per_mm), round(yy * px_per_mm)) for x, yy in order]


UNIT_AT = 1.2   # number beat: count-up, then the unit, then the question bubble


def number_times(seconds: float) -> tuple[float, float]:
    """(unit appears, bubble appears) for a number beat, spreading changes over the beat."""
    return UNIT_AT, round(max(2.4, seconds * 0.55), 2)


def step_times(seconds: float, steps: int) -> list[float]:
    return [round(seconds * i / steps, 2) for i in range(steps)] + [round(seconds, 2)]


def beat_page(beat: ShortBeat, seconds: float, spec: cut.ShortSpec, channel: Channel, cat_uri: str) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    steps = len(beat.items) if beat.visual == "grow" else beat.count if beat.visual == "wafer" else 1
    wafer_px = 760
    px_per_mm = wafer_px / WAFER_MM
    scale_px_per_cm = 64.0
    side_mm = beat.side_cm * 10 if beat.visual == "wafer" else 0.0
    return env.get_template("short_beat.html.j2").render(
        beat=beat, beat_seconds=round(seconds, 2), channel_name=channel.name, label=spec.label,
        brand_css=brand_css_path(channel.brand).read_text(encoding="utf-8"), cat_uri=cat_uri,
        long_channel=spec.long_channel, long_title=spec.long_title, number_at=number_times(seconds),
        step_at=step_times(seconds * 0.9, max(1, steps)),
        grow_px=grow_sizes(beat.items) if beat.items else [0],
        scale_px=round(beat.side_cm * scale_px_per_cm),
        card_w=round(CARD_MM[0] / 10 * scale_px_per_cm), card_h=round(CARD_MM[1] / 10 * scale_px_per_cm),
        wafer_px=wafer_px, wafer_side=round(side_mm * px_per_mm),
        wafer_slots=wafer_slots(side_mm, beat.count, px_per_mm) if beat.visual == "wafer" else [])


def hold_seconds(beat: ShortBeat, seconds: float) -> float:
    """Longest time the stage stays unchanged during this beat (the cat bobs throughout)."""
    if beat.visual in ("grow", "wafer"):
        steps = len(beat.items) if beat.visual == "grow" else beat.count
        return round(seconds / max(1, steps), 2)
    if beat.visual == "scale":
        return round(seconds * 0.3, 2)            # square, card at 45%, caption at 70%
    if beat.visual == "number":
        unit_at, bubble_at = number_times(seconds)
        return round(max(unit_at, bubble_at - unit_at, seconds - bubble_at), 2)
    return round(seconds - 0.4, 2)


def _concat_audio(work: Path, audios: list[Path]) -> Path:
    out = work / "narration.m4a"
    inputs = [arg for audio in audios for arg in ("-i", str(audio.resolve()))]
    graph = "".join(f"[{i}:a]" for i in range(len(audios))) + f"concat=n={len(audios)}:v=0:a=1[a]"
    ffmpeg_ops_run(work, [*inputs, "-filter_complex", graph, "-map", "[a]", "-c:a", "aac", "-b:a", "192k",
                          str(out.resolve())])
    return out


def ffmpeg_ops_run(cwd: Path, args: list[str]) -> None:
    from content_farm.production.shorts_render import _ffmpeg

    _ffmpeg(args, cwd)


def render_scripted(run_dir: Path, channel: Channel) -> ScriptedResult:
    from content_farm.assembly.drawtext import find_cjk_font
    from content_farm.explainer.capture import PageCapturer
    from content_farm.explainer.mascot.still import pose_png
    from content_farm.production.shorts_render import SIZE, ass_text

    spec = cut.load_spec(run_dir)
    script = Script.model_validate_json((run_dir / "script.json").read_text(encoding="utf-8"))
    if len(script.scenes) != len(spec.beats):
        raise ValueError(f"script.json has {len(script.scenes)} scenes for {len(spec.beats)} beats; re-run voice")
    seconds = [scene.duration_seconds for scene in script.scenes]
    audios = [run_dir / "audio" / f"scene_{i:03d}.mp3" for i in range(1, len(spec.beats) + 1)]
    missing = [a.name for a in audios if not a.is_file()]
    if missing:
        raise FileNotFoundError(f"voice audio missing: {', '.join(missing)}")
    work = run_dir / "short"
    work.mkdir(parents=True, exist_ok=True)
    pngtuber = channel.mascot.rig_ready and channel.mascot.host == "pngtuber"
    if pngtuber:   # the host is overlaid afterwards; the beats keep the cat's slot empty
        blank = work / "host_slot.png"
        Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(blank)
        cats = {pose: blank for pose in {b.pose for b in spec.beats}}
    else:
        cats = {pose: pose_png(pose, work / f"cat_{pose}.png") for pose in {b.pose for b in spec.beats}}

    cues = cut.relayout(cut.parse_cues((run_dir / "subtitles" / "subtitles.srt").read_text(encoding="utf-8")))
    (run_dir / "subtitles" / "subtitles.srt").write_text(cut.to_srt(cues), encoding="utf-8")
    font = find_cjk_font()
    (work / "subs.ass").write_text(ass_text(cues, Path(font).stem if font else "Arial"), encoding="utf-8")

    clips, report = [], []
    with PageCapturer(size=SIZE) as capturer:
        for index, (beat, length) in enumerate(zip(spec.beats, seconds), start=1):
            html = work / f"beat_{index:02d}.html"
            html.write_text(beat_page(beat, length, spec, channel, cats[beat.pose].resolve().as_uri()),
                            encoding="utf-8")
            if index == 1:
                capturer.still(html, work / "intro.png")   # manual-kit uses it as the Shorts cover
            clips.append(capturer.animate(html, work / f"beat_{index:02d}.mp4", length).clip)
            report.append({"beat": index, "visual": beat.visual, "seconds": round(length, 2),
                           "longest_hold": hold_seconds(beat, length)})
    narration = _concat_audio(work, audios)
    total = round(sum(seconds), 3)
    out = run_dir / "assembly" / "final.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    inputs = [arg for clip in clips for arg in ("-i", clip.name)]
    n = len(clips)
    graph = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0,ass=subs.ass[v]"
    ffmpeg_ops_run(work, [*inputs, "-i", narration.name, "-filter_complex", graph, "-map", "[v]",
                          "-map", f"{n}:a", "-t", f"{total:.3f}", "-r", str(ffmpeg_ops.FPS), "-c:v", "libx264",
                          "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                          "-movflags", "+faststart", str(out.resolve())])
    longest = max(item["longest_hold"] for item in report)
    (run_dir / BEAT_REPORT).write_text(json.dumps({"max_step_seconds": MAX_STEP_SECONDS, "beats": report},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
    if pngtuber:
        _overlay_host(run_dir, out, channel.mascot.ref, spec.beats, seconds)
    return ScriptedResult(video=out, seconds=total, beats=n, longest_hold=longest)


def _overlay_host(run_dir: Path, rendered: Path, pack_ref: str, beats: tuple[ShortBeat, ...],
                  seconds: list[float]) -> None:
    """The beats without a cat become draft.mp4; the PNGtuber goes bottom-left with each beat's pose."""
    from content_farm.explainer.mascot.cues import SceneCue
    from content_farm.explainer.pngtuber.run import run_host_overlay

    draft = rendered.with_name("draft.mp4")
    rendered.replace(draft)
    starts = [sum(seconds[:i]) for i in range(len(seconds) + 1)]
    cues = tuple(SceneCue(index=i, start=starts[i - 1], end=starts[i], pose=beat.pose)
                 for i, beat in enumerate(beats, start=1))
    run_host_overlay(run_dir, pack_ref, cues=cues, out=rendered)
