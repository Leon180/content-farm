"""Pillow-based thumbnail renderer with optional FFmpeg keyframe extraction."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from content_farm.thumbnail.schemas import ThumbnailSettings

logger = logging.getLogger(__name__)

_DEFAULT_SETTINGS = ThumbnailSettings()

_BREAK_PUNCT = re.compile(r"[，。！？；：、\n,.!?;:]")

_COMMON_CJK_FONT_PATHS = (
    "/System/Library/Fonts/PingFang.ttc",                           # macOS
    "/System/Library/Fonts/STHeiti Medium.ttc",                     # macOS fallback
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",       # Linux
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",           # Arch
    "/usr/share/fonts/truetype/noto/NotoSansCJKtc-Regular.otf",    # Ubuntu
)


class PillowProvider:
    """Renders thumbnails using Pillow + optional FFmpeg keyframe extraction."""

    def __init__(self, ffmpeg_path: str = "ffmpeg") -> None:
        self._ffmpeg = ffmpeg_path

    async def render(
        self,
        *,
        title: str,
        output_path: Path,
        video_path: Path | None = None,
        background_image_path: Path | None = None,
        settings: ThumbnailSettings | None = None,
    ) -> int:
        """Render a 1280x720 JPEG thumbnail with text overlay."""
        s = settings or _DEFAULT_SETTINGS
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Background: stock photo > video keyframe > gradient
        if background_image_path and background_image_path.exists():
            bg = Image.open(background_image_path)
            bg = bg.resize((s.width, s.height), Image.LANCZOS)
        elif video_path and video_path.exists():
            bg = await self._extract_keyframe(video_path, s)
        else:
            bg = _create_gradient(s)

        # 2. Dark overlay for text readability
        overlay = Image.new("RGBA", bg.size, (0, 0, 0, 100))
        bg = Image.alpha_composite(bg.convert("RGBA"), overlay)

        # 3. Draw title
        draw = ImageDraw.Draw(bg)
        font = _load_font(s)
        _draw_title(draw, title, font, s)

        # 4. Save JPEG
        rgb = bg.convert("RGB")
        rgb.save(str(output_path), "JPEG", quality=s.quality, optimize=True)

        return output_path.stat().st_size

    async def _extract_keyframe(
        self, video_path: Path, s: ThumbnailSettings,
    ) -> Image.Image:
        """Extract a frame at ~25% of video duration via FFmpeg."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            # Probe duration
            ffprobe = self._ffmpeg.replace("ffmpeg", "ffprobe")
            probe_cmd = [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ]
            proc = await asyncio.create_subprocess_exec(
                *probe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            duration = 10.0
            if proc.returncode == 0:
                try:
                    duration = float(stdout.decode().strip())
                except ValueError:
                    pass
            seek_time = duration * 0.25

            # Extract frame
            extract_cmd = [
                self._ffmpeg, "-y",
                "-ss", f"{seek_time:.2f}",
                "-i", str(video_path),
                "-vframes", "1",
                "-vf", (
                    f"scale={s.width}:{s.height}"
                    f":force_original_aspect_ratio=decrease,"
                    f"pad={s.width}:{s.height}:(ow-iw)/2:(oh-ih)/2"
                ),
                str(tmp_path),
            ]
            proc = await asyncio.create_subprocess_exec(
                *extract_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                detail = stderr.decode(errors="replace")[-300:]
                logger.warning("Keyframe extraction failed, using gradient: %s", detail)
                return _create_gradient(s)

            img = Image.open(tmp_path)
            return img.copy()
        finally:
            tmp_path.unlink(missing_ok=True)


def _create_gradient(s: ThumbnailSettings) -> Image.Image:
    """Create a top-to-bottom linear gradient background."""
    base = Image.new("RGB", (s.width, s.height))
    draw = ImageDraw.Draw(base)
    top = _parse_hex(s.background_color)
    bottom = _parse_hex(s.gradient_end_color)

    for y in range(s.height):
        ratio = y / s.height
        r = int(top[0] + (bottom[0] - top[0]) * ratio)
        g = int(top[1] + (bottom[1] - top[1]) * ratio)
        b = int(top[2] + (bottom[2] - top[2]) * ratio)
        draw.line([(0, y), (s.width, y)], fill=(r, g, b))

    return base


def _load_font(
    s: ThumbnailSettings,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load font: settings path → env var → system CJK → Pillow default."""
    font_path = s.font_path or os.environ.get("CF_THUMBNAIL_FONT_PATH", "")

    if font_path and Path(font_path).exists():
        try:
            return ImageFont.truetype(font_path, s.font_size)
        except OSError:
            logger.warning("Failed to load font at %s, using fallback", font_path)

    for candidate in _COMMON_CJK_FONT_PATHS:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, s.font_size)
            except OSError:
                continue

    logger.warning("No CJK font found; falling back to Pillow default")
    return ImageFont.load_default()


def _draw_title(
    draw: ImageDraw.Draw,
    title: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    s: ThumbnailSettings,
) -> None:
    """Draw wrapped, stroked title text centered on the image."""
    lines = _wrap_text(title, s.max_title_chars)
    line_height = s.font_size + 10

    total_text_height = line_height * len(lines)
    y_start = (s.height - total_text_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (s.width - text_width) // 2
        y = y_start + i * line_height

        draw.text(
            (x, y), line, font=font,
            fill=s.text_color,
            stroke_width=s.stroke_width,
            stroke_fill=s.stroke_color,
        )


def _wrap_text(text: str, max_chars: int) -> list[str]:
    """Wrap text for thumbnail display, preferring punctuation breaks."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    lines: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            stripped = remaining.strip()
            if stripped:
                lines.append(stripped)
            break

        best_break = max_chars
        half = max_chars // 2

        for pos in range(max_chars, half, -1):
            if pos < len(remaining) and _BREAK_PUNCT.match(remaining[pos]):
                best_break = pos + 1
                break

        chunk = remaining[:best_break].strip()
        remaining = remaining[best_break:].strip()
        if chunk:
            lines.append(chunk)

    return lines


def _parse_hex(hex_color: str) -> tuple[int, int, int]:
    """Parse '#RRGGBB' to (r, g, b) tuple."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
