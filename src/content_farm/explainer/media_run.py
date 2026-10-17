"""``media_to_visual``: deck + measured durations → ``visual/`` clips, credits, report.

Order of work:
1. one clip per slide (:mod:`content_farm.explainer.media`), exact slot length;
2. transitions (optional): the tail of clip N blends into clip N+1's first
   frame, so slots never overlap and assembly needs no xfade support;
3. copy onto the timeline names in ``visual/``; write ``credits.json``,
   ``media/media_report.json`` and ``media/contact_sheet.png``.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from content_farm.explainer import ffmpeg_ops
from content_farm.explainer.ai_images import write_prompt_files
from content_farm.explainer.artwork import artwork_credits_text
from content_farm.explainer.capture import PageCapturer
from content_farm.explainer.deck import Deck
from content_farm.explainer.media import USED_PLACEHOLDER, ClipResult, MediaContext, SlideJob, build_clip
from content_farm.explainer.motion_cache import MotionPaths
from content_farm.explainer.pages import build_pages
from content_farm.explainer.render import _label_font
from content_farm.explainer.stage_cues import plan as stage_plan
from content_farm.explainer.stock import StockClient
from content_farm.explainer.timeline import SlideClip, place_files

logger = logging.getLogger(__name__)

TRANSITION_CHOICES = ("none", *ffmpeg_ops.TRANSITIONS)
MIN_TRANSITION, MAX_TRANSITION = 0.1, 1.0


@dataclass(frozen=True)
class MediaOptions:
    transition: str = "crossfade"
    transition_seconds: float = 0.4
    replace: bool = False
    brand: str | None = None  # channel brand (see explainer.brands); None = category theme
    motion_paths: MotionPaths | None = None  # ai_image motion tools; None = Ken Burns
    staged: bool = True   # v3: reveal slide parts with the narration + pulses (no still > 7 s)

    def __post_init__(self) -> None:
        if self.transition not in TRANSITION_CHOICES:
            raise ValueError(f"transition must be one of {TRANSITION_CHOICES}")
        if not MIN_TRANSITION <= self.transition_seconds <= MAX_TRANSITION:
            raise ValueError(f"transition_seconds must be {MIN_TRANSITION}-{MAX_TRANSITION}")


@dataclass(frozen=True)
class MediaRun:
    results: tuple[ClipResult, ...]
    placed: tuple[Path, ...]
    credits_path: Path
    report_path: Path
    contact_sheet: Path


def jobs_for(deck: Deck, clips: Sequence[SlideClip], brand: str | None = None,
             narration: dict[str, list[tuple[float, str]]] | None = None) -> list[SlideJob]:
    """``narration``: per slide id, (seconds from the slide's start, sentence) — when given,
    animated slides and news cards are staged to it (stage_cues)."""
    if len(clips) != len(deck.slides):
        raise ValueError(f"{len(clips)} timeline slots for {len(deck.slides)} slides")
    animated_pages = build_pages(deck, animate=True, brand=brand)
    sections = [section for section in deck.sections for _ in section.slides]
    jobs = []
    for c in clips:
        slide = deck.slides[c.index - 1]
        stage = stage_plan(slide, narration.get(slide.id, []), c.seconds) if narration is not None else None
        jobs.append(SlideJob(index=c.index, section=sections[c.index - 1], slide=slide,
                             seconds=c.seconds, animated_page=animated_pages[c.index - 1], stage=stage))
    return jobs


def narration_by_slide(run_dir: Path) -> dict[str, list[tuple[float, str]]] | None:
    """Sentence timings from the voice step (script.json durations + aligned SRT); None before voice."""
    from content_farm.retention.timing import load_scenes, sentence_timeline

    try:
        scenes = load_scenes(run_dir)
        sentences = sentence_timeline(run_dir, scenes)
    except (OSError, KeyError, ValueError) as exc:
        logger.warning("no narration timing for staging (%s); slides keep the entrance-only animation", exc)
        return None
    starts = {s.slide_id: s.start for s in scenes}
    out: dict[str, list[tuple[float, str]]] = {}
    for sentence in sentences:
        out.setdefault(sentence.slide_id, []).append((round(sentence.start - starts[sentence.slide_id], 2),
                                                      sentence.text))
    return out


def media_to_visual(
    deck: Deck, run_dir: Path, clips: Sequence[SlideClip], *,
    stock: StockClient | None, options: MediaOptions = MediaOptions(),
) -> MediaRun:
    work_dir = run_dir / "media"
    write_prompt_files(deck, run_dir)
    jobs = jobs_for(deck, clips, brand=options.brand,
                    narration=narration_by_slide(run_dir) if options.staged else None)
    with PageCapturer() as capturer:
        ctx = MediaContext(deck=deck, run_dir=run_dir, work_dir=work_dir, capturer=capturer,
                           stock=stock, static_png_ok=options.transition == "none",
                           brand=options.brand, motion_paths=options.motion_paths)
        results = [build_clip(ctx, job) for job in jobs]
    finals = apply_transitions(results, work_dir, options)
    placed = place_files(clips, finals, run_dir / "visual", replace=options.replace)
    credits_path = write_credits(deck, results, run_dir / "credits.json")
    report_path = write_report(results, finals, options, work_dir / "media_report.json")
    sheet = media_contact_sheet(results, work_dir / "contact_sheet.png", work_dir / "sheet_frames")
    return MediaRun(tuple(results), tuple(placed), credits_path, report_path, sheet)


def apply_transitions(
    results: Sequence[ClipResult], work_dir: Path, options: MediaOptions,
) -> list[Path]:
    """Final file per slot. With ``none`` the built clips are used as they are."""
    paths = [r.path for r in results]
    if options.transition == "none" or len(paths) < 2:
        return paths
    out_dir = work_dir / "final"
    finals: list[Path] = []
    for i, result in enumerate(results):
        if i == len(results) - 1:
            final = out_dir / f"clip_{result.index:03d}.mp4"
            final.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result.path, final)
        else:
            head = ffmpeg_ops.first_frame(paths[i + 1], work_dir / "heads" / f"head_{i + 2:03d}.png")
            final = ffmpeg_ops.transition_into(
                result.path, head, out_dir / f"clip_{result.index:03d}.mp4", result.seconds,
                style=options.transition, length=options.transition_seconds,
            )
        finals.append(final)
    return finals


def ai_credits_text(entries: Sequence[dict]) -> str:
    """Which models drew (and moved) the 「AI 示意圖」 frames, one line per model or tool."""
    models: dict[str, dict] = {}
    motion: dict[str, dict] = {}
    for entry in entries:
        if entry.get("kind") != "ai_image":
            continue
        models.setdefault(entry.get("model_name") or entry.get("model") or "未記錄", entry)
        move = entry.get("motion") or {}
        if move.get("kind") == "wan":
            motion.setdefault(f"動態 / motion: {move.get('model_name')}", {
                "origin_repo": move.get("origin_repo"), "license_url": move.get("license_url")})
        elif move.get("kind") == "parallax":
            motion.setdefault(f"景深視差 / 2.5D parallax: {move.get('tool')}（工具）", {
                "origin_repo": move.get("tool_repo"), "license_url": move.get("tool_license_url")})
    if not models:
        return ""
    lines = ["AI 示意圖 / AI illustrations（非史料，僅示意）:"]
    for name, entry in {**models, **motion}.items():
        origin = entry.get("origin_repo")
        lines.append(f"- {name}" + (f"（{origin}, {entry.get('license_url', '')}）" if origin else ""))
    return "\n".join(lines)


def credits_text(entries: Sequence[dict]) -> str:
    """Ready-to-paste block for the YouTube description."""
    blocks = [block for block in (artwork_credits_text(entries), ai_credits_text(entries)) if block]
    artwork = "\n\n".join(blocks)
    stock = [e for e in entries if e.get("kind") == "stock"]
    if not stock:
        return artwork
    lines = [artwork, ""] if artwork else []
    lines.append("影片素材 / Stock footage:")
    for e in stock:
        provider = e["provider"].capitalize()
        lines.append(f"- {e['author'] or 'Unknown'} on {provider}: {e['source_url']} ({e['license']})")
    if any(e["provider"] == "pexels" for e in stock):
        lines.append("Videos provided by Pexels — https://www.pexels.com")
    if any(e["provider"] == "pixabay" for e in stock):
        lines.append("Videos from Pixabay — https://pixabay.com")
    return "\n".join(lines)


def write_credits(deck: Deck, results: Sequence[ClipResult], path: Path) -> Path:
    entries = [r.credit for r in results if r.credit]
    # Slots with no asset yet: not credited, but listed so "complete" is checkable.
    pending = [{"slide_id": r.slide_id, "slide_index": r.index, "kind": r.requested,
                "reason": r.note} for r in results if r.used == USED_PLACEHOLDER]
    payload = {
        "version": 1,
        "title": deck.title,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entries": entries,
        "pending": pending,
        "description_text": credits_text(entries),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_report(
    results: Sequence[ClipResult], finals: Sequence[Path], options: MediaOptions, path: Path,
) -> Path:
    payload = {
        "transition": options.transition,
        "transition_seconds": options.transition_seconds,
        "slides": [
            {"index": r.index, "slide_id": r.slide_id, "requested": r.requested, "used": r.used,
             "fallback": r.requested != r.used and r.used != USED_PLACEHOLDER or None,
             "placeholder": r.used == USED_PLACEHOLDER or None,
             "review": r.review or None,
             "seconds": r.seconds, "build_seconds": r.build_seconds, "note": r.note,
             "problems": list(r.problems), "file": str(f)}
            for r, f in zip(results, finals)
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _thumb_source(result: ClipResult, frames_dir: Path) -> Path:
    if result.path.suffix.lower() == ".png":
        return result.path
    at = min(max(result.seconds - 0.6, 0), 3.0)  # after the entrance animation settles
    return ffmpeg_ops.frame_at(result.path, at, frames_dir / f"frame_{result.index:03d}.png")


def media_contact_sheet(
    results: Sequence[ClipResult], out_path: Path, frames_dir: Path,
    *, columns: int = 3, thumb_width: int = 560,
) -> Path:
    """Review sheet: one frame per slot; placeholders and fallbacks get a red frame + tag,
    stock clips awaiting a human check an orange one."""
    thumb_h = thumb_width * 1080 // 1920
    gutter, label_h = 24, 44
    rows = -(-len(results) // columns)
    sheet = Image.new("RGB", (gutter + columns * (thumb_width + gutter),
                              gutter + rows * (thumb_h + label_h + gutter)), "#0e0f12")
    draw = ImageDraw.Draw(sheet)
    font, tag_font = _label_font(22), _label_font(34)
    for i, r in enumerate(results):
        x = gutter + (i % columns) * (thumb_width + gutter)
        y = gutter + (i // columns) * (thumb_h + label_h + gutter)
        with Image.open(_thumb_source(r, frames_dir)) as img:
            sheet.paste(img.convert("RGB").resize((thumb_width, thumb_h), Image.LANCZOS), (x, y))
        flagged = r.used == USED_PLACEHOLDER or r.requested != r.used
        if flagged:
            draw.rectangle((x - 4, y - 4, x + thumb_width + 4, y + thumb_h + 4), outline="#ff2d2d", width=8)
            tag = "AI 圖待補" if r.used == USED_PLACEHOLDER else f"退回 {r.used}"
            draw.rectangle((x, y, x + 230, y + 56), fill="#d62828")
            draw.text((x + 14, y + 8), tag, fill="#ffffff", font=tag_font)
        elif r.review:
            draw.rectangle((x - 4, y - 4, x + thumb_width + 4, y + thumb_h + 4), outline="#ff9f1c", width=8)
            draw.rectangle((x, y, x + 330, y + 56), fill="#e07a00")
            draw.text((x + 14, y + 8), "B-roll 待人工確認", fill="#ffffff", font=tag_font)
        label = f"{r.index:02d} · {r.slide_id} · {r.requested}" + (f"→{r.used}" if flagged else "")
        draw.text((x, y + thumb_h + 8), label, fill="#ff6b6b" if flagged else "#d8dbe0", font=font)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, optimize=True)
    return out_path
