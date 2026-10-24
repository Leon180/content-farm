"""``deck.json`` → ``script.json`` (the shared pipeline contract).

One slide becomes one ``Scene`` so voice writes one ``scene_NNN.mp3`` per
slide; one section becomes one ``ChapterOutline``. Durations are estimates
until voice runs ``sync_script_durations`` and overwrites them.
"""

from __future__ import annotations

from content_farm.explainer.deck import Deck, MediaKind, Slide, Source
from content_farm.script_gen.schemas import ChapterOutline, Scene, Script, VisualHint
from content_farm.types import GenreTemplate, Orientation, Tone, VideoLength

SLIDE_VISUAL_STYLE = "slide"


def deck_to_script(deck: Deck) -> Script:
    scenes: list[Scene] = []
    chapters: list[ChapterOutline] = []
    clock = 0.0

    for chapter_number, section in enumerate(deck.sections, start=1):
        chapter_start = clock
        for slide in section.slides:
            duration = slide.estimated_seconds
            scenes.append(Scene(
                scene_number=len(scenes) + 1,
                title=slide.heading,
                narration=slide.narration,
                visual_hint=_visual_hint(slide),
                duration_seconds=duration,
                chapter_number=chapter_number,
            ))
            clock += duration
        chapters.append(ChapterOutline(
            chapter_number=chapter_number,
            title=section.title,
            summary=" / ".join(s.heading for s in section.slides),
            duration_seconds=round(clock - chapter_start, 2),
            key_points=tuple(s.heading for s in section.slides),
            start_timestamp=round(chapter_start, 2),
        ))

    return Script(
        video_title=deck.title,
        description=deck.description,
        scenes=tuple(scenes),
        target_length=VideoLength.MEDIUM,
        tone=Tone.EDUCATIONAL,
        total_duration_seconds=round(clock, 2),
        tags=deck.tags,
        sources=tuple(_format_source(s) for s in deck.sources),
        pronunciation_map=dict(deck.pronunciation_map),
        orientation=Orientation.LANDSCAPE,
        genre=GenreTemplate.KNOWLEDGE,
        chapters=tuple(chapters),
    )


_SOURCE_PREFERENCE = {MediaKind.STOCK: "stock", MediaKind.STOCK_VIDEO: "stock", MediaKind.AI_IMAGE: "ai"}


def _visual_hint(slide: Slide) -> VisualHint:
    """Carry ``media`` into the scene so timeline tools can see what goes on screen.

    ``style`` is the media kind (``slide`` when absent, as in v1); ``description``
    stays ``<layout>:<slide id>`` and gains ``|<detail>`` for animated/ai/title cards.
    """
    kind = slide.media_kind
    media = slide.media
    detail = ""
    keywords: tuple[str, ...] = ()
    if media is not None:
        if kind in (MediaKind.STOCK, MediaKind.STOCK_VIDEO):
            keywords = (media.query,)
        elif kind == MediaKind.ANIMATED:
            detail = slide.animation.value
        elif kind == MediaKind.AI_IMAGE:
            detail = media.prompt
        elif kind == MediaKind.TITLE_CARD:
            detail = f"source:{media.source_id}"
        elif kind == MediaKind.ARTWORK:
            detail = f"artwork:{media.artwork}"
    description = f"{slide.layout.value}:{slide.id}" + (f"|{detail}" if detail else "")
    return VisualHint(
        description=description,
        style=SLIDE_VISUAL_STYLE if kind == MediaKind.SLIDE else kind.value,
        keywords=keywords,
        source_preference=_SOURCE_PREFERENCE.get(kind, "auto"),
    )


def _format_source(source: Source) -> str:
    return f"{source.title} — {source.url}" if source.url else source.title
