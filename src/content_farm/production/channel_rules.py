"""Channel-level rules that keep four channels from looking like one template.

Run by the ``policy`` step (errors stop the run before slides are rendered) and
again by QC. From the 2026-10 policy review (D1, D3):

- ``identity_opening`` / ``identity_outro``: the channel's own spoken opening and
  sign-off (``channels/<code>.yaml`` ``identity``) are in the first slides / last slide;
- ``template_phrase``: no studio-template wording (「用二十四張圖」…) in narration or
  the description;
- ``foreign_phrase``: no other channel's opening or sign-off;
- ``commentary``: at least one ``take`` slide — the channel's own argued view;
- ``mascot_presence``: a channel with a finished mascot rig shows it on (nearly) every slide.
"""

from __future__ import annotations

from collections.abc import Sequence

from content_farm.explainer.deck import Deck
from content_farm.production.channels import Channel
from content_farm.production.identity import Identity, foreign_signatures, template_phrases
from content_farm.production.qc import Finding

OPENING_SLIDES = 3              # the opening = first slides (~first 30 s)
MIN_TAKE_CHARS = 80             # a take is an argued paragraph, not a slogan
MIN_MASCOT_SHARE = 0.8


def opening_findings(identity: Identity, deck: Deck) -> list[Finding]:
    opening = "".join(slide.narration for slide in deck.slides[:OPENING_SLIDES])
    last = deck.slides[-1]
    findings = []
    if identity.opening.signature not in opening:
        findings.append(Finding("identity_opening", "error",
                                f"「{identity.opening.signature}」not spoken in the first {OPENING_SLIDES} "
                                f"slides (channel opening: {identity.opening.format})"))
    if identity.outro.signature not in last.narration:
        findings.append(Finding("identity_outro", "error",
                                f"last slide {last.id!r} lacks the channel sign-off「{identity.outro.signature}」"))
    return findings or [Finding("identity_opening", "ok", f"opening「{identity.opening.signature}」and "
                                                          f"sign-off「{identity.outro.signature}」present")]


def template_findings(deck: Deck, others: Sequence[Identity]) -> list[Finding]:
    texts = [(slide.id, slide.narration) for slide in deck.slides] + [("description", deck.description)]
    template = [f"{where}:{phrase}" for where, text in texts for phrase in template_phrases(text)]
    foreign = [f"{where}:{phrase}" for where, text in texts for phrase in foreign_signatures(text, others)]
    findings = []
    if template:
        findings.append(Finding("template_phrase", "error",
                                f"studio-template wording (政策審查 D3): {'; '.join(template)}"))
    if foreign:
        findings.append(Finding("foreign_phrase", "error",
                                f"another channel's opening/sign-off: {'; '.join(foreign)}"))
    return findings or [Finding("template_phrase", "ok", "no template or other-channel wording")]


def commentary_findings(deck: Deck) -> list[Finding]:
    takes = [slide for slide in deck.slides if slide.take]
    chars = sum(len(slide.narration) for slide in takes)
    if not takes or chars < MIN_TAKE_CHARS:
        return [Finding("commentary", "error",
                        f"needs the channel's own view: mark >= 1 slide `take: true` with >= {MIN_TAKE_CHARS} "
                        f"chars of argued narration (has {len(takes)} slide(s), {chars} chars)")]
    return [Finding("commentary", "ok", f"take slides: {', '.join(slide.id for slide in takes)}")]


def mascot_findings(channel: Channel, deck: Deck) -> list[Finding]:
    if not channel.mascot.rig_ready:
        return []
    slides = deck.slides
    with_mascot = sum(slide.mascot is not None for slide in slides)
    share = with_mascot / len(slides) if slides else 0.0
    level = "ok" if share >= MIN_MASCOT_SHARE else "error"
    return [Finding("mascot_presence", level,
                    f"{channel.mascot.name} on {with_mascot}/{len(slides)} slides (>= {MIN_MASCOT_SHARE:.0%})")]


def deck_rule_findings(channel: Channel, deck: Deck, others: Sequence[Identity]) -> list[Finding]:
    findings = commentary_findings(deck) + mascot_findings(channel, deck)
    if channel.identity is None:
        return findings
    return opening_findings(channel.identity, deck) + template_findings(deck, others) + findings
