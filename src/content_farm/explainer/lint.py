"""Production rules for a publishable deck.

These are softer than the schema validators: a short sample deck legitimately
breaks them, so ``deck_to_script.py`` prints them as warnings by default and
only fails with ``--strict``. Every message names the slide it is about.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from content_farm.explainer.deck import Deck, Layout, MediaKind, Motion

MIN_SLIDES = 15
MAX_SLIDES = 30
MIN_TOTAL_SECONDS = 5 * 60
MAX_TOTAL_SECONDS = 10 * 60
MAX_SLIDES_WITHOUT_BEAT = 3  # "about one light beat every 2-3 slides"
MIN_DISTINCT_LAYOUTS = 3
MAX_BULLETS_SHARE = 0.5
MAX_PLAIN_SLIDE_RUN = 2  # 3+ static slides in a row reads as a slideshow
MIN_FOOTAGE_SHARE = 0.2  # stock + ai_image share of all slides
# Visual v4 (Leon 2026-10-24): the picture leads, the slide text supports.
MAX_TEXT_ONLY_SHARE = 0.30   # slides that are only text (static / animated slide) of all slides
MIN_WAN_SHOTS = 2            # key shots moved by Wan2.2 I2V (baked overnight)
MAX_WAN_SHOTS = 3          # a deck's own wan_budget replaces it
WAN_MIN_DECK_SLIDES = 10     # a short sample deck is not asked for key shots
TEXT_ONLY_KINDS = (MediaKind.SLIDE, MediaKind.ANIMATED)

# Wan2.2 morphs faces: words that put a person / character face in the frame.
_WAN_FACE = re.compile(
    r"\b(?:faces?|portraits?|persons?|people|humans?|men|man|women|woman|boys?|girls?|child(?:ren)?|"
    r"characters?|animators?|workers?|engineers?|staff|chef|cat|mascot|shoppers?|runners?|archaeologists?|"
    r"expressions?|smil\w+|eyes?|heads?|crowd|customers?|audience|figures?)\b|角色|人物|表情|臉|人像|眼睛",
    re.IGNORECASE,
)

_WAN_NO_PEOPLE = re.compile(r"\b(?:no|without)\s+(?:people|persons?|humans?|characters?|faces?|figures?)\b", re.IGNORECASE)

# Wording that reads as buy/sell advice — the channel never gives it.
_ADVICE = re.compile(r"(買進|賣出|加碼|減碼|目標價|進場|出場|抄底|停損|值得買|推薦買)")
_DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class LintIssue:
    code: str
    message: str
    severity: str = "error"     # "warn" never fails --strict


def lint_deck(deck: Deck) -> tuple[LintIssue, ...]:
    """Return every production-rule violation (empty tuple = publishable)."""
    return (
        *_check_size(deck),
        *_check_beats(deck),
        *_check_layouts(deck),
        *_check_sourcing(deck),
        *_check_advice(deck),
        *_check_draft(deck),
        *_check_media(deck),
        *_check_visuals_v4(deck),
        *_check_shot_language(deck),
        *_check_section_rules(deck),
    )


def _check_size(deck: Deck) -> list[LintIssue]:
    issues: list[LintIssue] = []
    n = len(deck.slides)
    if not MIN_SLIDES <= n <= MAX_SLIDES:
        issues.append(LintIssue("slide-count", f"{n} slides; target {MIN_SLIDES}-{MAX_SLIDES}"))
    total = sum(s.estimated_seconds for s in deck.slides)
    if not MIN_TOTAL_SECONDS <= total <= MAX_TOTAL_SECONDS:
        issues.append(LintIssue(
            "duration",
            f"estimated {total / 60:.1f} min; target {MIN_TOTAL_SECONDS // 60}-"
            f"{MAX_TOTAL_SECONDS // 60} min",
        ))
    return issues


def _check_beats(deck: Deck) -> list[LintIssue]:
    issues: list[LintIssue] = []
    gap = 0
    previous_beat: str | None = None
    for slide in deck.slides:
        if slide.beat is None:
            gap += 1
            if gap == MAX_SLIDES_WITHOUT_BEAT + 1:
                issues.append(LintIssue(
                    "beat-gap",
                    f"slide {slide.id!r}: {gap} slides in a row without gossip/joke",
                ))
            continue
        if slide.beat == previous_beat:
            issues.append(LintIssue(
                "beat-repeat",
                f"slide {slide.id!r}: two {slide.beat} beats in a row; alternate gossip/joke",
            ))
        previous_beat = slide.beat
        gap = 0
    return issues


def _check_layouts(deck: Deck) -> list[LintIssue]:
    issues: list[LintIssue] = []
    layouts = [s.layout for s in deck.slides]
    distinct = len(set(layouts))
    if distinct < MIN_DISTINCT_LAYOUTS:
        issues.append(LintIssue(
            "layout-variety", f"only {distinct} distinct layouts; use >= {MIN_DISTINCT_LAYOUTS}",
        ))
    bullets = layouts.count(Layout.BULLETS)
    if layouts and bullets / len(layouts) > MAX_BULLETS_SHARE:
        issues.append(LintIssue(
            "bullets-heavy", f"{bullets}/{len(layouts)} slides are bullets (template look)",
        ))
    return issues


def _check_sourcing(deck: Deck) -> list[LintIssue]:
    return [
        LintIssue("unsourced-number", f"slide {s.id!r}: narration has numbers but no source_ids")
        for s in deck.slides
        if s.layout != Layout.TITLE and _DIGIT.search(s.narration) and not s.source_ids
    ]


def _check_advice(deck: Deck) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for slide in deck.slides:
        match = _ADVICE.search(slide.narration)
        if match:
            issues.append(LintIssue(
                "investment-advice",
                f"slide {slide.id!r}: {match.group(0)!r} reads as trading advice",
            ))
    return issues


def _check_draft(deck: Deck) -> list[LintIssue]:
    if not deck.draft_data:
        return []
    return [LintIssue("draft-data", "draft_data=true: numbers are placeholders, not publishable")]


def _check_media(deck: Deck) -> list[LintIssue]:
    issues: list[LintIssue] = []
    run = 0
    for slide in deck.slides:
        run = run + 1 if slide.media_kind == MediaKind.SLIDE else 0
        if run == MAX_PLAIN_SLIDE_RUN + 1:
            issues.append(LintIssue(
                "plain-slide-run",
                f"slide {slide.id!r}: {run} static slides in a row; animate one or add footage",
            ))
    kinds = [s.media_kind for s in deck.slides]
    # a channel-drawn animated diagram is moving picture too (v3: replaces off-topic stock)
    footage = sum(k in (MediaKind.STOCK, MediaKind.STOCK_VIDEO, MediaKind.AI_IMAGE, MediaKind.ARTWORK, MediaKind.DIAGRAM) for k in kinds)
    if kinds and footage / len(kinds) < MIN_FOOTAGE_SHARE:
        issues.append(LintIssue(
            "footage-share",
            f"{footage}/{len(kinds)} slides are stock/ai_image/artwork; target >= "
            f"{MIN_FOOTAGE_SHARE:.0%}",
        ))
    for slide in deck.slides:
        if slide.media_kind != MediaKind.TITLE_CARD or slide.media is None:
            continue
        source = deck.source_by_id(slide.media.source_id)
        if not (source.publisher and source.published):
            issues.append(LintIssue(
                "title-card-meta",
                f"slide {slide.id!r}: source {source.id!r} needs publisher and published date",
            ))
        if not source.headline:
            issues.append(LintIssue(
                "title-card-headline",
                f"slide {slide.id!r}: source {source.id!r} needs the outlet's verbatim headline "
                f"(shown as 媒體原標題, apart from the channel summary)",
            ))
    return issues


def _form(slide) -> str:
    """The on-screen form of a slide: the layout of a text page, the text frame of an AI picture, else its media kind."""
    if slide.media_kind in TEXT_ONLY_KINDS:
        return f"text:{slide.layout.value}"
    if slide.media_kind == MediaKind.AI_IMAGE and slide.media is not None:
        return f"ai:{slide.media.frame_kind.value}"
    return slide.media_kind.value


form_of = _form    # public name for other explainer modules (slideshow_risk)


def _check_visuals_v4(deck: Deck) -> list[LintIssue]:
    """Every section has an AI picture; text-only pages are at most 30 %; no two consecutive slides share a form;
    a long deck has 2-3 Wan key shots."""
    issues: list[LintIssue] = []
    for section in deck.sections:
        if not any(s.media_kind == MediaKind.AI_IMAGE for s in section.slides):
            issues.append(LintIssue("section-no-ai-image", f"section {section.title!r}: no ai_image slide (need >= 1 per section)"))
    slides = list(deck.slides)
    text_only = sum(s.media_kind in TEXT_ONLY_KINDS for s in slides)
    if slides and text_only / len(slides) > MAX_TEXT_ONLY_SHARE:
        issues.append(LintIssue(
            "text-only-share",
            f"{text_only}/{len(slides)} slides are text only; target <= {MAX_TEXT_ONLY_SHARE:.0%} (give them an ai_image)",
        ))
    for before, after in zip(slides, slides[1:]):
        if _form(before) == _form(after):
            issues.append(LintIssue(
                "form-repeat", f"slide {after.id!r}: same form as {before.id!r} ({_form(after)}); vary layout / media.frame",
            ))
    wan = [s.id for s in slides if s.media_kind == MediaKind.AI_IMAGE and s.media is not None
           and s.media.motion_kind == Motion.WAN]
    top = max(MAX_WAN_SHOTS, deck.wan_budget or 0)
    if len(slides) >= WAN_MIN_DECK_SLIDES and not MIN_WAN_SHOTS <= len(wan) <= top:
        issues.append(LintIssue(
            "wan-shots", f"{len(wan)} Wan key shots ({', '.join(wan) or 'none'}); target {MIN_WAN_SHOTS}-{top}",
            # no Wan at all is fine when no faceless shot exists: avoiding faces comes first (Leon 2026-10-24)
            severity="warn" if not wan else "error",
        ))
    issues.extend(_check_wan_faces(slides))
    return issues


def _check_wan_faces(slides) -> list[LintIssue]:
    """Wan distorts faces (Leon 2026-10-24): a Wan shot may only be a scene / object / environment / camera move."""
    issues: list[LintIssue] = []
    for slide in slides:
        media = slide.media
        if slide.media_kind != MediaKind.AI_IMAGE or media is None or media.motion_kind != Motion.WAN:
            continue
        text = _WAN_NO_PEOPLE.sub(" ", f"{media.prompt} {media.motion_prompt}")
        found = sorted({m.group(0).lower() for m in _WAN_FACE.finditer(text)})
        if found:
            issues.append(LintIssue(
                "wan-face",
                f"slide {slide.id!r}: Wan shot shows people / a face ({', '.join(found)}); "
                "use parallax, or a scene / object shot without characters",
            ))
    return issues


TEXT_HOLD_CHARS_PER_SECOND = 4.5   # lemo DIRECTOR.md reading rule (Chinese): on-screen text needs chars / 4.5 + 1.5 s
TEXT_HOLD_BASE_SECONDS = 1.5


def _check_shot_language(deck: Deck) -> list[LintIssue]:
    """Neighbouring AI pictures never share a shot size; a deck with many pictures varies its sizes; page text stays up
    long enough to be read (DIRECTOR.md pacing rules, rewritten)."""
    from content_farm.explainer import shot_language
    from content_farm.explainer.slideshow_risk import screen_text_chars

    issues: list[LintIssue] = []
    slides = list(deck.slides)
    for section in deck.sections:
        for before, after, size in shot_language.adjacent_repeats(list(section.slides)):
            issues.append(LintIssue("shot-size-repeat", f"slide {after!r}: same shot size ({size.value}) as {before!r}; "
                                                         "change shot_size (wide / full / medium / close / insert)"))
    sizes = shot_language.size_variety(slides)
    pictures = sum(s.media_kind == MediaKind.AI_IMAGE for s in slides)
    if pictures >= shot_language.MIN_PICTURES_FOR_VARIETY and 0 < sum(sizes.values()) and \
            len(sizes) < shot_language.MIN_DISTINCT_SIZES:
        issues.append(LintIssue("shot-size-variety", f"{pictures} AI pictures use only {len(sizes)} shot size(s); "
                                                      f"use >= {shot_language.MIN_DISTINCT_SIZES}", severity="warn"))
    for slide in slides:
        if slide.layout == Layout.TITLE or slide.media_kind in (MediaKind.AI_IMAGE, MediaKind.STOCK_VIDEO):
            continue          # text over a moving picture is a caption; bare text pages are the ones read like slides
        need = screen_text_chars(slide) / TEXT_HOLD_CHARS_PER_SECOND + TEXT_HOLD_BASE_SECONDS
        if slide.estimated_seconds < need:
            issues.append(LintIssue("text-hold", f"slide {slide.id!r}: {screen_text_chars(slide)} characters on screen "
                                                  f"need ~{need:.1f}s to read, narration lasts {slide.estimated_seconds:.1f}s",
                                    severity="warn"))
    return issues


def _check_section_rules(deck: Deck) -> list[LintIssue]:
    """Chapter rules (quality v5): wording a chapter must keep, and wording it must never contain."""
    issues: list[LintIssue] = []
    for section in deck.sections:
        text = "".join(f"{slide.heading}{slide.narration}" for slide in section.slides)
        issues += [LintIssue("must-keep-missing", f"section {section.title!r}: must keep {phrase!r}, it is gone")
                   for phrase in section.must_keep if phrase not in text]
        issues += [LintIssue("must-avoid-present", f"section {section.title!r}: must not contain {phrase!r}")
                   for phrase in section.must_avoid if phrase in text]
    return issues
