"""One headless Chromium for every v2 media page: stills, transparent overlays, animations.

Animations are captured frame by frame at fixed time steps: for frame ``i``
the page is told ``__anim.seek(i / fps)`` and then screenshotted. Wall-clock
speed never matters, so a slow machine produces the same video as a fast one.
Only the animated part is captured; ffmpeg holds the final frame to the end.
"""

from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from content_farm.explainer import ffmpeg_ops
from content_farm.explainer.render import _LAYOUT_CHECK_JS, HEIGHT, SAFE_TOP, WIDTH


@dataclass(frozen=True)
class AnimationCapture:
    clip: Path
    animation_seconds: float
    frames_captured: int
    problems: tuple[str, ...]  # layout problems in the final frame (overflow etc.)


class PageCapturer:
    """``with PageCapturer() as cap: cap.animate(html, out, seconds)``."""

    def __init__(self, fps: int = ffmpeg_ops.FPS) -> None:
        self._fps = fps
        self._pw = None
        self._browser = None
        self._page = None

    def __enter__(self) -> PageCapturer:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._page = self._browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()

    def _open(self, html_path: Path) -> object:
        page = self._page
        if page is None:
            raise RuntimeError("PageCapturer used outside its with-block")
        page.goto(html_path.resolve().as_uri(), wait_until="load")
        page.evaluate("document.fonts.ready.then(() => true)")
        return page

    def still(self, html_path: Path, png_path: Path, *, transparent: bool = False) -> Path:
        page = self._open(html_path)
        if page.evaluate("typeof window.__anim !== 'undefined'"):
            page.evaluate("window.__anim.seek(1e6)")  # final state
        png_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(png_path), omit_background=transparent)
        return png_path

    def animate(self, html_path: Path, out_clip: Path, clip_seconds: float) -> AnimationCapture:
        """Capture the page's ``__anim`` at fixed steps, hold the last frame to ``clip_seconds``."""
        page = self._open(html_path)
        if not page.evaluate("typeof window.__anim !== 'undefined'"):
            raise RuntimeError(f"{html_path.name} has no animation runtime")
        anim_seconds = float(page.evaluate("window.__anim.duration"))
        # capture through the end of the animation (plus one settled frame), never past the clip
        frames = min(
            math.ceil(anim_seconds * self._fps) + 1,
            ffmpeg_ops.frame_count(clip_seconds, self._fps),
        )
        with tempfile.TemporaryDirectory(prefix="anim_") as tmp:
            for i in range(frames):
                page.evaluate(f"window.__anim.seek({i / self._fps:.6f})")
                page.screenshot(path=str(Path(tmp) / f"frame_{i:05d}.png"))
            page.evaluate("window.__anim.seek(1e6)")
            has_content = page.evaluate("!!document.querySelector('.content')")
            problems = (
                page.evaluate(_LAYOUT_CHECK_JS, [SAFE_TOP, WIDTH, HEIGHT]) if has_content else []
            )
            ffmpeg_ops.frames_to_clip(str(Path(tmp) / "frame_%05d.png"), out_clip, clip_seconds)
        return AnimationCapture(
            clip=out_clip,
            animation_seconds=anim_seconds,
            frames_captured=frames,
            problems=tuple(problems),
        )
