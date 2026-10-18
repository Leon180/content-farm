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
import os
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


# Chromium re-rasters only the damaged tiles of a changed page; with the rig's
# SVG filter that made a frame's pixels depend on the frames rendered before
# it (measured: up to 69/255 on the tail after 5 prior frames). Full raster
# makes every frame a function of its own parameters.
CHROMIUM_ARGS = ("--disable-partial-raster",)


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
        browser = pw.chromium.launch(args=list(CHROMIUM_ARGS))
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
    out.parent.mkdir(parents=True, exist_ok=True)
    if len(parts) == 1:
        os.replace(parts[0], out)
        return
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


# --- Tiled GPU capture (incremental render) ---------------------------------------------------
# Profile 2026-10-18 (CoWoS v3, 150 frames): one frame per screenshot on Chromium's software
# raster = 144 ms/frame, almost all of it the rig's sticker filter (feMorphology + blur);
# GPU raster (ANGLE Metal) = 43 ms; GPU + 2x2 rig iframes per screenshot = 13.6 ms
# (decode + crop included). Composited on grey, tiled vs single capture differ in no pixel by
# more than 16/255 and in 0.0000% of pixels by more than 8 (only fully transparent RGB moves).
# A frame always lands in tile ``local index % TILES`` (chunks start on a tile boundary), so a
# scene renders to the same pixels however the work is split.
GPU_ARGS = ("--enable-gpu", "--use-angle=metal", "--enable-gpu-rasterization", "--ignore-gpu-blocklist")
GRID_ARGS = ("--disable-web-security", "--allow-file-access-from-files")  # script the rig iframes
TILE_COLS, TILE_ROWS = 2, 2
TILES = TILE_COLS * TILE_ROWS


def gpu_enabled() -> bool:
    return os.environ.get("CF_MASCOT_GPU", "1") != "0"


def render_settings() -> str:
    """Names what shapes the captured pixels (part of each scene's cache identity)."""
    return f"tiles{TILE_COLS}x{TILE_ROWS}:{'gpu' if gpu_enabled() else 'cpu'}"


def _grid_html(rig: Path) -> str:
    uri = rig.resolve().as_uri()
    cells = "".join(
        f'<iframe id="f{i}" src="{uri}" style="position:absolute;left:{(i % TILE_COLS) * CANVAS_W}px;'
        f'top:{(i // TILE_COLS) * CANVAS_H}px;width:{CANVAS_W}px;height:{CANVAS_H}px;border:0"></iframe>'
        for i in range(TILES))
    return f"<!doctype html><html><body style='margin:0;background:transparent'>{cells}</body></html>"


class RigGrid:
    """``with RigGrid() as grid: for rgba in grid.capture(frames): ...`` — one browser,
    TILES rig iframes, one screenshot per TILES frames."""

    def __init__(self, rig: Path = RIG_PATH) -> None:
        self._rig = rig
        self._stack = None
        self._page = None
        self._cdp = None

    def __enter__(self) -> RigGrid:
        from contextlib import ExitStack

        from playwright.sync_api import sync_playwright

        stack = ExitStack()
        try:
            tmp = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="rig_grid_")))
            grid = tmp / "grid.html"
            grid.write_text(_grid_html(self._rig), encoding="utf-8")
            pw = stack.enter_context(sync_playwright())
            browser = pw.chromium.launch(args=[*CHROMIUM_ARGS, *(GPU_ARGS if gpu_enabled() else ()), *GRID_ARGS])
            stack.callback(browser.close)
            page = browser.new_page(viewport={"width": CANVAS_W * TILE_COLS, "height": CANVAS_H * TILE_ROWS})
            page.goto(grid.as_uri())
            page.wait_for_function(f"[...Array({TILES}).keys()].every(i => document.getElementById('f' + i)"
                                   ".contentWindow.applyParams)")
            cdp = page.context.new_cdp_session(page)
            cdp.send("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        except BaseException:
            stack.close()
            raise
        self._stack, self._page, self._cdp = stack, page, cdp
        return self

    def __exit__(self, *exc: object) -> None:
        if self._stack is not None:
            self._stack.close()

    def capture(self, frames: Sequence[Frame]):
        """Yield one RGBA array (CANVAS_H x CANVAS_W x 4) per frame; frame i in tile i % TILES."""
        import base64
        import io

        import numpy as np
        from PIL import Image

        for lo in range(0, len(frames), TILES):
            batch = frames[lo:lo + TILES]
            self._page.evaluate(
                "(items) => items.forEach(([p, s], i) =>"
                " document.getElementById('f' + i).contentWindow.applyParams(p, s))",
                [[dict(f.params), f.say] for f in batch])
            shot = self._cdp.send("Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True})
            img = np.asarray(Image.open(io.BytesIO(base64.b64decode(shot["data"]))).convert("RGBA"))
            for i in range(len(batch)):
                x, y = (i % TILE_COLS) * CANVAS_W, (i // TILE_COLS) * CANVAS_H
                yield np.ascontiguousarray(img[y:y + CANVAS_H, x:x + CANVAS_W])


def encode_rgba(frames_rgba, fps: float, out: Path) -> int:
    """Pipe RGBA arrays into a ProRes 4444 .mov; returns the frame count."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{CANVAS_W}x{CANVAS_H}",
           "-framerate", f"{fps:g}", "-i", "-", *ALPHA_CODEC_ARGS, "-an", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    count = 0
    try:
        for rgba in frames_rgba:
            proc.stdin.write(rgba.tobytes())
            count += 1
    finally:
        proc.stdin.close()
        stderr = proc.stderr.read().decode(errors="replace")
        proc.wait()
    if proc.returncode != 0:
        raise MascotRenderError(f"ffmpeg failed for {out}: {stderr[-400:]}")
    return count


def _render_chunks(args: tuple[list[tuple[Sequence[Frame], str]], float, str]) -> int:
    """Worker: render a list of (frames, out path) chunks in one browser."""
    chunks, fps, rig = args
    with RigGrid(Path(rig)) as grid:
        return sum(encode_rgba(grid.capture(frames), fps, Path(out)) for frames, out in chunks)


def tile_chunks(count: int, size: int) -> list[tuple[int, int]]:
    """[lo, hi) chunks of ``count`` frames, each starting on a tile boundary."""
    size = max(TILES, size - size % TILES)
    return [(lo, min(count, lo + size)) for lo in range(0, count, size)]


def _lanes(pieces: Sequence[tuple[Sequence[Frame], Path, int]], workers: int) -> list[list[tuple[list, str]]]:
    """Spread chunks over ``workers`` lanes, longest first onto the least loaded lane."""
    lanes: list[list[tuple[list, str]]] = [[] for _ in range(max(1, min(workers, len(pieces))))]
    loads = [0] * len(lanes)
    for frames, part, _owner in sorted(pieces, key=lambda p: -len(p[0])):
        lane = loads.index(min(loads))
        lanes[lane].append((list(frames), str(part)))
        loads[lane] += len(frames)
    return [lane for lane in lanes if lane]


def render_scene_parts(jobs: Sequence[tuple[Sequence[Frame], Path]], fps: float, *, workers: int = 3,
                       chunk_frames: int = 400, rig: Path = RIG_PATH) -> RenderStats:
    """Render scenes (frames, out .mov) in parallel: each scene is cut into tile-aligned
    chunks, chunks are spread over ``workers`` processes, then joined per scene."""
    import shutil

    started = time.monotonic()
    if not jobs:
        return RenderStats(0, 0, 0, 0.0)
    work = jobs[0][1].parent
    work.mkdir(parents=True, exist_ok=True)
    tmp_root = Path(tempfile.mkdtemp(prefix=".parts_", dir=work))
    try:
        pieces = [(frames[lo:hi], tmp_root / f"job{j:03d}_part{c:03d}.mov", j)
                  for j, (frames, _out) in enumerate(jobs)
                  for c, (lo, hi) in enumerate(tile_chunks(len(frames), chunk_frames))]
        tasks = [(lane, fps, str(rig)) for lane in _lanes(pieces, workers)]
        if len(tasks) == 1:
            counts = [_render_chunks(tasks[0])]
        else:
            with multiprocessing.get_context("spawn").Pool(len(tasks)) as pool:
                counts = pool.map(_render_chunks, tasks)
        for j, (_frames, out) in enumerate(jobs):
            _concat([part for _f, part, owner in pieces if owner == j], out)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    stats = RenderStats(sum(counts), sum(counts), len(tasks), time.monotonic() - started)
    logger.info("mascot: %d frames in %d scene(s) with %d workers in %.1fs",
                stats.frames, len(jobs), stats.workers, stats.seconds)
    return stats
