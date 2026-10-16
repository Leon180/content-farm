"""Render an HN 快報 Short: five beat pages + an end card, mascot, burned subtitles.

Reads (written by earlier steps): ``news_script.json``, ``news_short.json``,
``script.json`` (scene durations measured by the voice step),
``audio/scene_00N.mp3``, ``subtitles/subtitles.srt``.
Writes: ``assembly/final.mp4`` (1080x1920 H.264+AAC), ``thumbnails/thumbnail.png``,
``credits.json``, the 9:16 re-wrapped ``subtitles/subtitles.srt``, pages under ``short/``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from content_farm.explainer import ffmpeg_ops
from content_farm.explainer.brands import brand_css_path
from content_farm.production import shorts_cut as cut
from content_farm.production.channels import Channel
from content_farm.production.news import script as ns
from content_farm.production.shorts_render import _ffmpeg, ass_text
from content_farm.script_gen.schemas import Script
from content_farm.subtitle.line_wrap import wrap_text

TEMPLATES = Path(__file__).parent / "templates"
SIZE = (cut.FRAME_W, cut.FRAME_H)
WORK = "short"
BUBBLES = {"hook": "先講結論！", "what": "原文重點", "why": "跟台灣有關的是…", "analogy": "換個說法",
           "take": "我的看法"}


@dataclass(frozen=True)
class RenderResult:
    video: Path
    seconds: float
    cues: int


def _wrap(text: str, max_chars: int = cut.SUB_MAX_CHARS) -> list[str]:
    """CJK-aware 9:16 wrap: join without spaces, then the strict wrap the Short cutter uses."""
    out: list[str] = []
    for line in wrap_text(text.replace("\n", ""), max_chars).split("\n"):
        out.extend(wrap_text(line, max_chars - 4).split("\n") if len(line) > max_chars + 1 else [line])
    return [line for line in out if line.strip()]


def relayout(cues: list[cut.Cue]) -> list[cut.Cue]:
    """≤ 2 lines per cue; longer cues are split in time by text length."""
    out: list[cut.Cue] = []
    for cue in cues:
        lines = _wrap(cue.text)
        groups = [lines[i:i + cut.SUB_MAX_LINES] for i in range(0, len(lines), cut.SUB_MAX_LINES)] or [[""]]
        weights = [max(1, sum(len(x) for x in g)) for g in groups]
        clock, span = cue.start, cue.end - cue.start
        for group, weight in zip(groups, weights):
            length = span * weight / sum(weights)
            out.append(cut.Cue(round(clock, 3), round(clock + length, 3), "\n".join(group)))
            clock += length
    return out


def reveal_times(points: int, seconds: float) -> list[float]:
    """Spread bullet reveals over the beat so the picture changes every ~2–3 s."""
    if points == 0:
        return []
    step = max(0.6, min(3.0, (seconds - 0.8) / (points + 1)))
    return [round(0.8 + step * (i + 0.5), 2) for i in range(points)]


def source_strip(news: ns.NewsScript) -> str:
    primary = next((s for s in news.sources if s.kind in ("article", "abstract")), news.sources[0])
    who = primary.publisher or primary.title[:28]
    when = primary.read_at[5:10] if primary.read_at else ""
    return f"來源：{who}・{when} 讀原文。摘要＋評論，非翻譯；連結見說明欄"


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))


def page_html(mode: str, *, news: ns.NewsScript, channel: Channel, day: str, index: int = 0,
              duration: float = 0.1, mascot: dict[str, str] | None = None) -> str:
    beat = news.beats[index] if mode != "end" else None
    kind = beat.kind if beat else "end"
    return _env().get_template("news_short.html.j2").render(
        mode=mode, beat=beat, index=index, kinds=ns.BEAT_ORDER, day=day,
        label=ns.BEAT_LABELS.get(kind, ""), brand_css=brand_css_path(channel.brand).read_text(encoding="utf-8"),
        reveal_at=reveal_times(len(beat.screen.points) if beat else 0, duration), duration=f"{duration:.3f}",
        mascot=mascot or {"closed": "", "open": ""}, talking=mode == "beat",
        bubble=(beat.term if beat and beat.kind == "analogy" and beat.term else BUBBLES.get(kind, "週六見！")),
        source=source_strip(news))


def mascot_stills(work: Path, poses: set[str]) -> dict[str, dict[str, str]]:
    """{pose: {"closed": png, "open": png}} via the chipcat rig (cached by file name)."""
    from content_farm.explainer.mascot.motion import Frame
    from content_farm.explainer.mascot.params import PARAM_DEFAULTS, pose_vector
    from content_farm.explainer.mascot.render import capture_pngs

    def frame(pose: str, mouth: float) -> Frame:
        v = pose_vector(pose)
        params = {**PARAM_DEFAULTS,
                  "ParamAngleX": v["AngleX"], "ParamAngleY": v["AngleY"], "ParamAngleZ": v["AngleZ"],
                  "ParamBodyAngleX": v["BodyAngleX"], "ParamBodyY": v["BodyY"],
                  "ParamEyeLOpen": v["EyeOpen"], "ParamEyeROpen": v["EyeOpen"],
                  "ParamEyeLSmile": v["EyeSmile"], "ParamEyeRSmile": v["EyeSmile"],
                  "ParamEyeBallX": v["EyeBallX"], "ParamEyeBallY": v["EyeBallY"], "ParamPupil": v["Pupil"],
                  "ParamMouthForm": v["MouthForm"], "ParamMouthO": v["MouthO"], "ParamMouthOpenY": mouth,
                  "ParamEarL": v["EarBase"], "ParamEarR": v["EarBase"], "ParamTailPuff": v["TailPuff"],
                  "ParamArmR": v["ArmR"], "ParamArmRWave": v["WaveAmp"] * 0.6, "ParamBreath": 0.5,
                  "ParamTail": 0.3, "ParamTail2": -0.2, "ParamBubble": 0.0}
        return Frame(params=params, say=None)

    out: dict[str, dict[str, str]] = {}
    wanted = [(pose, state, mouth) for pose in sorted(poses) for state, mouth in (("closed", 0.0), ("open", 0.75))]
    missing = [(p, s, m) for p, s, m in wanted if not (work / f"cat_{p}_{s}.png").is_file()]
    if missing:
        for (pose, state, _), png in zip(missing, capture_pngs([frame(p, m) for p, _, m in missing])):
            (work / f"cat_{pose}_{state}.png").write_bytes(png)
    for pose, state, _ in wanted:
        out.setdefault(pose, {})[state] = f"cat_{pose}_{state}.png"
    return out


def beat_durations(script: Script) -> list[float]:
    return [scene.duration_seconds for scene in script.scenes]


def _concat_audio(run_dir: Path, count: int, out: Path) -> Path:
    inputs = [arg for i in range(1, count + 1) for arg in ("-i", str((run_dir / "audio" / f"scene_{i:03d}.mp3").resolve()))]
    graph = "".join(f"[{i}:a]" for i in range(count)) + f"concat=n={count}:v=0:a=1[a]"
    _ffmpeg([*inputs, "-filter_complex", graph, "-map", "[a]", "-c:a", "pcm_s16le", str(out.resolve())], cwd=run_dir)
    return out


def _compose(work: Path, clips: list[Path], audio: Path, total: float, out: Path) -> Path:
    inputs = [arg for clip in clips for arg in ("-i", clip.name)]
    n = len(clips)
    graph = ("".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0,ass=subs.ass[v];"
             f"[{n}:a]apad=whole_dur={total:.3f}[a]")
    out.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg([*inputs, "-i", str(audio.resolve()), "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
             "-t", f"{total:.3f}", "-r", str(ffmpeg_ops.FPS), "-c:v", "libx264", "-preset", "medium",
             "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
             str(out.resolve())], cwd=work)
    return out


def write_credits(run_dir: Path, news: ns.NewsScript) -> Path:
    """No third-party media: self-made pages, the chipcat rig, our narration. Sources go in the description."""
    payload = {"version": 1, "title": news.title, "entries": [], "pending": [], "description_text": "",
               "derived_from": {"series": "hn", "item_id": news.item_id,
                                "sources": [s.model_dump() for s in news.sources]}}
    path = run_dir / "credits.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _subtitles(run_dir: Path, work: Path) -> int:
    from content_farm.assembly.drawtext import find_cjk_font

    srt = run_dir / "subtitles" / "subtitles.srt"
    cues = relayout(cut.parse_cues(srt.read_text(encoding="utf-8")))
    srt.write_text(cut.to_srt(cues), encoding="utf-8")   # QC and the manual kit read the 9:16 version
    font = find_cjk_font()
    (work / "subs.ass").write_text(ass_text(cues, Path(font).stem if font else "Arial"), encoding="utf-8")
    return len(cues)


def render_news_short(run_dir: Path, channel: Channel) -> RenderResult:
    from content_farm.explainer.capture import PageCapturer

    news = ns.load_script(run_dir)
    day = ns.load_item(run_dir).get("day", "")
    script = Script.model_validate_json((run_dir / "script.json").read_text(encoding="utf-8"))
    durations = beat_durations(script)
    if len(durations) != len(news.beats):
        raise ValueError(f"script.json has {len(durations)} scenes, news_script.json {len(news.beats)} beats")
    total = sum(durations) + ns.END_CARD_SECONDS
    if total > cut.MAX_SHORT_SECONDS:
        raise ValueError(f"Short would run {total:.1f}s (limit {cut.MAX_SHORT_SECONDS:.0f}s); shorten the script")
    work = run_dir / WORK
    work.mkdir(parents=True, exist_ok=True)
    cues = _subtitles(run_dir, work)
    poses = {b.pose or ns.DEFAULT_POSE[b.kind] for b in news.beats} | {"wave"}
    cats = mascot_stills(work, poses)
    clips = []
    with PageCapturer(size=SIZE) as capturer:
        for i, (beat, seconds) in enumerate(zip(news.beats, durations)):
            html = work / f"beat_{i + 1}_{beat.kind}.html"
            html.write_text(page_html("beat", news=news, channel=channel, day=day, index=i, duration=seconds,
                                      mascot=cats[beat.pose or ns.DEFAULT_POSE[beat.kind]]), encoding="utf-8")
            clips.append(capturer.animate(html, work / f"beat_{i + 1}.mp4", seconds).clip)
        end = work / "end.html"
        end.write_text(page_html("end", news=news, channel=channel, day=day, duration=ns.END_CARD_SECONDS,
                                 mascot={"closed": cats["wave"]["closed"], "open": ""}), encoding="utf-8")
        clips.append(capturer.animate(end, work / "end.mp4", ns.END_CARD_SECONDS).clip)
        thumb = work / "thumb.html"
        hook = news.beats[0]
        thumb.write_text(page_html("thumb", news=news, channel=channel, day=day, index=0,
                                   mascot={"closed": cats[hook.pose or ns.DEFAULT_POSE["hook"]]["closed"], "open": ""}),
                         encoding="utf-8")
        capturer.still(thumb, run_dir / "thumbnails" / "thumbnail.png")
    audio = _concat_audio(run_dir, len(durations), work / "narration.wav")
    video = _compose(work, clips, audio, total, run_dir / "assembly" / "final.mp4")
    write_credits(run_dir, news)
    return RenderResult(video=video, seconds=round(total, 2), cues=cues)
