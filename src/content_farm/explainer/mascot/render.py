"""Capture the rig frame by frame with Playwright and encode an alpha video.

Deterministic by construction: the page has no animations or timers, each
frame is ``applyParams(frame_i)`` then a screenshot, and frame ``i``'s params
were computed ahead of time from ``t = i / fps``. Frames are split into
contiguous chunks across worker processes (one headless Chromium each); each
worker pipes PNGs into its own ffmpeg, and the chunks are concatenated.
"""

from __future__ import annotations

import logging
import multiprocessing
import subprocess
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from content_farm.explainer.mascot.motion import Frame

logger = logging.getLogger(__name__)

RIG_PATH = Path(__file__).parent / "assets" / "rig.html"
CANVAS_W, CANVAS_H = 620, 540

# ProRes 4444 keeps alpha and is readable by ffmpeg and every NLE.
ALPHA_CODEC_ARGS = ("-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
                    "-vendor", "apl0")


class MascotRenderError(RuntimeError):
    """Capture or encode failed."""


@dataclass(frozen=True)
class RenderStats:
    frames: int
    unique_frames: int
    workers: int
    seconds: float


def capture_pngs(frames: Sequence[Frame], rig: Path = RIG_PATH):
    """Yield one PNG (bytes) per frame; consecutive identical frames are reused."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": CANVAS_W, "height": CANVAS_H})
            page.goto(rig.resolve().as_uri())
            last_key, last_png = None, b""
            for frame in frames:
                key = (tuple(frame.params.values()), frame.say)
                if key != last_key:
                    page.evaluate("([p, s]) => window.applyParams(p, s)", [dict(frame.params), frame.say])
                    last_png = page.screenshot(omit_background=True, type="png")
                    last_key = key
                yield last_png
        finally:
            browser.close()


def _encode_chunk(args: tuple[Sequence[Frame], float, str, str]) -> int:
    """Worker: capture ``frames`` and encode them to ``out`` (alpha .mov)."""
    frames, fps, out, rig = args
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", f"{fps:g}",
           "-c:v", "png", "-i", "-", *ALPHA_CODEC_ARGS, "-an", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    unique, previous = 0, None
    try:
        for png in capture_pngs(frames, Path(rig)):
            unique += png is not previous
            previous = png
            proc.stdin.write(png)
    finally:
        proc.stdin.close()
        stderr = proc.stderr.read().decode(errors="replace")
        proc.wait()
    if proc.returncode != 0:
        raise MascotRenderError(f"ffmpeg failed for {out}: {stderr[-400:]}")
    return unique


def split_chunks(n: int, workers: int) -> list[tuple[int, int]]:
    """Contiguous [lo, hi) ranges covering 0..n, at most ``workers`` of them."""
    workers = max(1, min(workers, n))
    size, extra = divmod(n, workers)
    bounds, lo = [], 0
    for w in range(workers):
        hi = lo + size + (1 if w < extra else 0)
        bounds.append((lo, hi))
        lo = hi
    return bounds


def render_alpha_video(
    frames: Sequence[Frame], fps: float, out: Path, *, workers: int = 4, rig: Path = RIG_PATH,
) -> RenderStats:
    """Render ``frames`` to ``out`` (ProRes 4444 .mov with alpha)."""
    if not frames:
        raise MascotRenderError("no frames to render")
    started = time.monotonic()
    out.parent.mkdir(parents=True, exist_ok=True)
    chunks = split_chunks(len(frames), workers)
    with tempfile.TemporaryDirectory(prefix="mascot_", dir=out.parent) as tmp:
        parts = [Path(tmp) / f"part_{i:03d}.mov" for i in range(len(chunks))]
        jobs = [(list(frames[lo:hi]), fps, str(p), str(rig)) for (lo, hi), p in zip(chunks, parts)]
        if len(jobs) == 1:
            uniques = [_encode_chunk(jobs[0])]
        else:
            with multiprocessing.get_context("spawn").Pool(len(jobs)) as pool:
                uniques = pool.map(_encode_chunk, jobs)
        _concat(parts, out)
    stats = RenderStats(len(frames), sum(uniques), len(chunks), time.monotonic() - started)
    logger.info("mascot: %d frames (%d unique) with %d workers in %.1fs",
                stats.frames, stats.unique_frames, stats.workers, stats.seconds)
    return stats


def _concat(parts: Sequence[Path], out: Path) -> None:
    listing = out.parent / f".{out.stem}_parts.txt"
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    try:
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-c", "copy", str(out)],
            capture_output=True, text=True, timeout=600,
        )
    finally:
        listing.unlink(missing_ok=True)
    if result.returncode != 0:
        raise MascotRenderError(f"concat failed: {result.stderr[-400:]}")


def render_still(frame: Frame, out: Path, rig: Path = RIG_PATH) -> Path:
    """One frame to a transparent PNG (previews, docs, tests)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(list(capture_pngs([frame], rig))[0])
    return out
