"""Build one timeline clip per slide according to ``slide.media.kind``.

Each builder returns a :class:`ClipResult` whose file is exactly as long as
the slide's slot (mp4) or a PNG still (plain ``slide`` with transitions off,
which keeps v1 output byte-identical). Stock and AI image problems never stop
the run: the slide falls back (to an animated slide / a placeholder) and the
reason is recorded.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from content_farm.explainer import ffmpeg_ops
from content_farm.explainer.ai_images import AI_IMAGE_DIR, find_image
from content_farm.explainer.artwork import ARTWORK_DIR, ARTWORK_MANIFEST, ArtworkEntry, credit_for, load_manifest
from content_farm.explainer.capture import PageCapturer
from content_farm.explainer.cards import overlay_html, placeholder_html, title_card_html
from content_farm.explainer.deck import Deck, MediaKind, Section, Slide
from content_farm.explainer.illustrate import AI_LABEL, load_record
from content_farm.explainer.motion import plan_motion
from content_farm.explainer.motion_cache import MotionPaths
from content_farm.explainer.pages import SlidePage
from content_farm.explainer.stage_cues import StagePlan
from content_farm.explainer.stock import StockClient, StockUnavailable, candidate_text, credit_entry

logger = logging.getLogger(__name__)

USED_PLACEHOLDER = "ai_placeholder"


@dataclass(frozen=True)
class ClipResult:
    index: int
    slide_id: str
    requested: str
    used: str            # slide | animated | stock | ai_image | ai_placeholder | title_card | artwork
    path: Path
    seconds: float       # slot length
    note: str = ""       # why a fallback happened, or stock fit mode, etc.
    credit: dict | None = None
    build_seconds: float = 0.0
    problems: tuple[str, ...] = ()
    review: bool = False  # needs a human look before publishing (every stock clip)


@dataclass(frozen=True)
class SlideJob:
    index: int
    section: Section
    slide: Slide
    seconds: float
    animated_page: SlidePage
    stage: StagePlan | None = None   # narration-cued reveals + pulses (None = entrance only)


def staged_html(html: str, stage: StagePlan | None) -> str:
    """Put the stage plan on <body> as data-cues / data-pulses for animate.js."""
    if stage is None:
        return html
    attrs = (f" data-cues='{json.dumps(list(stage.reveals))}'"
             f" data-pulses='{json.dumps([list(p) for p in stage.pulses])}'")
    return re.sub(r"<body\b", "<body" + attrs, html, count=1)


@dataclass
class MediaContext:
    deck: Deck
    run_dir: Path
    work_dir: Path
    capturer: PageCapturer
    stock: StockClient | None
    static_png_ok: bool  # True when transitions are off: plain slides stay PNG
    brand: str | None = None  # channel brand stylesheet (None = deck category theme)
    motion_paths: MotionPaths | None = None  # local video tools (None = ai_image falls back to Ken Burns)
    ai_image_dir: Path = field(init=False)
    artwork: dict[str, ArtworkEntry] = field(init=False)

    def __post_init__(self) -> None:
        self.ai_image_dir = self.run_dir / AI_IMAGE_DIR
        self.artwork = load_manifest(self.run_dir)

    def html(self, name: str, content: str) -> Path:
        path = self.work_dir / "html" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def clip_path(self, job: SlideJob, suffix: str) -> Path:
        return self.work_dir / "clips" / f"clip_{job.index:03d}{suffix}"


def build_clip(ctx: MediaContext, job: SlideJob) -> ClipResult:
    started = time.monotonic()
    kind = job.slide.media_kind
    builder = {
        MediaKind.SLIDE: _plain_slide,
        MediaKind.ANIMATED: _animated,
        MediaKind.STOCK: _stock,
        MediaKind.AI_IMAGE: _ai_image,
        MediaKind.TITLE_CARD: _title_card,
        MediaKind.ARTWORK: _artwork,
        MediaKind.DIAGRAM: _diagram,
    }[kind]
    if kind == MediaKind.SLIDE and job.stage is not None:
        builder = _animated   # v3: a plain slide gets pulses instead of holding still for its whole slot
    result = builder(ctx, job)
    elapsed = round(time.monotonic() - started, 2)
    logger.info("clip %02d %s → %s (%.1fs) %s", job.index, kind.value, result.used, elapsed, result.note)
    return replace(result, build_seconds=elapsed)


def _result(job: SlideJob, used: str, path: Path, **extra: object) -> ClipResult:
    return ClipResult(index=job.index, slide_id=job.slide.id, requested=job.slide.media_kind.value,
                      used=used, path=path, seconds=job.seconds, **extra)  # type: ignore[arg-type]


def _plain_slide(ctx: MediaContext, job: SlideJob) -> ClipResult:
    png = ctx.run_dir / "slides" / f"slide_{job.index:03d}.png"
    if not png.is_file():
        raise FileNotFoundError(f"missing rendered slide {png}; run render_slides first")
    if ctx.static_png_ok:
        return _result(job, "slide", png)
    return _result(job, "slide", ffmpeg_ops.still_to_clip(png, ctx.clip_path(job, ".mp4"), job.seconds))


def _animated(ctx: MediaContext, job: SlideJob, note: str = "") -> ClipResult:
    html = ctx.html(f"{job.animated_page.stem}_anim.html", staged_html(job.animated_page.html, job.stage))
    if job.stage is not None:
        capture = ctx.capturer.animate_staged(html, ctx.clip_path(job, ".mp4"), job.seconds)
        note = f"{note}staged {len(job.stage.reveals)} reveal(s) {len(job.stage.pulses)} pulse(s) " \
               f"hold≤{job.stage.longest_hold:.1f}s | "
    else:
        capture = ctx.capturer.animate(html, ctx.clip_path(job, ".mp4"), job.seconds)
    detail = f"{job.slide.animation.value} {capture.animation_seconds:.1f}s/{capture.frames_captured}f"
    return _result(job, "animated", capture.clip, note=f"{note}{detail}".strip(),
                   problems=capture.problems)


def _overlay_png(ctx: MediaContext, job: SlideJob, ai_label: str = "", lower_third: bool = True) -> Path:
    media = job.slide.media
    frame = media.frame_kind.value if media is not None and media.kind == MediaKind.AI_IMAGE else "lower"
    html = ctx.html(f"overlay_{job.index:03d}.html",
                    overlay_html(ctx.deck, job.section, job.slide, job.index, brand=ctx.brand,
                                 ai_label=ai_label, lower_third=lower_third, frame=frame))
    return ctx.capturer.still(html, ctx.work_dir / "overlays" / f"overlay_{job.index:03d}.png",
                              transparent=True)


def _stock(ctx: MediaContext, job: SlideJob) -> ClipResult:
    media = job.slide.media
    query, keywords = (media.query, media.keywords) if media else ("", ())
    try:
        if ctx.stock is None:
            raise StockUnavailable("stock disabled (--no-stock)")
        asset = ctx.stock.fetch(query, job.seconds, keywords)
        source_seconds = ffmpeg_ops.probe(asset.path)["duration"]
        clip, mode = ffmpeg_ops.stock_to_clip(
            asset.path, _overlay_png(ctx, job), ctx.clip_path(job, ".mp4"), job.seconds, source_seconds,
        )
    except (StockUnavailable, ffmpeg_ops.FFmpegError) as exc:
        logger.warning("slide %s: stock fallback → animated: %s", job.slide.id, exc)
        return _animated(ctx, job, note=f"FALLBACK stock→animated: {exc} | ")
    cache = "cache" if asset.from_cache else "download"
    note = (f"{asset.candidate.provider}:{asset.candidate.provider_id} {mode} ({cache}) "
            f"matched={'/'.join(asset.matched)} [{candidate_text(asset.candidate).strip()}]")
    # Keyword match is evidence, not proof: a human still watches every stock clip.
    return _result(job, "stock", clip, note=note, credit=credit_entry(asset, job.slide.id, job.index),
                   review=True)


def _ai_image(ctx: MediaContext, job: SlideJob) -> ClipResult:
    image = find_image(ctx.ai_image_dir, job.slide.id)
    out = ctx.clip_path(job, ".mp4")
    if image is not None:
        record = load_record(image)
        plan = plan_motion(ctx.motion_paths, ctx.run_dir, job.slide, job.index, image, record)
        overlay = _overlay_png(ctx, job, ai_label=AI_LABEL)
        if plan.clip is None:
            clip = ffmpeg_ops.ken_burns(image, overlay, out, job.seconds)
        else:
            clip = ffmpeg_ops.motion_loop(plan.clip, overlay, out, job.seconds, retime_fps=plan.retime_fps)
        return _result(job, "ai_image", clip, note=f"{plan.note} on {image.name} [{AI_LABEL}]",
                       credit={**_ai_credit(job, image, record), "motion": plan.credit},
                       problems=plan.problems)
    expected = (AI_IMAGE_DIR / f"{job.slide.id}.png").as_posix()
    html = ctx.html(f"placeholder_{job.index:03d}.html",
                    placeholder_html(ctx.deck, job.section, job.slide, job.index, expected,
                                     brand=ctx.brand))
    png = ctx.capturer.still(html, ctx.work_dir / "placeholders" / f"{job.slide.id}.png")
    clip = ffmpeg_ops.still_to_clip(png, out, job.seconds)
    return _result(job, USED_PLACEHOLDER, clip, note=f"PLACEHOLDER: {expected} not found")


def _ai_credit(job: SlideJob, image: Path, record: dict | None = None) -> dict:
    """Generation parameters from the illustrate sidecar; a hand-placed image has none
    (QC then flags the missing model / seed)."""
    record = record if record is not None else (load_record(image) or {})
    model = record.get("model_name") or record.get("model")
    licence = (f"AI-generated ({model}; model licence {record['license']}) for this channel"
               if model and record.get("license") else "AI-generated for this channel (generator unrecorded)")
    keep = ("provider", "model", "model_name", "repo", "origin_repo", "license_url", "seed", "steps", "size")
    return {"slide_id": job.slide.id, "slide_index": job.index, "kind": "ai_image", "file": image.name,
            "license": licence, "ai_generated": True, "ai_label": AI_LABEL,
            "prompt": record.get("prompt") or (job.slide.media.prompt if job.slide.media else ""),
            **{key: record[key] for key in keep if key in record}}


def _artwork(ctx: MediaContext, job: SlideJob) -> ClipResult:
    artwork_id = job.slide.media.artwork if job.slide.media else ""
    entry = ctx.artwork.get(artwork_id)
    image = entry.path(ctx.run_dir) if entry else None
    out = ctx.clip_path(job, ".mp4")
    if entry is not None and image is not None and image.is_file():
        html = ctx.html(f"overlay_{job.index:03d}.html",
                        overlay_html(ctx.deck, job.section, job.slide, job.index, brand=ctx.brand,
                                     artwork_caption=entry.caption))
        overlay = ctx.capturer.still(html, ctx.work_dir / "overlays" / f"overlay_{job.index:03d}.png",
                                     transparent=True)
        clip = ffmpeg_ops.artwork_plate(image, overlay, out, job.seconds)
        return _result(job, "artwork", clip, note=f"artwork {artwork_id} ({image.name})",
                       credit=credit_for(entry, artwork_id, slide_id=job.slide.id, index=job.index))
    expected = f"{(ARTWORK_DIR / ARTWORK_MANIFEST).as_posix()} → {artwork_id!r}"
    html = ctx.html(f"placeholder_{job.index:03d}.html",
                    placeholder_html(ctx.deck, job.section, job.slide, job.index, expected,
                                     brand=ctx.brand, tag="畫作待補"))
    png = ctx.capturer.still(html, ctx.work_dir / "placeholders" / f"{job.slide.id}.png")
    clip = ffmpeg_ops.still_to_clip(png, out, job.seconds)
    return _result(job, USED_PLACEHOLDER, clip, note=f"PLACEHOLDER: artwork {artwork_id!r} missing")


def _diagram(ctx: MediaContext, job: SlideJob) -> ClipResult:
    """Channel-drawn animated diagram under the usual overlay (top bar, lower-third, sources)."""
    from content_farm.explainer.diagrams.render import render_clip

    media = job.slide.media
    starts = list(job.stage.reveals) if job.stage else []
    raw = render_clip(media.diagram, dict(media.params), starts, job.seconds,
                      ctx.work_dir / "diagrams" / f"{job.slide.id}.mp4", brand=ctx.brand, heading=job.slide.heading)
    clip, _ = ffmpeg_ops.stock_to_clip(raw, _overlay_png(ctx, job, lower_third=False), ctx.clip_path(job, ".mp4"),
                                       job.seconds, job.seconds)
    return _result(job, "diagram", clip, note=f"diagram {media.diagram} stages at {starts}")


def _title_card(ctx: MediaContext, job: SlideJob) -> ClipResult:
    html = ctx.html(f"title_card_{job.index:03d}.html",
                    staged_html(title_card_html(ctx.deck, job.section, job.slide, job.index, brand=ctx.brand),
                                job.stage))
    if job.stage is not None:
        capture = ctx.capturer.animate_staged(html, ctx.clip_path(job, ".mp4"), job.seconds)
    else:
        capture = ctx.capturer.animate(html, ctx.clip_path(job, ".mp4"), job.seconds)
    source_id = job.slide.media.source_id if job.slide.media else ""
    pulses = f" {len(job.stage.pulses)} pulse(s)" if job.stage else ""
    return _result(job, "title_card", capture.clip, note=f"source_id={source_id}{pulses}",
                   credit=_news_card_credit(ctx, job, source_id))


def _news_card_credit(ctx: MediaContext, job: SlideJob, source_id: str) -> dict | None:
    """The card names a publisher and shows its headline: credit the report (publisher, headline, date, URL) so
    the licence record and the description cover it ("quoted headline, not a reprint")."""
    if not source_id:
        return None
    source = ctx.deck.source_by_id(source_id)
    return {"slide_id": job.slide.id, "slide_index": job.index, "kind": "news_card", "source_id": source.id,
            "publisher": source.publisher or "", "headline": source.headline or source.title,
            "published": source.published or "", "source_url": source.url or "",
            "license": "引用標題，非轉載全文 / headline quoted, article not reproduced"}
