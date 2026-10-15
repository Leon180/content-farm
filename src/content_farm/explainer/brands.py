"""Channel brands (design proposal, 2026-10).

A brand is the per-*channel* visual system: one stylesheet in
``templates/themes/brands/<code>.css`` that every video on that channel reuses,
plus the thumbnail / icon / banner templates in ``templates/brands/<code>/``.
Nothing selects a brand unless ``brand=<code>`` is passed to ``build_pages`` /
``overlay_html``; without it decks render exactly as before.

The ten ``styles`` were explorations on one deck; brands are what those
explorations turned into once they were redefined around a channel's
personality (see ``docs/design/channel-brands/``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from content_farm.explainer.styles import contrast_report_for, palette_from_css

TEMPLATES_DIR = Path(__file__).parent / "templates"
BRAND_CSS_DIR = TEMPLATES_DIR / "themes" / "brands"
BRAND_ASSET_DIR = TEMPLATES_DIR / "brands"


@dataclass(frozen=True)
class BrandSpec:
    code: str
    channel: str          # recommended channel name (proposal, not final)
    line: str             # 頻道類型
    category: str         # deck category the channel's decks use today
    mascot: str           # who sits in the mascot slot
    derived_from: tuple[str, ...]  # slide-styles-10 codes it borrowed from


BRANDS: tuple[BrandSpec, ...] = (
    BrandSpec("chipcat", "晶片貓", "台灣科技產業拆解", "tech",
              "晶片貓（本尊）", ("cleanroom", "datajournal", "blueprint")),
    BrandSpec("yokai", "妖怪溯源所", "神話・怪物溯源", "knowledge",
              "說書貓（晶片貓換裝：斗篷＋提燈）", ("editorial", "newspaper")),
    BrandSpec("offwork", "晶片貓下班了", "冷笑話 Shorts＋迷因考古", "knowledge",
              "下班貓（晶片貓便服）＋配角 PM 狗", ("collage", "pastel")),
    BrandSpec("cel", "賽璐璐研究室", "動畫產業拆解", "knowledge",
              "格仔（新角色，底片格身體）", ("blueprint", "swiss", "chalk")),
)

_BY_CODE = {spec.code: spec for spec in BRANDS}


def brand_codes() -> tuple[str, ...]:
    return tuple(_BY_CODE)


def get_brand(code: str) -> BrandSpec:
    try:
        return _BY_CODE[code]
    except KeyError:
        raise ValueError(f"unknown brand {code!r}; choose from {', '.join(_BY_CODE)}") from None


def brand_css_path(code: str) -> Path:
    get_brand(code)  # validates the code before touching the filesystem
    return BRAND_CSS_DIR / f"{code}.css"


def brand_palette(code: str) -> dict[str, str]:
    return palette_from_css(brand_css_path(code).read_text(encoding="utf-8"), f"brand {code!r}")


def brand_contrast_report(code: str) -> list[dict[str, object]]:
    return contrast_report_for(brand_palette(code))
