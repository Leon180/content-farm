"""Where the cat sits on a 1920x1080 explainer frame, and the ffmpeg overlay.

Frame budget (see ``templates/base.css``): meta row at x 120–1520, y 832–872;
burned subtitles bottom-centre (52 pt, ≤ 24 chars ≈ 1250 px wide, MarginV 80)
→ x ≈ 335–1585, y ≥ 880. The 620x540 rig canvas is pinned to the bottom-right
corner, so the cat's own pixels stay at x ≥ 1600 below y 880 and never reach
the meta row; only the transparent part of the canvas overlaps those zones.
``FORBIDDEN`` is what tests check the rendered alpha against.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from content_farm.explainer.mascot.render import CANVAS_H, CANVAS_W

FRAME_W, FRAME_H = 1920, 1080
# 2026-10-18 (CoWoS v3, 8:30): medium 79.7 s vs veryfast 52.2 s at crf 18, SSIM 0.9987 against the
# medium encode and a smaller file; decode + overlay alone is 23.5 s. YouTube re-encodes anyway.
OVERLAY_PRESET = "veryfast"


@dataclass(frozen=True)
class Rect:
    x0: int
    y0: int
    x1: int
    y1: int

    def to_canvas(self, origin: tuple[int, int]) -> Rect:
        ox, oy = origin
        return Rect(self.x0 - ox, self.y0 - oy, self.x1 - ox, self.y1 - oy)

    def clip(self, w: int, h: int) -> Rect | None:
        r = Rect(max(0, self.x0), max(0, self.y0), min(w, self.x1), min(h, self.y1))
        return r if r.x0 < r.x1 and r.y0 < r.y1 else None


META_ROW = Rect(120, 832, 1520, 872)
SUBTITLES = Rect(320, 880, 1600, 1080)
FORBIDDEN: dict[str, Rect] = {"meta": META_ROW, "subtitles": SUBTITLES}

# Canvas top-left on the frame: flush with the bottom-right corner.
ORIGIN = (FRAME_W - CANVAS_W, FRAME_H - CANVAS_H)


def overlay_command(
    draft: Path, alpha_video: Path, out: Path, *, crf: int = 18, duration: float | None = None,
    origin: tuple[int, int] = ORIGIN,
) -> list[str]:
    """ffmpeg args: draft + alpha mascot → out. Audio is copied untouched."""
    x, y = origin
    trim = ["-t", f"{duration:.3f}"] if duration else []
    graph = f"[0:v][1:v]overlay={x}:{y}:eof_action=pass:format=auto,format=yuv420p[v]"
    return [
        "ffmpeg", "-v", "error", "-y", "-i", str(draft), "-i", str(alpha_video),
        "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", OVERLAY_PRESET, "-crf", str(crf),
        "-c:a", "copy", *trim, "-movflags", "+faststart", str(out),
    ]


def overlay(
    draft: Path, alpha_video: Path, out: Path, *, crf: int = 18, duration: float | None = None,
    origin: tuple[int, int] = ORIGIN,
) -> Path:
    result = subprocess.run(overlay_command(draft, alpha_video, out, crf=crf, duration=duration, origin=origin),
                            capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(f"overlay failed: {result.stderr[-400:]}")
    return out
