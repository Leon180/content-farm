"""Compose the yokai launch kit: text-free ink banners, ink avatars (fox / seal), kyubi thumbnails, and sheets.

Run from the repo root: python artifacts/yokai-launch/src/compose_yokai.py [banner|avatar|thumb ...]   (PIL + numpy only)
Fonts: Noto Sans CJK TC (SIL OFL) from ~/Library/Fonts; Xingkai TC / Libian TC are macOS system fonts (rendered into
pixels only, never redistributed as font files).
"""
import glob
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, "artifacts/brand-kit/src")
from compose import BANNER, SAFE_H, SAFE_W, circle_preview, cover, font, safe_preview  # noqa: E402

OUT = Path("artifacts/yokai-launch")
RAW = OUT / "raw"
KIT = Path("artifacts/brand-kit")
PAPER = (238, 231, 216)
VERMILION = (196, 48, 32)
INK = (24, 22, 20)
ASSETS = "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/*/AssetData/"


def system_font(name: str, index: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(glob.glob(ASSETS + name)[0], size, index=index)


def xingkai(size: int) -> ImageFont.FreeTypeFont:
    return system_font("Xingkai.ttc", 1, size)  # Xingkai TC Bold


def libian(size: int) -> ImageFont.FreeTypeFont:
    return system_font("Libian.ttc", 1, size)  # Libian TC


def grain(img: Image.Image, amount: float, seed: int) -> Image.Image:
    noise = np.random.default_rng(seed).normal(0, amount, (img.height, img.width, 1))
    return Image.fromarray(np.clip(np.asarray(img, dtype=float) + noise, 0, 255).astype("uint8"))


# ---------- banners (no text at all) ----------

# subject centre in the 1664x928 source and the zoom that fits it into the 1546x423 safe band (source px -> canvas px)
FRAMING = {1: ((1050, 585), 0.80), 2: ((832, 550), 0.86), 3: ((760, 595), 0.84),
           "2b1": ((900, 400), 0.74), "2b2": ((880, 410), 0.74)}


def smoothstep(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, 0.0, 1.0)
    return clipped * clipped * (3 - 2 * clipped)


def banner(option: int | str, source: str | None = None) -> Image.Image:
    """Place the generated painting so its subject sits in the centre band, fading the edges into plain paper."""
    art = Image.open(RAW / f"{source or f'ykc{option}'}.png").convert("RGB")
    (ax, ay), zoom = FRAMING[option]
    paper = tuple(int(v) for v in np.median(np.asarray(art)[:60].reshape(-1, 3), axis=0))
    size = (round(art.width * zoom), round(art.height * zoom))
    scaled = art.resize(size, Image.LANCZOS)
    feather = 150
    ys, xs = np.mgrid[0:size[1], 0:size[0]]
    edge = np.minimum.reduce([xs, ys, size[0] - 1 - xs, size[1] - 1 - ys])
    alpha = Image.fromarray((smoothstep(edge / feather) * 255).astype("uint8"))
    canvas = Image.new("RGB", (1664, 928), paper)
    canvas.paste(scaled, (round(832 - ax * zoom), round(464 - ay * zoom)), alpha)
    return grain(canvas.resize(BANNER, Image.LANCZOS), 2.2, len(str(option)) + 7)


def mobile_crop(img: Image.Image) -> Image.Image:
    return img.crop(((BANNER[0] - SAFE_W) // 2, (BANNER[1] - SAFE_H) // 2,
                     (BANNER[0] + SAFE_W) // 2, (BANNER[1] + SAFE_H) // 2))


def build_banners() -> None:
    rows = []
    for option in (1, 2, 3):
        plain = banner(option)
        plain.save(OUT / f"yokai-banner-v2-{option}.png")
        preview = safe_preview(plain.convert("RGBA")).convert("RGB")
        preview.save(OUT / f"yokai-banner-v2-{option}-safe.png")
        rows.append((plain, preview))
    sheet = Image.new("RGB", (2000, 1500), (245, 245, 247))
    draw = ImageDraw.Draw(sheet)
    draw.text((50, 30), "妖怪溯源所　封面 v2 候選", font=font("Black", 64), fill=(20, 20, 24))
    draw.text((50, 120), "九尾狐影片同模型同畫風前綴；純水墨背景、不放任何文字（Leon 2026-10-25）。右欄＝手機只看到的中央裁切。",
              font=font("Medium", 30), fill=(90, 90, 100))
    for index, (plain, preview) in enumerate(rows):
        y0 = 190 + index * 430
        draw.text((50, y0), f"選項 {index + 1}", font=font("Bold", 40), fill=(20, 20, 24))
        sheet.paste(plain.resize((640, 360), Image.LANCZOS), (50, y0 + 50))
        sheet.paste(preview.resize((640, 360), Image.LANCZOS), (730, y0 + 50))
        sheet.paste(mobile_crop(plain).resize((530, 145), Image.LANCZOS), (1420, y0 + 50))
        draw.text((1420, y0 + 215), "手機只看得到這一塊", font=font("Medium", 28), fill=(90, 90, 100))
    sheet.save(OUT / "yokai-banner-v2-sheet.png")


def build_banner_2b() -> None:
    """Leon picked option 2 (2026-10-25): regenerated with a clearly nine-tailed fox; best two seeds."""
    picks = [("2b1", "ykc2b4"), ("2b2", "ykc2b1")]
    rows = []
    for index, (key, source) in enumerate(picks, start=1):
        plain = banner(key, source)
        plain.save(OUT / f"yokai-banner-v2-2b-{index}.png")
        preview = safe_preview(plain.convert("RGBA")).convert("RGB")
        preview.save(OUT / f"yokai-banner-v2-2b-{index}-safe.png")
        rows.append((plain, preview))
    sheet = Image.new("RGB", (2000, 1070), (245, 245, 247))
    draw = ImageDraw.Draw(sheet)
    draw.text((50, 30), "妖怪溯源所　封面 選項 2 重生（九尾狐）", font=font("Black", 56), fill=(20, 20, 24))
    draw.text((50, 110), "同構圖（卷軸＋狐狸）、純水墨、無文字；尾巴扇形展開。右欄＝手機只看到的中央裁切。",
              font=font("Medium", 28), fill=(90, 90, 100))
    for index, (plain, preview) in enumerate(rows):
        y0 = 180 + index * 430
        draw.text((50, y0), f"2b-{index + 1}", font=font("Bold", 40), fill=(20, 20, 24))
        sheet.paste(plain.resize((640, 360), Image.LANCZOS), (50, y0 + 50))
        sheet.paste(preview.resize((640, 360), Image.LANCZOS), (730, y0 + 50))
        sheet.paste(mobile_crop(plain).resize((530, 145), Image.LANCZOS), (1420, y0 + 50))
        draw.text((1420, y0 + 215), "手機只看得到這一塊", font=font("Medium", 28), fill=(90, 90, 100))
    sheet.save(OUT / "yokai-banner-v2-2b-sheet.png")


# ---------- avatars ----------

def ink_mask(size: tuple[int, int], draw_fn, blur: float, noise_amp: float, level: int, seed: int) -> Image.Image:
    layer = Image.new("L", size, 0)
    draw_fn(ImageDraw.Draw(layer))
    soft = np.asarray(layer.filter(ImageFilter.GaussianBlur(blur)), dtype=float)
    noise = np.random.default_rng(seed).normal(0, 1, size[::-1])
    noise = np.asarray(Image.fromarray(((noise - noise.min()) / np.ptp(noise) * 255).astype("uint8"))
                       .filter(ImageFilter.GaussianBlur(2.5)), dtype=float)
    return Image.fromarray(np.clip((soft + (noise - noise.mean()) * noise_amp - level) * 6, 0, 255).astype("uint8"))


def avatar_seal() -> Image.Image:
    img = grain(Image.new("RGB", (800, 800), PAPER), 3.0, 11)
    wash = Image.new("L", (800, 800), 0)
    ImageDraw.Draw(wash).ellipse((110, 110, 690, 690), fill=60)
    img.paste(Image.new("RGB", (800, 800), (150, 142, 128)), (0, 0), wash.filter(ImageFilter.GaussianBlur(70)))
    weibei = ImageFont.truetype(glob.glob(ASSETS + "WeibeiTC-Bold.otf")[0], 470)

    def seal_shape(d: ImageDraw.ImageDraw) -> None:
        d.rectangle((170, 170, 630, 630), fill=255)
        d.text((400, 400), "妖", font=weibei, fill=0, anchor="mm")  # carved out: paper shows through

    mask = ink_mask((800, 800), seal_shape, 3.2, 5.0, 128, 5)
    mottle = np.random.default_rng(9).normal(0, 1, (50, 50))
    mottle = np.asarray(Image.fromarray(((mottle - mottle.min()) / np.ptp(mottle) * 255).astype("uint8"))
                        .resize((800, 800), Image.BICUBIC), dtype=float)[..., None] / 255.0
    red = np.array(VERMILION, dtype=float) * (0.82 + 0.28 * mottle)
    layer = Image.fromarray(np.clip(red, 0, 255).astype("uint8"))
    img.paste(layer, (0, 0), mask)
    return img.rotate(-3, resample=Image.BICUBIC, fillcolor=PAPER)


def avatar_fox(pick: int) -> Image.Image:
    return cover(Image.open(RAW / f"ykav{pick}.png").convert("RGB"), (800, 800), zoom=1.3)  # tighter: reads at 48 px


def build_avatars(fox_pick: int) -> None:
    fox = avatar_fox(fox_pick)
    seal = avatar_seal()
    fox.save(OUT / "yokai-avatar-v2-D.png")
    seal.save(OUT / "yokai-avatar-v2-E.png")
    items = [(f"頭像 {name}（舊）", Image.open(KIT / f"yokai-avatar-{name}.png").convert("RGB")) for name in "ABC"]
    items += [("頭像 D（新・水墨九尾狐）", fox), ("頭像 E（新・「妖」字印章）", seal)]
    sheet = Image.new("RGBA", (2000, 1000), (245, 245, 247, 255))
    draw = ImageDraw.Draw(sheet)
    draw.text((50, 30), "妖怪溯源所　頭像 v2", font=font("Black", 64), fill=(20, 20, 24))
    draw.text((50, 120), "A/B/C 為舊候選（保留）；D/E 為水墨風新作。每個附 240／96／48 px 圓形預覽（YouTube 實際顯示為圓形）。",
              font=font("Medium", 30), fill=(90, 90, 100))
    for index, (label, avatar) in enumerate(items):
        x0, y0 = 50 + (index % 3) * 650, 200 + (index // 3) * 400
        draw.text((x0, y0), label, font=font("Bold", 34), fill=(20, 20, 24))
        sheet.alpha_composite(circle_preview(avatar, 240), (x0, y0 + 60))
        sheet.alpha_composite(circle_preview(avatar, 96), (x0 + 280, y0 + 60))
        sheet.alpha_composite(circle_preview(avatar, 48), (x0 + 280, y0 + 180))
        draw.text((x0 + 340, y0 + 190), "96 / 48 px", font=font("Medium", 24), fill=(90, 90, 100))
    sheet.convert("RGB").save(OUT / "yokai-avatar-v2-sheet.png")


# ---------- kyubi thumbnails ----------

THUMBS = [  # (key, image, lines, highlighted characters, subject)
    ("A", "ykth_a", ("原典說", "牠吃人"), "吃人", "狐臉特寫"),
    ("B", "ykth_b", ("牠本來", "不是妲己"), "妲己", "九尾全身"),
    ("C", "ykth_c", ("殺生石", "裂開了"), "裂開", "裂石與狐影"),
]


def draw_hook(img: Image.Image, lines: tuple[str, ...], highlight: str, size: int) -> None:
    draw = ImageDraw.Draw(img)
    face = xingkai(size)
    y = 720 - 70 - len(lines) * (size + 10)
    for line in lines:
        x = 60
        for char in line:
            color = VERMILION if char in highlight else INK
            draw.text((x, y), char, font=face, fill=color, stroke_width=11, stroke_fill=(250, 246, 236))
            x += face.getlength(char)
        y += size + 10


def thumbnail(key: str, image: str, lines: tuple[str, ...], highlight: str) -> Image.Image:
    img = cover(Image.open(RAW / f"{image}.png").convert("RGB"), (1280, 720))
    veil = np.linspace(0.0, 1.0, 1280)[None, :, None]
    veil = np.clip(1.0 - veil / 0.55, 0.0, 1.0) * 0.55
    base = np.asarray(img, dtype=float)
    img = Image.fromarray((base * (1 - veil) + np.array(PAPER) * veil).astype("uint8"))
    draw_hook(img, lines, highlight, 190)
    draw = ImageDraw.Draw(img)
    draw.rectangle((44, 40, 300, 100), fill=VERMILION)
    draw.text((172, 70), "妖怪溯源所", font=font("Bold", 34), fill=(255, 255, 255), anchor="mm")
    return img


def build_thumbs() -> None:
    made = []
    for key, image, lines, highlight, _ in THUMBS:
        img = thumbnail(key, image, lines, highlight)
        img.save(OUT / f"kyubi-thumb-{key}.jpg", quality=88)
        made.append((key, img))
    sheet = Image.new("RGB", (2000, 1500), (245, 245, 247))
    draw = ImageDraw.Draw(sheet)
    draw.text((50, 30), "九尾狐　縮圖 3 選項", font=font("Black", 64), fill=(20, 20, 24))
    draw.text((50, 120), "規則：主體大、單一焦點、鉤子 5–7 字、每句話前 60 秒內兌現（原典說吃人／最早不是妲己／殺生石裂開）。右欄＝手機首頁 168 px 寬實際大小與 2 倍放大。",
              font=font("Medium", 26), fill=(90, 90, 100))
    for index, (key, img) in enumerate(made):
        y0 = 190 + index * 430
        draw.text((50, y0), f"選項 {key}　{THUMBS[index][4]}", font=font("Bold", 38), fill=(20, 20, 24))
        sheet.paste(img.resize((640, 360), Image.LANCZOS), (50, y0 + 50))
        sheet.paste(img.resize((168, 94), Image.LANCZOS), (730, y0 + 50))
        sheet.paste(img.resize((336, 189), Image.LANCZOS), (730, y0 + 170))
        draw.text((930, y0 + 80), "168×94 實際大小", font=font("Medium", 24), fill=(90, 90, 100))
        draw.text((1090, y0 + 230), "2×", font=font("Medium", 24), fill=(90, 90, 100))
    sheet.save(OUT / "kyubi-thumb-sheet.png")


if __name__ == "__main__":
    wanted = sys.argv[1:] or ["banner", "avatar", "thumb"]
    if "banner2b" in wanted:
        build_banner_2b()
    if "banner" in wanted:
        build_banners()
    if "avatar" in wanted:
        build_avatars(2)
    if "thumb" in wanted:
        build_thumbs()
