"""Compose avatars (800x800), banners (2560x1440 + safe-area previews) and per-channel sheets from raw art.

Run: python artifacts/brand-kit/src/compose.py   (PIL only, no model calls). Existing characters are reused as-is.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

KIT = Path("artifacts/brand-kit")
RAW = KIT / "raw"
PACK = Path("src/content_farm/explainer/pngtuber/packs/paint-bottle-3d")
FONT_DIR = Path.home() / "Library/Fonts"
SAFE_W, SAFE_H = 1546, 423
BANNER = (2560, 1440)


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / f"NotoSansCJKtc-{weight}.otf"), size)


def hexrgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def cover(img: Image.Image, size: tuple[int, int], zoom: float = 1.0) -> Image.Image:
    if zoom > 1.0:  # trim the paper/white edge some generations carry
        margin_x, margin_y = round(img.width * (1 - 1 / zoom) / 2), round(img.height * (1 - 1 / zoom) / 2)
        img = img.crop((margin_x, margin_y, img.width - margin_x, img.height - margin_y))
    scale = max(size[0] / img.width, size[1] / img.height)
    resized = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (resized.width - size[0]) // 2, (resized.height - size[1]) // 2
    return resized.crop((left, top, left + size[0], top + size[1]))


def paste_center(canvas: Image.Image, sprite: Image.Image, center: tuple[int, int], height: int) -> None:
    scale = height / sprite.height
    sprite = sprite.resize((round(sprite.width * scale), round(sprite.height * scale)), Image.LANCZOS)
    canvas.alpha_composite(sprite, (center[0] - sprite.width // 2, center[1] - sprite.height // 2))


def circle_preview(avatar: Image.Image, size: int) -> Image.Image:
    small = avatar.convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(small, (0, 0), mask.resize((size, size), Image.LANCZOS))
    return out


# ---------- avatars ----------

def grid_lines(canvas: Image.Image, color: str, step: int, alpha: int = 40) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for pos in range(0, canvas.width, step):
        draw.line((pos, 0, pos, canvas.height), fill=(*hexrgb(color), alpha), width=4)
        draw.line((0, pos, canvas.width, pos), fill=(*hexrgb(color), alpha), width=4)
    canvas.alpha_composite(layer)


def cat_sprite(pose: str) -> Image.Image:
    return Image.open(RAW / f"chipcat_{pose}.png").convert("RGBA")


def bottle(expression: str) -> Image.Image:
    base = Image.open(PACK / "base.png").convert("RGBA")
    if expression != "base":
        base.alpha_composite(Image.open(PACK / f"{expression}.png").convert("RGBA"))
    return base


def badge(canvas: Image.Image, char: str, fill: str, ink: str) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((470, 470, 670, 670), fill=hexrgb(fill), outline=hexrgb(ink), width=8)
    draw.text((570, 570), char, font=font("Black", 130), fill=hexrgb(ink), anchor="mm")


def avatar_chipcat(option: int) -> Image.Image:
    if option == 1:
        img = Image.new("RGBA", (800, 800), hexrgb("#0e1b2a") + (255,))
        grid_lines(img, "#8aa4c0", 160)
        paste_center(img, cat_sprite("idle"), (400, 430), 640)
    elif option == 2:
        img = Image.new("RGBA", (800, 800), hexrgb("#d9480f") + (255,))
        grid_lines(img, "#ffffff", 100, 36)
        paste_center(img, cat_sprite("smug"), (400, 430), 640)
    else:
        img = Image.new("RGBA", (800, 800), hexrgb("#f2f5f8") + (255,))
        sprite = cat_sprite("wave").crop((0, 0, 380, 300))  # head and shoulders: reads at 48 px
        paste_center(img, sprite, (400, 430), 620)
        ImageDraw.Draw(img).ellipse((22, 22, 777, 777), outline=hexrgb("#d9480f"), width=44)
    return img


def avatar_cel(option: int) -> Image.Image:
    if option == 1:
        img = Image.new("RGBA", (800, 800), hexrgb("#f5f1e8") + (255,))
        ImageDraw.Draw(img).ellipse((100, 100, 700, 700), fill=hexrgb("#cc2f2a"))
        paste_center(img, bottle("base"), (400, 410), 660)
    elif option == 2:
        img = Image.new("RGBA", (800, 800), hexrgb("#1f2329") + (255,))
        ImageDraw.Draw(img).polygon([(0, 560), (800, 260), (800, 340), (0, 640)], fill=hexrgb("#cc2f2a"))
        paste_center(img, bottle("smug"), (400, 410), 660)
    else:
        img = Image.new("RGBA", (800, 800), hexrgb("#dbe7f3") + (255,))
        grid_lines(img, "#5b8fc9", 80, 70)
        sprite = bottle("surprised").crop((200, 120, 570, 560))  # cap and face
        paste_center(img, sprite, (400, 410), 680)
    return img


def avatar_generated(channel: str, option: int, char: str, badge_fill: str, badge_ink: str) -> Image.Image:
    img = cover(Image.open(RAW / f"{channel}_a{option}.png").convert("RGBA"), (800, 800), zoom=1.12)
    if option == 3:
        badge(img, char, badge_fill, badge_ink)
    return img


# ---------- banners ----------

def banner_background(channel: str, option: int) -> Image.Image:
    generated = RAW / f"{channel}_b{option}.png"
    if generated.is_file():
        return cover(Image.open(generated).convert("RGBA"), BANNER, zoom=1.15)
    if channel == "chipcat":
        if option == 1:
            img = Image.new("RGBA", BANNER, hexrgb("#0e1b2a") + (255,))
            grid_lines(img, "#8aa4c0", 160, 34)
            draw = ImageDraw.Draw(img)
            for x in range(80, BANNER[0], 320):  # chip pads at the top and bottom edges only
                for y in (60, 1380):
                    draw.rectangle((x, y - 14, x + 70, y + 14), fill=hexrgb("#d9480f"))
        else:
            img = Image.new("RGBA", BANNER, hexrgb("#f2f5f8") + (255,))
            draw = ImageDraw.Draw(img)
            draw.polygon([(0, 1440), (900, 1440), (1500, 0), (600, 0)], fill=hexrgb("#d9480f") + (255,))
            grid_lines(img, "#0e1b2a", 160, 18)
        return img
    # cel
    if option == 1:
        img = Image.new("RGBA", BANNER, hexrgb("#f5f1e8") + (255,))
        grid_lines(img, "#5b8fc9", 80, 60)
        ImageDraw.Draw(img).rectangle((0, 1340, 2560, 1370), fill=hexrgb("#cc2f2a"))
    else:
        img = Image.new("RGBA", BANNER, hexrgb("#1f2329") + (255,))
        draw = ImageDraw.Draw(img)
        for x in range(40, BANNER[0], 200):  # film-strip frames along the edges
            draw.rounded_rectangle((x, 40, x + 150, 190), 12, outline=hexrgb("#f5f1e8"), width=6)
            draw.rounded_rectangle((x, 1250, x + 150, 1400), 12, outline=hexrgb("#f5f1e8"), width=6)
        draw.rectangle((0, 1210, 2560, 1224), fill=hexrgb("#cc2f2a"))
    return img


def banner(channel: str, option: int, spec: dict) -> Image.Image:
    img = banner_background(channel, option)
    left, top = (BANNER[0] - SAFE_W) // 2, (BANNER[1] - SAFE_H) // 2
    panel = Image.new("RGBA", BANNER, (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle((left - 30, top - 30, left + SAFE_W + 30, top + SAFE_H + 30), 40,
                                            fill=hexrgb(spec["panel"]) + (spec["panel_alpha"],))
    img.alpha_composite(panel)
    mark = spec["mark"](option)
    mark_size = 360
    mark = mark.convert("RGBA").resize((mark_size, mark_size), Image.LANCZOS) if mark.width == mark.height else mark
    img.alpha_composite(circle_preview(mark, mark_size), (left + 20, top + (SAFE_H - mark_size) // 2))
    text_x = left + mark_size + 70
    draw = ImageDraw.Draw(img)
    ink, soft = hexrgb(spec["ink"]), hexrgb(spec["soft"])
    draw.text((text_x, top + 20), spec["name"], font=font("Black", 128), fill=ink)
    draw.text((text_x, top + 188), spec["taglines"][option - 1], font=font("Bold", 50), fill=ink)
    draw.text((text_x, top + 292), "每週 ＿＿ 、＿＿ 更新", font=font("Medium", 42), fill=soft)
    return img


def safe_preview(img: Image.Image) -> Image.Image:
    out = img.copy()
    left, top = (BANNER[0] - SAFE_W) // 2, (BANNER[1] - SAFE_H) // 2
    shade = Image.new("RGBA", BANNER, (0, 0, 0, 120))
    ImageDraw.Draw(shade).rectangle((left, top, left + SAFE_W, top + SAFE_H), fill=(0, 0, 0, 0))
    out.alpha_composite(shade)
    draw = ImageDraw.Draw(out)
    draw.rectangle((left, top, left + SAFE_W, top + SAFE_H), outline=(255, 40, 40), width=8)
    draw.text((left, top - 60), "安全區 1546×423（所有裝置都看得到）", font=font("Bold", 44), fill=(255, 60, 60))
    return out


# ---------- sheet ----------

def sheet(channel: str, spec: dict, avatars: list[Image.Image], banners: list[Image.Image]) -> Image.Image:
    width, height = 2000, 1560
    img = Image.new("RGBA", (width, height), (245, 245, 247, 255))
    draw = ImageDraw.Draw(img)
    draw.text((50, 30), f"{spec['name']}　品牌包候選", font=font("Black", 64), fill=(20, 20, 24))
    draw.text((50, 120), spec["note"], font=font("Medium", 32), fill=(90, 90, 100))
    for index, avatar in enumerate(avatars):
        x0 = 50 + index * 650
        draw.text((x0, 200), f"頭像 {chr(65 + index)}", font=font("Bold", 40), fill=(20, 20, 24))
        img.alpha_composite(circle_preview(avatar, 360), (x0, 260))
        img.alpha_composite(circle_preview(avatar, 96), (x0 + 400, 260))
        img.alpha_composite(circle_preview(avatar, 48), (x0 + 400, 380))
        draw.text((x0 + 460, 390), "96 / 48 px", font=font("Medium", 26), fill=(90, 90, 100))
    for index, (plain, _) in enumerate(banners):
        y0 = 700 + index * 430
        draw.text((50, y0 - 10), f"橫幅 {index + 1}", font=font("Bold", 40), fill=(20, 20, 24))
        img.alpha_composite(plain.resize((640, 360), Image.LANCZOS), (50, y0 + 40))
        img.alpha_composite(banners[index][1].resize((640, 360), Image.LANCZOS), (730, y0 + 40))
        crop = plain.crop(((BANNER[0] - SAFE_W) // 2, (BANNER[1] - SAFE_H) // 2,
                           (BANNER[0] + SAFE_W) // 2, (BANNER[1] + SAFE_H) // 2))
        img.alpha_composite(crop.resize((530, 145), Image.LANCZOS), (1420, y0 + 40))
        draw.text((1420, y0 + 200), "手機只看得到這一塊", font=font("Medium", 28), fill=(90, 90, 100))
    return img


def build(channel: str, spec: dict, avatar_fn) -> None:
    avatars = [avatar_fn(option) for option in (1, 2, 3)]
    for index, avatar in enumerate(avatars):
        avatar.convert("RGBA").save(KIT / f"{channel}-avatar-{chr(65 + index)}.png")
    banners = []
    for option in (1, 2):
        plain = banner(channel, option, spec)
        preview = safe_preview(plain)
        plain.convert("RGB").save(KIT / f"{channel}-banner-{option}.png")
        preview.convert("RGB").save(KIT / f"{channel}-banner-{option}-safe.png")
        banners.append((plain, preview))
    sheet(channel, spec, avatars, banners).convert("RGB").save(KIT / f"{channel}-sheet.png")
    print("built", channel)


SPECS = {
    "chipcat": dict(name="晶片貓", panel="#0e1b2a", panel_alpha=215, ink="#ffffff", soft="#ffc21a",
                    taglines=["晶片貓：用貓的速度看懂半導體", "半導體長片 × 科技快報，一次看懂"],
                    note="既有角色（灰虎斑＋晶片頭盔）；橫幅標語 2 同時涵蓋長片與「晶片貓快報」Shorts。",
                    mark=lambda o: avatar_chipcat(1)),
    "cel": dict(name="賽璐璐研究室", panel="#1f2329", panel_alpha=225, ink="#f5f1e8", soft="#f0a29e",
                taglines=["把動畫產業一格一格拆開", "一秒二十四格，錢都花在哪"],
                note="既有角色：顏料瓶老師傅（3D 版 PNGtuber 圖，換表情與構圖）。",
                mark=lambda o: avatar_cel(1)),
    "yokai": dict(name="妖怪溯源所", panel="#14110d", panel_alpha=215, ink="#efe4cb", soft="#c9a45c",
                  taglines=["每隻妖怪都查戶口，先看原典", "從山海經追到玉藻前，查出處不唬爛"],
                  note="符號型（無角色）；青蛙書記已選定為主持人，此處刻意不用，避免與主持人設定打架。",
                  mark=lambda o: avatar_generated("yokai", 1, "妖", "#e0503a", "#14110d")),
    "deepsea": dict(name="深潛日誌", panel="#04101c", panel_alpha=205, ink="#dcecf5", soft="#36e0c4",
                    taglines=["一次下潛，帶回一個深海冷知識", "越往下越安靜，也越奇怪"],
                    note="符號型（無角色）；名稱候選：深潛日誌（查重無同名）／深海打卡／潛入深藍。",
                    mark=lambda o: avatar_generated("deepsea", 1, "深", "#36e0c4", "#04101c")),
    "fable": dict(name="寓言學堂", panel="#2b1d12", panel_alpha=205, ink="#efe4cb", soft="#e8b27d",
                  taglines=["先聽故事，最後才告訴你它在講什麼", "一則小故事，一個大道理"],
                  note="符號型（無人物）；名稱候選：寓言學堂／先聽個故事（「原來如此」已有同名頻道，不建議）。",
                  mark=lambda o: avatar_generated("fable", 1, "寓", "#e08a52", "#2b1d12")),
}

if __name__ == "__main__":
    build("chipcat", SPECS["chipcat"], avatar_chipcat)
    build("cel", SPECS["cel"], avatar_cel)
    build("yokai", SPECS["yokai"], lambda o: avatar_generated("yokai", o, "妖", "#e0503a", "#14110d"))
    build("deepsea", SPECS["deepsea"], lambda o: avatar_generated("deepsea", o, "深", "#36e0c4", "#04101c"))
    build("fable", SPECS["fable"], lambda o: avatar_generated("fable", o, "寓", "#e08a52", "#2b1d12"))
