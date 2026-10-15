"""Opt-in slide styles (design exploration, 2026-10).

Each style is a full theme stylesheet in ``templates/themes/styles/<code>.css``
that drops into the same templates as the three category themes. Nothing
selects a style unless ``style=<code>`` is passed to ``build_pages`` /
``overlay_html``; decks without it render exactly as before.

The palette is read from the stylesheet's ``:root`` block, so the contrast
numbers in the review page can never drift from what is actually rendered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

STYLES_DIR = Path(__file__).parent / "templates" / "themes" / "styles"

# Colour roles every style must define, and how each one is used as text.
PALETTE_KEYS = ("bg", "fg", "muted", "rule", "card", "accent", "accent-2")
_VAR_RE = re.compile(r"--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\b")


@dataclass(frozen=True)
class StyleSpec:
    code: str
    name: str            # 中文名
    tagline: str         # 一句話描述
    fonts: str           # heading / body / numbers
    categories: tuple[str, ...]   # ai / tech / knowledge fit, best first
    ai_distance: int     # 1 = looks like a stock template … 5 = clearly hand-directed
    ai_note: str
    motion: str          # how the shared animate.js recipes read in this style
    mascot: str          # pairing notes for 晶片貓 in the bottom-right slot


STYLES: tuple[StyleSpec, ...] = (
    StyleSpec(
        "swiss", "極簡瑞士網格", "白底黑字一抹紅，靠字級與網格說話，沒有任何裝飾。",
        "Noto Sans CJK TC Black / Regular；數字 Helvetica Neue Bold",
        ("tech", "knowledge"), 3,
        "國際主義版式很常見，但大字左齊加細尺規比預設圓角卡片少很多「模板味」。",
        "動畫要硬：count_up 數字跳完就停、線條直接畫出，不要彈跳或光暈。",
        "白底讓任何顏色的角色都很跳；角色描邊 #1d2230 跟黑字同一個重量，最協調。",
    ),
    StyleSpec(
        "editorial", "雜誌編輯", "米色紙上的宋體大標與細線，像長文報導的跨頁。",
        "Songti TC Bold（標題）/ Noto Sans CJK TC（內文）；數字 Didot",
        ("knowledge", "ai", "tech"), 4,
        "宋體大標＋Didot 數字是編輯台的選擇，模板產生器很少這樣配。",
        "淡入要慢（0.5 s 以上）；count_up 用 Didot 的細髮線數字最好看；線條像排版尺規逐段畫。",
        "暖色紙底對深色描邊角色很友善；角色色彩飽和度不要太高，否則搶過宋體標題。",
    ),
    StyleSpec(
        "chalk", "黑板粉筆", "墨綠黑板、粉筆字與手寫底線，像老師在課堂上畫給你看。",
        "Noto Sans CJK TC Medium；英數 Chalkboard SE",
        ("knowledge", "tech"), 4,
        "粉筆粉塵紋理與歪斜底線是手作感來源；風險是看久了像兒童教材。",
        "draw_line 最對味（像粉筆劃過）；建議把 easing 換成線性、文字逐字出現。",
        "深綠底需要角色的白色光暈（mascot worker 已有 2.5 px）；角色若是淺色系會像貼紙，最自然。",
    ),
    StyleSpec(
        "blueprint", "藍圖工程圖", "藍曬紙上的白線網格、尺寸標註與等寬數字。",
        "Noto Sans CJK TC Bold；數字與標籤 Menlo",
        ("tech", "ai"), 3,
        "工程藍圖是常見主題包，但加了尺寸標註線與圖框角標後比較像真的圖紙。",
        "線條要用虛線先畫再實線；count_up 可以像儀表讀數；整體動得越機械越好。",
        "飽和藍底會讓暖色角色（橘、黃）非常跳；冷色角色會被吃掉，需要白色描邊。",
    ),
    StyleSpec(
        "neon", "霓虹賽博", "近黑紫底、洋紅與青色的發光字，夜市招牌遇上終端機。",
        "Noto Sans CJK TC Black；數字 SF Mono",
        ("ai", "tech"), 1,
        "最像 AI 生成封面的一種：紫黑＋霓虹光暈是 2023 年後最氾濫的視覺。",
        "光暈閃爍、掃描線很適合，但 8–10 分鐘看下來會累；動畫要克制。",
        "暗底配發光字，角色需要強烈外光暈才分得出輪廓；可愛角色在這裡會有反差萌，也可能違和。",
    ),
    StyleSpec(
        "pastel", "日系粉彩", "奶油粉底、圓角貼紙與圓體字，輕鬆不嚇人。",
        "Hiragino Maru Gothic ProN（圓體，缺字退 Noto Sans CJK TC）；數字 Arial Rounded",
        ("knowledge", "ai"), 2,
        "粉彩圓角卡很常見於模板；圓體字與貼紙陰影讓它比一般粉彩多一點個性。",
        "動畫可以彈一點（overshoot），但 animate.js 共用 easing 不彈；建議只加 CSS 陰影即可。",
        "和可愛動物角色最搭；角色的深色描邊在淺粉底上對比最高，看起來最「一套」。",
    ),
    StyleSpec(
        "newspaper", "復古報紙", "泛黃新聞紙、粗宋標題、雙線欄框與網點。",
        "Songti TC Black（標題）/ Songti TC（內文）；數字 Bodoni 72",
        ("knowledge", "tech"), 5,
        "雙線欄框、網點、宋體號外標題都很難被模板誤打誤撞做出來，辨識度最高。",
        "最好是「印出來」的感覺：不淡入、直接蓋章式出現；count_up 可以像翻牌機。",
        "黑白報紙上放彩色角色會很突出，像報紙上的貼紙；角色若做成單色網點版會最融合。",
    ),
    StyleSpec(
        "datajournal", "資料新聞", "淡橙米色底、細格線與圖表標註，像財經媒體的圖解。",
        "Noto Sans CJK TC Bold / Regular；數字 DIN Alternate",
        ("tech", "ai", "knowledge"), 4,
        "看起來像一個有編輯方針的媒體，不像套版；細格線與資料標註是關鍵。",
        "grow_bars 與 count_up 是本命；動畫要精準、等速、可讀，不要裝飾。",
        "暖淡底對角色友善；角色應退到「旁註」的角色，對話泡泡用細框白底最一致。",
    ),
    StyleSpec(
        "collage", "紙張剪貼", "牛皮紙底、白紙片、紙膠帶與微微歪掉的卡片。",
        "Noto Sans CJK TC Black；數字 Marker Felt",
        ("knowledge", "ai"), 5,
        "旋轉、膠帶、撕紙邊這些「不完美」最不像 AI 模板；代價是每張要對齊得更小心。",
        "卡片「被拍上去」的感覺最好：短位移＋輕微旋轉；畫線可以像麥克筆。",
        "角色像另一張貼上去的剪紙最自然；可以給角色加白色剪紙邊（mascot worker 的光暈加粗即可）。",
    ),
    StyleSpec(
        "cleanroom", "晶圓無塵室", "冷白無塵室燈光、晶圓晶粒格與黃光區警示色。",
        "Noto Sans CJK TC Bold / Light；數字 SF Mono",
        ("tech", "ai"), 4,
        "晶粒格、黃光條與製程代號是半導體頻道才會有的語彙，跟主題綁得很緊。",
        "draw_line 可以像晶圓量測掃描；count_up 搭配黃光條填滿；整體乾淨、等速。",
        "淺冷色底配晶片貓最合主題；角色可以戴無塵衣兜帽當彩蛋，顏色避開黃色（會跟警示色撞）。",
    ),
)

_BY_CODE = {spec.code: spec for spec in STYLES}


def style_codes() -> tuple[str, ...]:
    return tuple(_BY_CODE)


def get_style(code: str) -> StyleSpec:
    try:
        return _BY_CODE[code]
    except KeyError:
        raise ValueError(f"unknown style {code!r}; choose from {', '.join(_BY_CODE)}") from None


def style_css_path(code: str) -> Path:
    get_style(code)  # validates the code before touching the filesystem
    return STYLES_DIR / f"{code}.css"


def palette(code: str) -> dict[str, str]:
    """Colour roles from the stylesheet's first ``:root`` block."""
    return palette_from_css(style_css_path(code).read_text(encoding="utf-8"), f"style {code!r}")


def palette_from_css(css: str, label: str) -> dict[str, str]:
    """Colour roles from the first ``:root`` block of any theme stylesheet."""
    if ":root" not in css:
        raise ValueError(f"{label} has no :root block")
    root = css[css.index(":root"):]
    root = root[: root.index("}")]
    found = {name: value.lower() for name, value in _VAR_RE.findall(root)}
    missing = [key for key in PALETTE_KEYS if key not in found]
    if missing:
        raise ValueError(f"{label} is missing palette roles: {', '.join(missing)}")
    return {key: found[key] for key in PALETTE_KEYS}


def relative_luminance(hex_colour: str) -> float:
    """WCAG 2.x relative luminance of ``#rrggbb``."""
    value = hex_colour.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"expected #rrggbb, got {hex_colour!r}")
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (label, foreground role, background role, minimum ratio for how it is used)
# 4.5 = WCAG AA body text; 3.0 = AA large text (>= 24 px bold-ish / 31 px).
CONTRAST_PAIRS = (
    ("內文 fg/bg", "fg", "bg", 4.5),
    ("輔助字 muted/bg（22 px 頁尾）", "muted", "bg", 4.5),
    ("強調大字 accent/bg（數字、年份）", "accent", "bg", 3.0),
    ("卡片內文 fg/card", "fg", "card", 4.5),
    ("次強調 accent-2/bg", "accent-2", "bg", 3.0),
)


def contrast_report(code: str) -> list[dict[str, object]]:
    return contrast_report_for(palette(code))


def contrast_report_for(colours: dict[str, str]) -> list[dict[str, object]]:
    return [
        {"pair": label, "fg": colours[fg], "bg": colours[bg],
         "ratio": round(contrast_ratio(colours[fg], colours[bg]), 2), "min": minimum,
         "ok": contrast_ratio(colours[fg], colours[bg]) >= minimum}
        for label, fg, bg, minimum in CONTRAST_PAIRS
    ]
