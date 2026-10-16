"""Per-channel identity: how a channel opens, signs off and writes its description.

YouTube's "inauthentic content" rule (YPP, 2025-07) names "AI-generated content
made with generic or unoriginal templates giving the impression of mass
production". Four channels run by one studio share a pipeline, so what a viewer
(or a reviewer) hears in the first seconds, reads in the description and sees
at the end must differ per channel. These settings live in ``channels/<code>.yaml``
under ``identity:``; :mod:`content_farm.production.channel_rules` enforces them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

# Phrases that read as a studio template on any channel (policy review 2026-10, D3).
TEMPLATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"用\s*[0-9０-９一二三四五六七八九十兩]+\s*張圖"),
    re.compile(r"我先把結論放在這裡"),
    re.compile(r"所有數字附來源"),
)


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Opening(_Strict):
    format: str = Field(min_length=10, max_length=200)    # how the first ~15 s go (deck skill reads it)
    signature: str = Field(min_length=2, max_length=20)   # must be spoken in the opening slides


class Outro(_Strict):
    signature: str = Field(min_length=2, max_length=24)   # must be spoken on the last slide
    endcard: str = Field(min_length=2, max_length=30)     # closing line for the end screen


class DescriptionTemplate(_Strict):
    header: str = Field(min_length=2, max_length=80)          # first line; {title} = video title
    sources_label: str = Field(min_length=2, max_length=60)   # heading of the source list
    footer: str = Field(min_length=2, max_length=160)         # channel promise, before the disclosure


class Identity(_Strict):
    opening: Opening
    take_label: str = Field(min_length=2, max_length=16)  # how the channel names its own view
    outro: Outro
    description: DescriptionTemplate

    def fixed_lines(self) -> tuple[str, ...]:
        """Strings that must not appear in any other channel's identity."""
        header_fixed = self.description.header.replace("{title}", "").strip()
        return (self.opening.signature, self.outro.signature, self.outro.endcard, header_fixed,
                self.description.sources_label, self.description.footer, self.take_label)


def template_phrases(text: str) -> list[str]:
    return [match.group(0) for pattern in TEMPLATE_PATTERNS for match in pattern.finditer(text)]


def collisions(identities: Sequence[tuple[str, Identity]]) -> list[str]:
    """Every fixed string one channel shares with another (equal, or contained in it)."""
    found = []
    for index, (code_a, a) in enumerate(identities):
        for code_b, b in identities[index + 1:]:
            for line_a in a.fixed_lines():
                for line_b in b.fixed_lines():
                    if line_a and line_b and (line_a in line_b or line_b in line_a):
                        found.append(f"{code_a}「{line_a}」≈ {code_b}「{line_b}」")
    return found


def foreign_signatures(text: str, others: Iterable[Identity]) -> list[str]:
    """Another channel's spoken opening/outro signature inside this channel's text."""
    return [sig for other in others for sig in (other.opening.signature, other.outro.signature)
            if sig in text]
