"""Concept-diagram pages (the reveal, the explain beats, the closing line) and the thumbnail, as HTML for the page capturer.

A diagram frame is the story picture in a window (top of a 9:16 frame, left of a 16:9 one) beside a paper panel;
the panel is a transparent-background overlay PNG, so ffmpeg can lay it over the moving picture. Rows of an
explain beat appear one by one (one overlay per step).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from content_farm.production.fable.model import Beat, Fable

TEMPLATES = Path(__file__).parent / "templates"
PAPER = "0xF3E9D2"          # the same colour as the panel, for the ffmpeg canvas behind the window


@dataclass(frozen=True)
class Geometry:
    size: tuple[int, int]
    window: tuple[int, int, int, int]       # x, y, w, h of the picture window
    panel_css: str
    rule_css: str
    pad: int
    gap: int
    px: dict[str, int]                      # font sizes: label, head, row, row4, apply, name6/name8/name9

    @property
    def width(self) -> int:
        return self.size[0]


GEOMETRY = {
    "short": Geometry((1080, 1920), (0, 0, 1080, 880), "left:0;top:880px;width:1080px;height:1040px;",
                      "left:0;top:0;width:100%;height:10px;", 60, 28,
                      {"label": 40, "head": 56, "row": 44, "row4": 38, "apply": 56, "name6": 150, "name8": 126, "name9": 100}),
    "mid": Geometry((1920, 1080), (0, 0, 1080, 1080), "left:1080px;top:0;width:840px;height:1080px;",
                    "left:0;top:0;width:10px;height:100%;", 56, 24,
                    {"label": 34, "head": 48, "row": 38, "row4": 34, "apply": 46, "name6": 130, "name8": 108, "name9": 88}),
}


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))


def _name_px(geo: Geometry, name: str) -> int:
    size = len(name)
    return geo.px["name6"] if size <= 6 else geo.px["name8"] if size <= 8 else geo.px["name9"]


def overlay_html(fable: Fable, beat: Beat, rows_visible: int | None = None) -> str:
    """Panel for a reveal / explain / apply beat; ``rows_visible`` limits the explain rows shown so far."""
    geo = GEOMETRY[fable.format]
    rows = list(beat.card.rows) if beat.card else []
    if rows_visible is not None:
        rows = rows[:rows_visible]
    heading = (beat.card.title if beat.card and beat.card.title else "現實裡的它") if beat.act != "explain" else \
        (beat.card.title if beat.card and beat.card.title else "故事 → 概念")
    return _env().get_template("fable_overlay.html.j2").render(
        w=geo.size[0], h=geo.size[1], mode={"reveal": "reveal", "explain": "explain"}.get(beat.act, "apply"),
        panel_css=geo.panel_css, rule_css=geo.rule_css, pad=geo.pad, gap=geo.gap, label_px=geo.px["label"],
        head_px=geo.px["head"], row_px=geo.px["row4"] if len(beat.card.rows if beat.card else ()) > 3 else geo.px["row"],
        apply_px=geo.px["apply"], name_px=_name_px(geo, fable.concept.name), domain=fable.concept.domain,
        concept=fable.concept.name, english=" / ".join(fable.concept.english[:2]), heading=heading, rows=rows)


def row_times(count: int, seconds: float, lead: float = 0.8) -> list[float]:
    """When each row appears: spread over the beat so the screen changes every ~2–3 s."""
    if count == 0:
        return []
    step = max(0.6, min(3.0, (seconds - lead) / (count + 1)))
    return [round(lead + step * (i + 0.5), 2) for i in range(count)]


def thumb_html(fable: Fable, image_name: str) -> str:
    geo = GEOMETRY[fable.format]
    short = fable.format == "short"
    return _env().get_template("fable_thumb.html.j2").render(
        w=geo.size[0], h=geo.size[1], image=image_name, title=fable.title, tag="寓言學堂",
        pad=70 if short else 60, title_px=92 if short else 84, tag_px=40 if short else 34)
