"""Brand asset pages: thumbnails, icon, banner, Shorts frame, end card, overview.

Markup lives in ``templates/brands/<code>/assets.html.j2`` (one macro per asset)
and ``templates/brands/endcard.html.j2`` (shared by every channel). This module
only feeds them sample copy and wraps them in a page with the brand's ``:root``
tokens, so the colours can never drift from the slide stylesheet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from content_farm.explainer.brands import BRAND_ASSET_DIR, BRANDS, brand_css_path, brand_palette

ASSET_SHOTS: tuple[tuple[str, tuple[int, int]], ...] = (
    ("thumb_1", (1280, 720)), ("thumb_2", (1280, 720)), ("thumb_3", (1280, 720)),
    ("icon", (800, 800)), ("icon_circle", (800, 800)),
    ("banner", (2560, 1440)), ("shorts", (1080, 1920)), ("endcard", (1920, 1080)),
)

# Sample copy for the three thumbnail mockups per channel (示意, not commitments).
THUMBS: dict[str, tuple[dict, ...]] = {
    "chipcat": (
        {"kicker": "TEARDOWN #012", "lines": ["CoWoS", "卡住 AI？"], "hl": "CoWoS", "sub": "瓶頸在封裝"},
        {"kicker": "TEARDOWN #013", "lines": ["為什麼", "只有台灣？"], "hl": "台灣", "sub": "晶圓代工的護城河"},
        {"kicker": "TEARDOWN #014", "lines": ["HBM", "是什麼？"], "hl": "HBM", "sub": "AI 的記憶體"},
    ),
    "yokai": (
        {"title": "九尾狐", "sub": "牠原本會吃人", "seal": "山海經"},
        {"title": "魔神仔", "sub": "台灣版神隱", "seal": "台灣"},
        {"title": "河童", "sub": "原型到底是誰", "seal": "日本", "size": 190},
    ),
    "offwork": (
        {"tag": "迷因考古", "lines": ["bug？", "是feature！"], "hl": "feature", "size": 112,
         "circle": "left:590px;top:268px;width:520px;height:180px"},
        {"tag": "迷因考古", "lines": ["已讀不回", "幾歲了？"], "hl": "幾歲", "size": 128},
        {"tag": "冷笑話", "lines": ["需求只改", "一點點"], "hl": "一點點", "size": 132},
    ),
    "cel": (
        {"cut": "012", "lines": ["一集動畫", "要多少錢？"], "num": "¥?", "unit": "千萬", "note": "← 片尾有答案",
         "ring_w": 520},
        {"cut": "013", "lines": ["一秒", "畫幾張？"], "num": "8", "unit": "張", "note": "一拍三！", "num_x": 150,
         "ring_w": 300},
        {"cut": "014", "lines": ["作畫監督", "在監督誰？"], "num": "300", "unit": "張/集", "note": "← 示意數字",
         "ring_w": 600, "size": 110},
    ),
}

ENDCARD: dict[str, dict] = {
    "chipcat": {"closing": "拆完了，下一顆晶片見。", "font": "'Noto Sans CJK TC'", "weight": 900},
    "yokai": {"closing": "今日溯源，到此為止。", "font": "'Weibei TC', 'Songti TC'", "weight": 700},
    "offwork": {"closing": "好，冷。下班。", "font": "'Noto Sans CJK TC'", "weight": 900},
    "cel": {"closing": "收工，原畫交出去了。", "font": "'Noto Sans CJK TC'", "weight": 900},
}

_ENV = Environment(loader=FileSystemLoader(str(BRAND_ASSET_DIR)), autoescape=select_autoescape(["html", "j2"]))

_PAGE = """<!doctype html><html lang="zh-Hant-TW"><head><meta charset="utf-8"><style>
{root}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: {w}px; height: {h}px; overflow: hidden; position: relative; }}
{style}
{extra}
</style></head><body>{body}</body></html>"""

_BANNER_GUIDE = """<div style="position:absolute;left:507px;top:509px;width:1546px;height:423px;
outline:4px dashed rgba(230,40,90,.85);pointer-events:none"></div>
<div style="position:absolute;left:515px;top:470px;font:700 26px 'Noto Sans CJK TC';color:rgba(230,40,90,.95)">
所有裝置都看得到的安全區 1546×423（虛線僅為標示）</div>"""


def root_block(code: str) -> str:
    css = brand_css_path(code).read_text(encoding="utf-8")
    start = css.index(":root")
    return css[start: css.index("}", start) + 1]


def studio_mark() -> Markup:
    return Markup((BRAND_ASSET_DIR / "studio_mark.svg").read_text(encoding="utf-8"))


def asset_html(code: str, stem: str, silhouette: Callable[..., str]) -> str:
    sizes = dict(ASSET_SHOTS)
    width, height = sizes[stem]
    macros = _ENV.get_template(f"{code}/assets.html.j2").module

    def sil(left: int, top: int, width: int) -> Markup:
        return Markup(silhouette(code, left=left, top=top, width=width))

    extra = ""
    if stem.startswith("thumb_"):
        body = macros.thumb(THUMBS[code][int(stem[-1]) - 1], sil)
    elif stem == "icon":
        body = macros.icon()
    elif stem == "icon_circle":  # how YouTube shows it: circle crop, plus 3 small sizes
        body = Markup(
            '<div style="position:absolute;inset:0;background:#e9e9e9"></div>'
            '<div style="position:absolute;left:100px;top:40px;width:600px;height:600px;border-radius:50%;'
            'overflow:hidden"><div style="position:relative;width:800px;height:800px;transform:scale(.75);'
            f'transform-origin:0 0">{macros.icon()}</div></div>'
            + "".join(
                f'<div style="position:absolute;left:{x}px;top:{700 - s // 2}px;width:{s}px;height:{s}px;'
                f'border-radius:50%;overflow:hidden"><div style="position:relative;width:800px;height:800px;'
                f'transform:scale({s / 800});transform-origin:0 0">{macros.icon()}</div></div>'
                for x, s in ((260, 88), (380, 48), (460, 24))
            )
        )
    elif stem == "banner":
        body, extra = macros.banner(sil) + Markup(_BANNER_GUIDE), ""
    elif stem == "shorts":
        body = macros.shorts(sil) + Markup(
            '<div style="position:absolute;left:0;right:0;top:1480px;bottom:0;background:'
            'repeating-linear-gradient(45deg,rgba(0,0,0,.08) 0 18px,transparent 18px 36px)"></div>'
            '<div style="position:absolute;right:0;top:900px;width:130px;height:580px;background:'
            'repeating-linear-gradient(45deg,rgba(0,0,0,.08) 0 18px,transparent 18px 36px)"></div>'
            '<div style="position:absolute;left:40px;top:1500px;font:500 28px \'Noto Sans CJK TC\';color:rgba(0,0,0,.45)">'
            "斜線區＝Shorts 介面（標題、按鈕）會蓋住，只放字幕以外的東西</div>")
    elif stem == "endcard":
        body = _ENV.get_template("endcard.html.j2").module.endcard(ENDCARD[code], sil, studio_mark())
    else:
        raise ValueError(f"unknown asset {stem!r}")
    return _PAGE.format(root=root_block(code), w=width, h=height, style=macros.style(), extra=extra, body=body)


def overview_html(out_dir: Path) -> str:
    """Four columns, one per brand: icon, thumbnail, two slides, palette, closing line."""
    cols = []
    for spec in BRANDS:
        uri = (out_dir / spec.code).resolve().as_uri()
        chips = "".join(
            f'<span style="display:inline-block;width:64px;height:40px;background:{hexv};'
            f'border:1px solid rgba(255,255,255,.25)" title="{role}"></span>'
            for role, hexv in brand_palette(spec.code).items())
        cols.append(f"""
<section style="width:560px">
  <div style="display:flex;align-items:center;gap:18px;height:120px">
    <img src="{uri}/icon.png" style="width:110px;height:110px;border-radius:50%">
    <div><div style="font:900 44px 'Noto Sans CJK TC'">{spec.channel}</div>
    <div style="font:24px 'Noto Sans CJK TC';color:#9aa">{spec.line}</div></div>
  </div>
  <img src="{uri}/thumb_1.jpg" style="width:560px;margin-top:14px;display:block">
  <img src="{uri}/slide_01.jpg" style="width:560px;margin-top:14px;display:block">
  <img src="{uri}/slide_02.jpg" style="width:560px;margin-top:14px;display:block">
  <div style="margin-top:16px;display:flex;gap:6px">{chips}</div>
  <div style="margin-top:14px;font:500 24px 'Noto Sans CJK TC';color:#bbb">角色：{spec.mascot}</div>
</section>""")
    mark = (BRAND_ASSET_DIR / "studio_mark.svg").read_text(encoding="utf-8")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:2400px; height:1340px; background:#0d0f12; color:#f2f2f2; padding:50px 52px; font-family:'Noto Sans CJK TC'; }}
</style></head><body>
<div style="display:flex;align-items:center;gap:20px;margin-bottom:26px">
  <span style="display:inline-flex;width:48px;height:48px;color:#f2f2f2">{mark}</span>
  <span style="font:900 40px 'Noto Sans CJK TC'">四個頻道，四套品牌</span>
  <span style="font:26px 'Noto Sans CJK TC';color:#9aa">隱形的同一條線：片尾版位、字幕系統、來源列、工作室標記</span>
</div>
<div style="display:flex;gap:28px">{''.join(cols)}</div>
</body></html>"""
