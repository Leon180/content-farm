"""Two thumbnail options + a suggested cover frame for a news Short (thumbnail-v2 rules).

Usage:
    python scripts/news_thumb.py --run-dir output/technews-… --hook-a "AI 沒賺到錢？" --beat-a 1 \
        --hook-b "七巨頭獨賺" --beat-b 2 [--out-dir DIR]

Rules applied (REPORT-thumbnail-v2): one main subject filling most of the frame (the beat's AI picture, top 62 %),
4–8 character hook set big on a solid panel below (never the title), a 168-px-wide preview check of the letter height.
Writes ``thumbnails/option_a.jpg``, ``option_b.jpg`` (1080×1920, < 2 MB), ``…_tiny.png`` previews and
``thumbnails/cover_frame.json`` (the second of the video that makes the best Shorts cover). Pictures are the Short's own
beat pictures; nothing new is generated.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from content_farm.assembly.drawtext import find_cjk_font  # noqa: E402
from content_farm.explainer.ai_images import AI_IMAGE_DIR, find_image  # noqa: E402

W, H = 1080, 1920
PIC_H = 1190
PANEL = (16, 36, 44)          # deep teal-black
HOOK = (255, 236, 179)        # warm amber-cream
ACCENT = (245, 166, 35)
TINY_W = 168
MAX_BYTES = 2_000_000


def cover_picture(image: Path) -> Image.Image:
    with Image.open(image) as src:
        pic = src.convert("RGB")
    scale = max(W / pic.width, PIC_H / pic.height)
    pic = pic.resize((round(pic.width * scale), round(pic.height * scale)), Image.LANCZOS)
    left, top = (pic.width - W) // 2, (pic.height - PIC_H) // 2
    return pic.crop((left, top, left + W, top + PIC_H))


def _fit_font(draw: ImageDraw.ImageDraw, text: str, font_path: str, max_w: int, start: int) -> ImageFont.FreeTypeFont:
    size = start
    while size > 40:
        font = ImageFont.truetype(font_path, size)
        if draw.textlength(text, font=font) <= max_w:
            return font
        size -= 4
    return ImageFont.truetype(font_path, 40)


def render_option(image: Path, hook: str, out: Path) -> dict:
    if not 4 <= len(hook.replace(" ", "")) <= 8:
        raise ValueError(f"hook {hook!r}: 4–8 characters please (thumbnail-v2 rule)")
    font_path = find_cjk_font()
    if font_path is None:
        raise RuntimeError("no CJK font found")
    canvas = Image.new("RGB", (W, H), PANEL)
    canvas.paste(cover_picture(image), (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, PIC_H, W, PIC_H + 10), fill=ACCENT)
    font = _fit_font(draw, hook, font_path, W - 120, 230)
    box = draw.textbbox((0, 0), hook, font=font)
    x, y = (W - (box[2] - box[0])) // 2 - box[0], PIC_H + 10 + (H - PIC_H - 10 - (box[3] - box[1])) // 2 - box[1]
    draw.text((x + 6, y + 6), hook, font=font, fill=(0, 0, 0))
    draw.text((x, y), hook, font=font, fill=HOOK)
    for quality in (92, 88, 84, 80, 74):
        canvas.save(out, "JPEG", quality=quality, optimize=True)
        if out.stat().st_size <= MAX_BYTES:
            break
    tiny = canvas.resize((TINY_W, round(H * TINY_W / W)), Image.LANCZOS)
    tiny.save(out.with_name(out.stem + "_tiny.png"))
    return {"hook": hook, "picture": image.name, "font_px": font.size, "letter_px_at_168": round(font.size * TINY_W / W, 1),
            "bytes": out.stat().st_size}


def cover_frame(run_dir: Path, beat: int) -> dict:
    """The Short's cover is a frame of the video: pick a moment in ``beat`` after its picture has settled."""
    script = json.loads((run_dir / "script.json").read_text(encoding="utf-8"))
    starts, clock = [], 0.0
    for scene in script["scenes"]:
        starts.append(clock)
        clock += scene["duration_seconds"]
    second = round(starts[beat - 1] + min(2.0, script["scenes"][beat - 1]["duration_seconds"] / 2), 1)
    return {"beat": beat, "second": second,
            "why": "the beat's picture is fully on screen, headline and number settled, subtitles not yet covering it"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--hook-a", required=True)
    parser.add_argument("--beat-a", type=int, default=1)
    parser.add_argument("--hook-b", required=True)
    parser.add_argument("--beat-b", type=int, default=2)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)
    out_dir = args.out_dir or args.run_dir / "thumbnails"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for key, hook, beat in (("a", args.hook_a, args.beat_a), ("b", args.hook_b, args.beat_b)):
        image = find_image(args.run_dir / AI_IMAGE_DIR, f"beat{beat}")
        if image is None:
            raise SystemExit(f"no picture for beat{beat} in {args.run_dir / AI_IMAGE_DIR}")
        result[key] = render_option(image, hook, out_dir / f"option_{key}.jpg")
    result["cover_frame"] = cover_frame(args.run_dir, args.beat_a)
    (out_dir / "cover_frame.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
