"""Render a 「一個數字」 Short planned by :mod:`content_farm.production.shorts_cut`.

Outputs in the Short's run-dir (same names the runner, QC and ``package`` read):
``script.json``, ``audio/scene_001.mp3``, ``subtitles/subtitles.srt``,
``credits.json``, ``assembly/final.mp4`` (1080x1920, H.264 + AAC), and the
three captured pages under ``short/`` for the review page.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from content_farm.explainer import ffmpeg_ops
from content_farm.explainer.brands import brand_css_path
from content_farm.explainer.capture import PageCapturer
from content_farm.explainer.deck import load_deck
from content_farm.production import shorts_cut as cut
from content_farm.production.channels import Channel
from content_farm.script_gen.schemas import Script

TEMPLATES = Path(__file__).parent / "templates"
SIZE = (cut.FRAME_W, cut.FRAME_H)
FFMPEG_TIMEOUT = 900


@dataclass(frozen=True)
class CutResult:
    video: Path
    timing: cut.Timing
    cues: int


def page_html(mode: str, spec: cut.ShortSpec, channel: Channel, source: str) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    css = brand_css_path(channel.brand).read_text(encoding="utf-8")
    return env.get_template("short_card.html.j2").render(
        mode=mode, spec=spec, channel_name=channel.name, source=source, brand_css=css)


def _ass_time(seconds: float) -> str:
    centis = round(seconds * 100)
    hours, rest = divmod(centis, 360_000)
    minutes, rest = divmod(rest, 6000)
    secs, centis = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def ass_text(cues: list[cut.Cue], font_name: str) -> str:
    """Bottom-centred white text with a thick ink outline (the brand's comic lettering)."""
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {cut.FRAME_W}\nPlayResY: {cut.FRAME_H}\nScaledBorderAndShadow: yes\nWrapStyle: 2\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{cut.SUB_FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00141414,&H00141414,"
        f"1,0,0,0,100,100,0,0,1,{cut.SUB_OUTLINE},4,2,{cut.SUB_MARGIN_X},{cut.SUB_MARGIN_X},"
        f"{cut.SUB_MARGIN_V},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = [
        f"Dialogue: 0,{_ass_time(c.start)},{_ass_time(c.end)},Default,,0,0,0,,"
        + c.text.replace("{", "(").replace("}", ")").replace("\n", "\\N")
        for c in cues
    ]
    return header + "\n".join(events) + "\n"


def _ffmpeg(args: list[str], cwd: Path) -> None:
    try:
        result = subprocess.run(["ffmpeg", "-y", "-hide_banner", *args], cwd=cwd, capture_output=True,
                                text=True, timeout=FFMPEG_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ffmpeg_ops.FFmpegError(f"ffmpeg failed to run: {exc}") from exc
    if result.returncode != 0:
        raise ffmpeg_ops.FFmpegError(f"ffmpeg exit {result.returncode}: {result.stderr[-800:]}")


def _capture_pages(work: Path, spec: cut.ShortSpec, channel: Channel, source: str,
                   timing: cut.Timing) -> list[Path]:
    clips = []
    with PageCapturer(size=SIZE) as capturer:
        for mode, seconds in (("intro", timing.intro), ("body", timing.body), ("outro", timing.outro)):
            html = work / f"{mode}.html"
            html.write_text(page_html(mode, spec, channel, source), encoding="utf-8")
            capturer.still(html, work / f"{mode}.png")
            if mode == "body":
                clips.append(capturer.animate(html, work / "body.mp4", seconds).clip)
            else:
                clips.append(ffmpeg_ops.still_to_clip(work / f"{mode}.png", work / f"{mode}.mp4", seconds,
                                                      size=SIZE))
    return clips


def _compose(work: Path, clips: list[Path], audio: Path, timing: cut.Timing, out: Path) -> Path:
    """Concat the three silent clips, burn subtitles, pad the narration with silence for the outro."""
    inputs = [arg for clip in clips for arg in ("-i", clip.name)]
    graph = (f"[0:v][1:v][2:v]concat=n=3:v=1:a=0,ass=subs.ass[v];"
             f"[3:a]apad=whole_dur={timing.total:.3f}[a]")
    out.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg([*inputs, "-i", str(audio.resolve()), "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
             "-t", f"{timing.total:.3f}", "-r", str(ffmpeg_ops.FPS), "-c:v", "libx264", "-preset", "medium",
             "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
             str(out.resolve())], cwd=work)
    return out


def render_short(run_dir: Path, channel: Channel) -> CutResult:
    spec = cut.load_spec(run_dir)
    long_dir = Path(spec.long_run_dir)
    deck = load_deck(long_dir / "deck.json")
    slide = next((s for s in deck.slides if s.id == spec.slide_id), None)
    if slide is None:
        raise ValueError(f"slide {spec.slide_id!r} is not in {long_dir}/deck.json")
    index = cut.slide_index(deck, slide.id)
    start, end = cut.scene_window(cut.scene_durations(long_dir), index)
    timing = cut.plan_timing(end - start, spec.intro_seconds, spec.outro_seconds)

    source_srt = (long_dir / "subtitles" / "subtitles.srt").read_text(encoding="utf-8")
    cues = cut.relayout(cut.cues_in_window(cut.parse_cues(source_srt), start, end))
    (run_dir / "subtitles").mkdir(parents=True, exist_ok=True)
    (run_dir / "subtitles" / "subtitles.srt").write_text(cut.to_srt(cues), encoding="utf-8")

    audio = run_dir / "audio" / "scene_001.mp3"
    audio.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(long_dir / "audio" / f"scene_{index:03d}.mp3", audio)

    long_script = Script.model_validate_json((long_dir / "script.json").read_text(encoding="utf-8"))
    script = cut.short_script(long_script, deck, slide, spec, timing)
    (run_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    cut.write_credits(run_dir, spec)

    work = run_dir / "short"
    work.mkdir(parents=True, exist_ok=True)
    from content_farm.assembly.drawtext import find_cjk_font

    font = find_cjk_font()
    (work / "subs.ass").write_text(ass_text(cues, Path(font).stem if font else "Arial"), encoding="utf-8")
    clips = _capture_pages(work, spec, channel, cut.source_note(deck, slide), timing)
    video = _compose(work, clips, audio, timing, run_dir / "assembly" / "final.mp4")
    return CutResult(video=video, timing=timing, cues=len(cues))
