"""Contact sheets for the synthetic audience: one frame every ``STEP`` seconds, 6 per sheet,
timestamp in the top-left corner of every cell (the format of the 2026-10-17 trial)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

STEP = 5.0
PER_SHEET = 6
COLUMNS = 3
CELL_W = 640


def _font(size: int) -> ImageFont.ImageFont:
    from content_farm.assembly.drawtext import find_cjk_font

    path = find_cjk_font()
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def mmss(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def extract_frames(video: Path, out_dir: Path, step: float = STEP) -> list[tuple[float, Path]]:
    """Frames at 0, step, 2·step … (one ffmpeg pass)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("frame_*.jpg"):
        old.unlink()
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-an",
           "-vf", f"fps=1/{step}:start_time=0:round=down,scale={CELL_W}:-2", "-q:v", "4",
           str(out_dir / "frame_%04d.jpg")]
    result = subprocess.run(cmd, capture_output=True, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(f"frame extraction failed: {result.stderr.decode(errors='replace')[-400:]}")
    frames = sorted(out_dir.glob("frame_*.jpg"))
    if not frames:
        raise RuntimeError(f"no frames extracted from {video}")
    return [(i * step, path) for i, path in enumerate(frames)]


def build_sheets(frames: list[tuple[float, Path]], out_dir: Path) -> list[Path]:
    font = _font(30)
    out_dir.mkdir(parents=True, exist_ok=True)
    sheets = []
    for n, start in enumerate(range(0, len(frames), PER_SHEET), 1):
        chunk = frames[start:start + PER_SHEET]
        first = Image.open(chunk[0][1])
        cell_w, cell_h = first.size
        rows = (len(chunk) + COLUMNS - 1) // COLUMNS
        sheet = Image.new("RGB", (cell_w * COLUMNS + 4 * (COLUMNS + 1), cell_h * rows + 4 * (rows + 1)), "#222")
        for k, (t, path) in enumerate(chunk):
            x = 4 + (k % COLUMNS) * (cell_w + 4)
            y = 4 + (k // COLUMNS) * (cell_h + 4)
            sheet.paste(Image.open(path).convert("RGB"), (x, y))
            draw = ImageDraw.Draw(sheet)
            label = mmss(t)
            box = draw.textbbox((x + 8, y + 6), label, font=font)
            draw.rectangle((box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4), fill="#000000")
            draw.text((x + 8, y + 6), label, fill="#FFE066", font=font)
        path = out_dir / f"sheet_{n:02d}.jpg"
        sheet.save(path, quality=85)
        sheets.append(path)
    return sheets
