"""Production rules for a publishable deck.

These are softer than the schema validators: a short sample deck legitimately
breaks them, so ``deck_to_script.py`` prints them as warnings by default and
only fails with ``--strict``. Every message names the slide it is about.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from content_farm.explainer.deck import Deck, Layout, MediaKind

MIN_SLIDES = 15
MAX_SLIDES = 30
MIN_TOTAL_SECONDS = 5 * 60
MAX_TOTAL_SECONDS = 10 * 60
MAX_SLIDES_WITHOUT_BEAT = 3  # "about one light beat every 2-3 slides"
MIN_DISTINCT_LAYOUTS = 3
MAX_BULLETS_SHARE = 0.5
MAX_PLAIN_SLIDE_RUN = 2  # 3+ static slides in a row reads as a slideshow
MIN_FOOTAGE_SHARE = 0.2  # stock + ai_image share of all slides

# Wording that reads as buy/sell advice — the channel never gives it.
_ADVICE = re.compile(r"(買進|賣出|加碼|減碼|目標價|進場|出場|抄底|停損|值得買|推薦買)")
_DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class LintIssue:
    code: str
    message: str


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
    footage = sum(k in (MediaKind.STOCK, MediaKind.AI_IMAGE) for k in kinds)
    if kinds and footage / len(kinds) < MIN_FOOTAGE_SHARE:
        issues.append(LintIssue(
            "footage-share",
            f"{footage}/{len(kinds)} slides are stock/ai_image; target >= "
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
    return issues
