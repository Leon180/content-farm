"""Render a fable: picture-book segments → concept-diagram segments (xfade at the reveal) → subtitles → ``final.mp4``.

Reads ``fable.json``, ``script.json`` (scene durations measured by the voice step), ``audio/scene_*.mp3``,
``subtitles/subtitles.srt`` and the picture manifest (``fable_images``). Writes ``assembly/final.mp4``
(1080×1920 for a Short, 1920×1080 for the mid-length video), ``thumbnails/thumbnail.png``, ``credits.json``, and the
re-wrapped ``subtitles/subtitles.srt``. Working files live in ``fable_work/``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from content_farm.explainer.ai_images import AI_IMAGE_DIR, find_image
from content_farm.production import shorts_cut as cut
from content_farm.production.channels import Channel
from content_farm.production.fable import cards, compose, images
from content_farm.production.fable.model import Beat, Fable, load
from content_farm.script_gen.schemas import Script

WORK = "fable_work"
SUBTITLES = {"short": {"chars": 13, "px": 66, "margin_v": 150, "outline": 5},
             "mid": {"chars": 22, "px": 52, "margin_v": 60, "outline": 4}}
MIN_SHOT_SECONDS = 1.5


@dataclass(frozen=True)
class RenderResult:
    video: Path
    seconds: float
    pictures: int
    drawn: int
    cues: int


def shot_seconds(total: float, shots: int) -> list[float]:
    """Split a beat's seconds over its pictures (equal parts, never below MIN_SHOT_SECONDS each)."""
    count = max(1, min(shots, int(total // MIN_SHOT_SECONDS) or 1))
    return [total / count] * count


def _loop_for(run_dir: Path, work: Path, manifest: dict, beat: Beat, shot_number: int) -> Path:
    """The ping-pong loop of the picture a shot shows (its own, or its ``reuse`` target's)."""
    drawn = manifest["shots"][f"{beat.id}.{shot_number}"]["image_id"]
    clip = Path(manifest["clips"][drawn]["clip"])
    return compose.pingpong(clip if clip.is_absolute() else run_dir / clip, work / f"{drawn}.pp.mp4", work)


def _overlays(capturer, fable: Fable, beat: Beat, seconds: float, work: Path) -> list[tuple[Path, float]]:
    """Panel PNGs of a diagram beat and when each appears (explain rows come in one by one)."""
    if beat.act != "explain" or not (beat.card and beat.card.rows):
        html = work / f"{beat.id}.html"
        html.write_text(cards.overlay_html(fable, beat), encoding="utf-8")
        return [(capturer.still(html, work / f"{beat.id}.png", transparent=True), 0.0)]
    rows = len(beat.card.rows)
    starts = [0.0, *cards.row_times(rows, seconds)]
    out = []
    for visible, start in enumerate(starts):
        html = work / f"{beat.id}_{visible}.html"
        html.write_text(cards.overlay_html(fable, beat, rows_visible=visible), encoding="utf-8")
        out.append((capturer.still(html, work / f"{beat.id}_{visible}.png", transparent=True), start))
    return out


def build_segments(run_dir: Path, work: Path, fable: Fable, durations: list[float], manifest: dict) -> tuple[list[Path], int | None, float]:
    """One mp4 per picture / diagram; returns (segments, index of the reveal segment, seconds before the reveal)."""
    from content_farm.explainer.capture import PageCapturer

    geo = cards.GEOMETRY[fable.format]
    segments: list[Path] = []
    reveal_at: int | None = None
    pre_seconds = 0.0
    with PageCapturer(size=geo.size) as capturer:
        for beat, seconds in zip(fable.beats, durations):
            if beat.act in ("hook", "story"):
                for n, part in enumerate(shot_seconds(seconds, len(beat.shots)), 1):
                    out = work / f"{beat.id}_{n}.mp4"
                    compose.picture_segment(_loop_for(run_dir, work, manifest, beat, n), geo.size, part, out, work)
                    segments.append(out)
                continue
            if beat.act == "reveal":
                reveal_at, pre_seconds = len(segments), sum(durations[:fable.beats.index(beat)])
            lead = compose.TRANSITION_SECONDS if beat.act == "reveal" else 0.0
            out = work / f"{beat.id}.mp4"
            fade = (lead + 0.2, 0.5) if beat.act == "reveal" else None
            compose.diagram_segment(_loop_for(run_dir, work, manifest, beat, 1), geo,
                                    _overlays(capturer, fable, beat, seconds + lead, work), seconds + lead, out, work, fade)
            segments.append(out)
    return segments, reveal_at, pre_seconds


def write_subtitles(run_dir: Path, work: Path, fable: Fable) -> int:
    """Re-wrap the voice step's cues for this frame, rewrite ``subtitles.srt`` and write ``subs.ass``."""
    from content_farm.assembly.drawtext import find_cjk_font

    spec = SUBTITLES[fable.format]
    srt = run_dir / "subtitles" / "subtitles.srt"
    cues = cut.relayout(cut.parse_cues(srt.read_text(encoding="utf-8")), spec["chars"], 2)
    srt.write_text(cut.to_srt(cues), encoding="utf-8")
    font = find_cjk_font()
    (work / "subs.ass").write_text(compose.ass_text(cues, cards.GEOMETRY[fable.format].size, Path(font).stem if font else "Arial",
                                                    spec["px"], spec["margin_v"], spec["outline"]), encoding="utf-8")
    return len(cues)


def write_thumbnail(run_dir: Path, work: Path, fable: Fable, channel: Channel, durations: list[float]) -> Path:
    """Thumbnail options (hook + thumbnail-composed picture) when fable.json has them, else the legacy title card;
    a Short also gets its suggested cover frame."""
    from content_farm.explainer.capture import PageCapturer
    from content_farm.production.fable import thumb

    if fable.format == "short":
        thumb.write_cover_frame(run_dir, fable, durations)
    if fable.thumb:
        return thumb.render_options(run_dir, fable, channel)["a"]
    first = find_image(run_dir / AI_IMAGE_DIR, images.drawn_shots(fable)[0].image_id)
    html = work / "thumb.html"
    html.write_text(cards.thumb_html(fable, first.resolve().as_uri(), channel.name), encoding="utf-8")
    with PageCapturer(size=cards.GEOMETRY[fable.format].size) as capturer:
        return capturer.still(html, run_dir / "thumbnails" / "thumbnail.png")


def write_credits(run_dir: Path, fable: Fable, manifest: dict) -> Path:
    payload = {"version": 1, "title": fable.title, "entries": images.credit_entries(run_dir, fable, manifest["clips"]),
               "pending": [], "description_text": "",
               "derived_from": {"series": "fable", "concept": fable.concept.name, "domain": fable.concept.domain,
                                "references": list(fable.concept.references)}}
    path = run_dir / "credits.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def render_fable(run_dir: Path, channel: Channel, env_file: Path | None = None) -> RenderResult:
    fable = load(run_dir)
    script = Script.model_validate_json((run_dir / "script.json").read_text(encoding="utf-8"))
    durations = [scene.duration_seconds for scene in script.scenes]
    if len(durations) != len(fable.beats):
        raise ValueError(f"script.json has {len(durations)} scenes, fable.json {len(fable.beats)} beats: run fable_prepare")
    work = run_dir / WORK
    work.mkdir(parents=True, exist_ok=True)
    manifest = images.load_manifest(run_dir)
    cues = write_subtitles(run_dir, work, fable)
    segments, reveal_at, pre_seconds = build_segments(run_dir, work, fable, durations, manifest)
    total = round(sum(durations), 3)
    scene_files = [run_dir / "audio" / f"scene_{i:03d}.mp3" for i in range(1, len(durations) + 1)]
    audio = compose.concat_audio(scene_files, work / "narration.wav", run_dir)
    video = compose.assemble(segments, reveal_at, pre_seconds, audio, total, run_dir / "assembly" / "final.mp4", work)
    write_thumbnail(run_dir, work, fable, channel, durations)
    write_credits(run_dir, fable, manifest)
    return RenderResult(video, total, len(manifest["clips"]), 0, cues)
