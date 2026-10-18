"""Scene identities for the media step and the cached build of one slot.

identity(job) = slide (texts, layout, media, mascot, sentence ids excluded), its section
title, page number / page count (both printed on the frame), deck-level fields the
frame shows, brand, slot length, the narration stage plan (when each part appears),
the external files the builder reads, and the source of the explainer renderer.

A slot's final clip also depends on the next slot (the transition blends into its
first frame), so the final is keyed by (this identity, next identity, transition).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Sequence
from dataclasses import asdict, replace
from pathlib import Path

from content_farm.explainer import ffmpeg_ops
from content_farm.explainer.ai_images import AI_IMAGE_DIR
from content_farm.explainer.artwork import ARTWORK_DIR
from content_farm.explainer.deck import Deck, MediaKind
from content_farm.explainer.media import ClipResult, MediaContext, SlideJob, build_clip
from content_farm.explainer.scene_cache import SceneCache, code_digest, digest, file_digest, files_digest

logger = logging.getLogger(__name__)

MEDIA_CACHE_VERSION = 1
EXPLAINER_DIR = Path(__file__).parent
# The mascot / PNGtuber hosts are drawn by their own step; editing them must not redo media.
_CODE_SKIP = ("mascot/", "pngtuber/", "media_cache.py", "scene_cache.py", "sentence_ids.py", "fix_scope.py")


def renderer_digest() -> str:
    return code_digest(EXPLAINER_DIR, skip=_CODE_SKIP)


def _deck_frame_fields(deck: Deck) -> dict:
    return {"title": deck.title, "category": deck.category.value, "as_of": deck.as_of,
            "draft_data": deck.draft_data, "sources": [s.model_dump(mode="json") for s in deck.sources]}


def _external_files(run_dir: Path, job: SlideJob) -> dict:
    """Files outside deck.json the builder reads for this slide."""
    slide_id = job.slide.id
    kind = job.slide.media_kind
    files: dict[str, object] = {}
    if kind == MediaKind.SLIDE:
        files["slide_png"] = file_digest(run_dir / "slides" / f"slide_{job.index:03d}.png")
    if kind == MediaKind.AI_IMAGE:
        files["ai_images"] = files_digest((run_dir / AI_IMAGE_DIR).glob(f"{slide_id}*"))
        files["ai_motion"] = files_digest((run_dir / "assets" / "ai_motion").glob(f"*{slide_id}*"))
    if kind == MediaKind.ARTWORK:
        files["artwork"] = files_digest((run_dir / ARTWORK_DIR).glob("*"))
    return files


def job_identity(deck: Deck, job: SlideJob, *, run_dir: Path, brand: str | None, static_png_ok: bool,
                 motion: object, code: str) -> str:
    slide = job.slide.model_dump(mode="json", exclude={"sentence_ids", "notes"})
    page_html = hashlib.sha256(job.animated_page.html.encode("utf-8")).hexdigest()[:20]
    return digest({
        "v": MEDIA_CACHE_VERSION, "code": code, "slide": slide, "section": job.section.title,
        "index": job.index, "total": len(deck.slides), "deck": _deck_frame_fields(deck),
        "brand": brand, "seconds": round(job.seconds, 3), "static_png_ok": static_png_ok,
        "stage": asdict(job.stage) if job.stage else None, "page_html": page_html,
        "motion": repr(motion), "files": _external_files(run_dir, job),
    })


def final_identity(key: str, next_key: str | None, transition: str, seconds: float) -> str:
    return digest({"v": MEDIA_CACHE_VERSION, "clip": key, "next": next_key, "transition": transition,
                   "seconds": round(seconds, 3)})


def _result_meta(result: ClipResult) -> dict:
    return {**{k: v for k, v in asdict(result).items() if k != "path"},
            "suffix": result.path.suffix, "problems": list(result.problems)}


def _from_meta(meta: dict, path: Path, job: SlideJob) -> ClipResult:
    fields = {k: v for k, v in meta.items() if k not in ("suffix", "files", "identity")}
    # index / seconds come from this run's job (a moved slide keeps its clip only when the
    # page number is not part of the frame; it is, so in practice the key moves with it).
    return replace(ClipResult(**{**fields, "path": path, "problems": tuple(meta.get("problems", ()))}),
                   index=job.index, seconds=job.seconds, build_seconds=0.0)


def cached_build(ctx: MediaContext, job: SlideJob, cache: SceneCache, key: str) -> tuple[ClipResult, bool]:
    """(result, reused): the stored clip for ``key``, else build it and store it."""
    meta = cache.get(key)
    if meta is not None:
        name = f"clip{meta['suffix']}"
        return _from_meta(meta, cache.path(key, name), job), True
    result = build_clip(ctx, job)
    name = f"clip{result.path.suffix}"
    # Plain slides with transitions off point at slides/slide_NNN.png: copy, never move it.
    move = result.path.is_relative_to(ctx.work_dir)
    cache.put(key, {name: result.path}, {**_result_meta(result), "identity": key}, move=move)
    return replace(result, path=cache.path(key, name)), False


def cached_transitions(results: Sequence[ClipResult], keys: Sequence[str], work_dir: Path,
                       cache: SceneCache, *, style: str, length: float) -> tuple[list[Path], list[str]]:
    """Final file per slot (blend into the next slot's first frame), reused per (clip, next) pair."""
    if style == "none" or len(results) < 2:
        return [r.path for r in results], list(keys)
    finals: list[Path] = []
    final_keys: list[str] = []
    for i, result in enumerate(results):
        if i == len(results) - 1:
            finals.append(result.path)
            final_keys.append(keys[i])
            continue
        fkey = final_identity(keys[i], keys[i + 1], f"{style}:{length}", result.seconds)
        final_keys.append(fkey)
        if cache.get(fkey) is None:
            head = ffmpeg_ops.first_frame(results[i + 1].path, work_dir / "heads" / f"head_{i + 2:03d}.png")
            tmp = ffmpeg_ops.transition_into(result.path, head, work_dir / "final" / f"clip_{result.index:03d}.mp4",
                                             result.seconds, style=style, length=length)
            cache.put(fkey, {"final.mp4": tmp}, {"identity": fkey}, move=True)
        finals.append(cache.path(fkey, "final.mp4"))
    return finals, final_keys


def cached_frame(cache: SceneCache, key: str, make) -> Path:
    """Contact-sheet frame for a clip, stored beside it."""
    path = cache.path(key, "sheet_frame.png")
    if path.is_file():
        return path
    tmp = make(cache.entry(key) / ".sheet_frame.tmp.png")
    tmp.replace(path)
    return path


GENERATIONS = 3
TIMING_FILE = "narration_timing.json"


def stable_narration(run_dir: Path, work_dir: Path, deck: Deck,
                     narration: dict[str, list[tuple[float, str]]] | None) -> dict[str, list[tuple[float, str]]] | None:
    """Per-slide sentence timings, kept from the last run while the slide's audio and narration
    are unchanged. The aligned SRT is absolute: when an earlier scene's length changes, ms
    rounding moves later scenes' sentence offsets by 0.01 s and their stage plans (hence their
    identities) would change for nothing (CoWoS run (a), 2026-10-18: 4 untouched slides redrawn)."""
    if narration is None:
        return None
    path = work_dir / TIMING_FILE
    try:
        stored = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except json.JSONDecodeError:
        stored = {}
    out: dict[str, list[tuple[float, str]]] = {}
    for index, slide in enumerate(deck.slides, start=1):
        key = digest({"audio": file_digest(run_dir / "audio" / f"scene_{index:03d}.mp3"), "text": slide.narration})
        previous = stored.get(slide.id)
        if previous and previous.get("key") == key:
            out[slide.id] = [(float(t), str(text)) for t, text in previous["timing"]]
        else:
            out[slide.id] = list(narration.get(slide.id, []))
            stored[slide.id] = {"key": key, "timing": out[slide.id]}
    work_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stored, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def remember_generation(work_dir: Path, keys: Sequence[str], cache: SceneCache) -> list[str]:
    """Keep the pieces of the last GENERATIONS runs (so an undo is free); drop older ones."""
    log = work_dir / "cache_generations.json"
    try:
        history = json.loads(log.read_text(encoding="utf-8")) if log.is_file() else []
    except json.JSONDecodeError:
        history = []
    history = [*history, sorted(set(keys))][-GENERATIONS:]
    log.write_text(json.dumps(history), encoding="utf-8")
    return cache.prune({k for generation in history for k in generation})
