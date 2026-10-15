"""deck → one standalone HTML page per slide (pure; no browser).

The CSS is inlined so each ``slides/slide_NNN.html`` can be opened, hand-edited
and re-shot on its own. The only external reference is the optional mascot PNG,
linked by absolute ``file://`` URI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from content_farm.explainer.deck import Category, Deck, Section, Slide

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

DISCLAIMER = {
    Category.AI: "非投資建議",
    Category.TECH: "非投資建議",
    Category.KNOWLEDGE: "",
}


@dataclass(frozen=True)
class SlidePage:
    index: int  # 1-based, == scene_number
    slide: Slide
    html: str

    @property
    def stem(self) -> str:
        return f"slide_{self.index:03d}"


@lru_cache(maxsize=1)
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _css(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def theme_css(deck: Deck, style: str | None = None) -> str:
    """Theme stylesheet: the deck category's theme, or an opt-in style from
    ``themes/styles/`` (see :mod:`content_farm.explainer.styles`)."""
    if style is None:
        return _css(f"themes/{deck.category.value}.css")
    from content_farm.explainer.styles import style_css_path

    return style_css_path(style).read_text(encoding="utf-8")


def mascot_uri(mascot_dir: Path | None, slide: Slide) -> str | None:
    """``file://`` URI of the pose PNG, or None (slot stays empty, never an error)."""
    if slide.mascot is None or mascot_dir is None:
        return None
    path = mascot_dir / f"{slide.mascot.pose}.png"
    if not path.is_file():
        logger.info("mascot pose %r not found at %s; slot left empty", slide.mascot.pose, path)
        return None
    return path.resolve().as_uri()


def build_pages(
    deck: Deck,
    *,
    mascot_dir: Path | None = None,
    show_safe_zone: bool = False,
    animate: bool = False,
    style: str | None = None,
) -> tuple[SlidePage, ...]:
    """One page per slide. ``animate`` embeds ``animate.js`` with ``slide.animation``;
    the page still opens in its final state until ``__anim.seek(t)`` is called.
    ``style`` swaps the category theme for an opt-in style (None = category theme)."""
    template = _environment().get_template("slide.html.j2")
    base_css = _css("base.css")
    theme = theme_css(deck, style)
    total = len(deck.slides)

    pages: list[SlidePage] = []
    for section, slide in _walk(deck):
        index = len(pages) + 1
        html = template.render(
            deck=deck,
            section=section,
            slide=slide,
            index=index,
            total=total,
            sources=[deck.source_by_id(sid).title for sid in slide.source_ids],
            disclaimer=DISCLAIMER[deck.category],
            mascot_src=mascot_uri(mascot_dir, slide),
            show_safe_zone=show_safe_zone,
            base_css=base_css,
            theme_css=theme,
            animation=slide.animation.value if animate else None,
            animate_js=_css("animate.js") if animate else "",
        )
        pages.append(SlidePage(index=index, slide=slide, html=html))
    return tuple(pages)


def _walk(deck: Deck) -> list[tuple[Section, Slide]]:
    return [(section, slide) for section in deck.sections for slide in section.slides]
