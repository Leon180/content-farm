"""不奇而寓 banner v2: picture-book side panels on cream paper, clean paper in the safe area, brown title (no card)."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from compose import BANNER, KIT, RAW, SAFE_H, SAFE_W, font, safe_preview

INK, SOFT, FAINT = (74, 47, 28), (112, 78, 50), (150, 112, 78)
PAPER = (252, 249, 238)
TAGLINE = "先聽一個故事，再告訴你它在講什麼"
SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"


def songti(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(SONGTI, size, index=2)  # Songti TC Bold (the SC faces lack traditional glyphs)


def panel(name: str, side: str) -> tuple[Image.Image, Image.Image]:
    img = Image.open(RAW / f"fbv2_{name}.png").convert("RGB")
    scale = BANNER[1] / img.height
    img = img.resize((round(img.width * scale), BANNER[1]), Image.LANCZOS)
    ramp = np.linspace(0.0, 1.0, img.width)
    alpha = np.clip((0.62 - ramp) / 0.30, 0.0, 1.0) if side == "L" else np.clip((ramp - 0.38) / 0.30, 0.0, 1.0)
    mask = Image.fromarray((np.tile(alpha, (img.height, 1)) * 255).astype("uint8"))
    return img, mask


def rough_text(canvas: Image.Image, xy: tuple[int, int], text: str, face: ImageFont.FreeTypeFont, color, seed: int) -> None:
    """Ink-like edge: blur the glyph mask, add low-frequency noise, threshold."""
    layer = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(layer).text(xy, text, font=face, fill=255, anchor="mm")
    blurred = np.asarray(layer.filter(ImageFilter.GaussianBlur(2.2)), dtype=float)
    noise = np.random.default_rng(seed).normal(0, 1, canvas.size[::-1])
    noise = np.asarray(Image.fromarray(((noise - noise.min()) / np.ptp(noise) * 255).astype("uint8"))
                       .filter(ImageFilter.GaussianBlur(3)), dtype=float)
    ink = np.clip((blurred + (noise - noise.mean()) * 1.4 - 120) * 6, 0, 255).astype("uint8")
    canvas.paste(Image.new("RGB", canvas.size, color), (0, 0), Image.fromarray(ink))


def wavy_line(draw: ImageDraw.ImageDraw, cx: int, y: int, half: int) -> None:
    points = [(cx - half + i * 8, y + 5 * np.sin(i / 3.0)) for i in range(int(half * 2 / 8) + 1)]
    draw.line(points, fill=FAINT, width=5, joint="curve")


def banner_v2(option: int) -> Image.Image:
    img = Image.new("RGB", BANNER, PAPER)
    left, left_mask = panel(f"{option}L", "L")
    right, right_mask = panel(f"{option}R", "R")
    img.paste(left, (0, 0), left_mask)
    img.paste(right, (BANNER[0] - right.width, 0), right_mask)
    cx, cy = BANNER[0] // 2, BANNER[1] // 2
    top = cy - SAFE_H // 2
    rough_text(img, (cx, top + 100), "不奇而寓", songti(170), INK, option)
    wavy_line(ImageDraw.Draw(img), cx, top + 218, 150)
    ImageDraw.Draw(img).text((cx, top + 288), TAGLINE, font=songti(58), fill=SOFT, anchor="mm")
    ImageDraw.Draw(img).text((cx, top + 378), "每週 ＿＿ 、＿＿ 更新", font=font("Medium", 36), fill=FAINT, anchor="mm")
    return img


def main() -> None:
    results = []
    for option in (1, 2, 3):
        plain = banner_v2(option)
        plain.save(KIT / f"fable-banner-v2-{option}.png")
        preview = safe_preview(plain.convert("RGBA")).convert("RGB")
        preview.save(KIT / f"fable-banner-v2-{option}-safe.png")
        results.append((plain, preview))
    sheet = Image.new("RGB", (2000, 1500), (245, 245, 247))
    draw = ImageDraw.Draw(sheet)
    draw.text((50, 30), "不奇而寓　橫幅 v2 候選", font=font("Black", 64), fill=(20, 20, 24))
    draw.text((50, 120), "寓言影片同模型同畫風前綴；中央安全區是乾淨紙色、無資訊框。右欄＝手機只看到的中央裁切。",
              font=font("Medium", 30), fill=(90, 90, 100))
    for index, (plain, preview) in enumerate(results):
        y0 = 190 + index * 430
        draw.text((50, y0), f"選項 {index + 1}", font=font("Bold", 40), fill=(20, 20, 24))
        sheet.paste(plain.resize((640, 360), Image.LANCZOS), (50, y0 + 50))
        sheet.paste(preview.resize((640, 360), Image.LANCZOS), (730, y0 + 50))
        crop = plain.crop(((BANNER[0] - SAFE_W) // 2, (BANNER[1] - SAFE_H) // 2,
                           (BANNER[0] + SAFE_W) // 2, (BANNER[1] + SAFE_H) // 2))
        sheet.paste(crop.resize((530, 145), Image.LANCZOS), (1420, y0 + 50))
        draw.text((1420, y0 + 215), "手機只看得到這一塊", font=font("Medium", 28), fill=(90, 90, 100))
    sheet.save(KIT / "fable-banner-v2-sheet.png")


if __name__ == "__main__":
    main()
