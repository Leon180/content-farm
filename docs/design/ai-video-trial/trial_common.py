"""Shared helpers for the AI video trial: the 「AI 示意圖」 label, swap / RSS sampling, render gate."""

from __future__ import annotations

import re
import subprocess
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LABEL = "AI 示意圖"
FONTS = ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
         "/Library/Fonts/Arial Unicode.ttf")
_SWAP = re.compile(r"used = ([\d.]+)M")
# Processes that mean another session is rendering video; we must not generate alongside them.
RENDER_MARKERS = ("ffmpeg", "remotion", "assembly")


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise FileNotFoundError(f"no CJK font among {FONTS}")


def label_layer(width: int, height: int) -> Image.Image:
    """Transparent RGBA layer with 「AI 示意圖」 in a translucent box at the top-left (same look as ai-trial)."""
    size = max(16, height // 28)
    face = font(size)
    pad, margin = size // 2, size
    left, top, right, bottom = face.getbbox(LABEL)
    box = (margin, margin, margin + right - left + 2 * pad, margin + bottom - top + 2 * pad)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(box, radius=pad, fill=(0, 0, 0, 150))
    draw.text((margin + pad - left, margin + pad - top), LABEL, font=face, fill=(255, 255, 255, 235))
    return layer


def swap_used_mb() -> float:
    out = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, check=True).stdout
    match = _SWAP.search(out)
    if match is None:
        raise RuntimeError(f"unexpected vm.swapusage output: {out!r}")
    return float(match.group(1))


def tree_rss_kb(pid: int) -> int:
    """RSS of pid plus its direct children (pipelines often fork a worker)."""
    out = subprocess.run(["ps", "-Ao", "pid=,ppid=,rss="], capture_output=True, text=True, check=True).stdout
    total = 0
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and (int(parts[0]) == pid or int(parts[1]) == pid):
            total += int(parts[2])
    return total


class Sampler(threading.Thread):
    """Samples process-tree RSS and system swap once a second until stopped."""

    def __init__(self, pid: int) -> None:
        super().__init__(daemon=True)
        self.pid, self.peak_rss_kb, self.max_swap_mb, self.stop = pid, 0, 0.0, threading.Event()

    def run(self) -> None:
        while not self.stop.is_set():
            self.peak_rss_kb = max(self.peak_rss_kb, tree_rss_kb(self.pid))
            self.max_swap_mb = max(self.max_swap_mb, swap_used_mb())
            self.stop.wait(1.0)


def foreign_renders(own_pids: set[int]) -> list[str]:
    """Command lines of render-like processes that are not ours."""
    out = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True, check=True).stdout
    hits = []
    for line in out.splitlines():
        pid_text, _, cmd = line.strip().partition(" ")
        if not pid_text.isdigit() or int(pid_text) in own_pids:
            continue
        exe = cmd.split(" ", 1)[0].rsplit("/", 1)[-1]
        if exe in RENDER_MARKERS:
            hits.append(cmd[:160])
    return hits


def wait_until_render_idle(own_pids: set[int], poll_seconds: int = 30, max_wait_seconds: int = 3600) -> float:
    """Block while another session renders; return seconds waited. Raise if it never clears."""
    waited = 0.0
    while True:
        hits = foreign_renders(own_pids)
        if not hits:
            return waited
        if waited >= max_wait_seconds:
            raise TimeoutError(f"render still running after {waited:.0f}s: {hits[:2]}")
        print(f"[gate] waiting for foreign render: {hits[0]}", flush=True)
        time.sleep(poll_seconds)
        waited += poll_seconds
