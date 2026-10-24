"""Shot language for AI illustrations (quality v5 item 3).

A generated picture is described in layers, so neighbouring pictures stop looking like the same scene:

1. shot size   (wide / full / medium / close / insert)   - ``media.shot_size`` or read from the prompt's words
2. camera move (push / pull / pan / track / crane / still) - ``media.camera`` (parallax and Wan follow it)
3. subject     - ``media.prompt``
4. lighting    - ``media.lighting``
5. style       - the channel's style (``channels/styles/<code>.md``, else ``ai_illustration.style_prefix``)

The five-layer idea is OpenMontage's; the vocabulary below and the pacing rules (neighbouring pictures never share a
shot size, shot sizes and camera moves must vary) paraphrase the lemo-opuscar DIRECTOR.md checklist (MIT). The code is ours.
"""

from __future__ import annotations

import re
from collections import Counter

from content_farm.explainer.deck import Camera, Media, MediaKind, ShotSize, Slide

SIZE_PHRASE = {
    ShotSize.WIDE: "wide establishing shot, the subject small within its surroundings",
    ShotSize.FULL: "full shot of the whole subject",
    ShotSize.MEDIUM: "medium shot",
    ShotSize.CLOSE: "close-up detail filling the frame",
    ShotSize.INSERT: "insert shot of a single object on its own",
}
CAMERA_PHRASE = {
    Camera.PUSH: "slow push-in",
    Camera.PULL: "slow pull-back",
    Camera.PAN: "slow pan sideways",
    Camera.TRACK: "camera tracking alongside the subject",
    Camera.CRANE: "rising crane move",
    Camera.STILL: "locked-off camera",
}
# words in a free-written prompt that already name a shot size (checked in this order: the tighter shot wins a tie)
_SIZE_WORDS: tuple[tuple[ShotSize, re.Pattern[str]], ...] = (
    (ShotSize.INSERT, re.compile(r"\binsert shot\b|\bsingle object\b|\bisolated object\b", re.I)),
    (ShotSize.CLOSE, re.compile(r"\bclose-?up\b|\bmacro\b|\bextreme close\b|\bdetail shot\b", re.I)),
    (ShotSize.WIDE, re.compile(r"\bwide (?:shot|angle|view)\b|\bestablishing\b|\bpanorama\b|\baerial\b|\bbird'?s[- ]eye\b|"
                               r"\blong shot\b|\bvast\b", re.I)),
    (ShotSize.FULL, re.compile(r"\bfull (?:shot|body|view)\b|\bwhole\b", re.I)),
    (ShotSize.MEDIUM, re.compile(r"\bmedium shot\b|\bmid shot\b|\bwaist[- ]up\b", re.I)),
)
MIN_DISTINCT_SIZES = 3        # a deck with six or more AI pictures uses at least this many shot sizes
MIN_PICTURES_FOR_VARIETY = 6


def shot_size_of(media: Media) -> ShotSize | None:
    """The explicit size, else one named by the prompt's own words, else None (unspecified: never counted as a repeat)."""
    if media.shot_size is not None:
        return media.shot_size
    for size, pattern in _SIZE_WORDS:
        if pattern.search(media.prompt):
            return size
    return None


def layers(media: Media) -> str:
    """The shot-size and lighting layers as prompt text (empty when the deck did not use them and the prompt names none)."""
    parts = []
    if media.shot_size is not None and not _names_size(media.prompt, media.shot_size):
        parts.append(SIZE_PHRASE[media.shot_size])
    return ", ".join(parts)


def _names_size(prompt: str, size: ShotSize) -> bool:
    return any(pattern.search(prompt) for s, pattern in _SIZE_WORDS if s == size)


def compose_prompt(style_prefix: str, media: Media) -> str:
    """Style, then shot size, then the subject, then lighting: what the image model is asked for."""
    head = layers(media)
    tail = f"lighting: {media.lighting.strip()}" if media.lighting.strip() else ""
    body = ", ".join(p for p in (head, media.prompt.strip().rstrip("."), tail) if p)
    return f"{style_prefix.strip()} {body}".strip()


def motion_prompt_for(media: Media) -> str:
    """The text that tells Wan what moves: the slide's own motion_prompt, else the camera layer."""
    if media.motion_prompt.strip():
        return media.motion_prompt.strip()
    return CAMERA_PHRASE.get(media.camera, "") if media.camera is not None else ""


def adjacent_repeats(slides: list[Slide]) -> list[tuple[str, str, ShotSize]]:
    """(earlier id, later id, size) for neighbouring AI pictures that share a known shot size.

    Neighbours are neighbours in the deck's order of AI pictures within one section; a text page between two pictures
    does not separate them (the viewer still sees two pictures of the same size one after the other)."""
    out: list[tuple[str, str, ShotSize]] = []
    previous: Slide | None = None
    for slide in slides:
        if slide.media_kind != MediaKind.AI_IMAGE or slide.media is None:
            continue
        if previous is not None and previous.media is not None:
            before, after = shot_size_of(previous.media), shot_size_of(slide.media)
            if before is not None and before == after:
                out.append((previous.id, slide.id, before))
        previous = slide
    return out


def size_variety(slides: list[Slide]) -> Counter[ShotSize]:
    return Counter(size for s in slides if s.media_kind == MediaKind.AI_IMAGE and s.media is not None
                   and (size := shot_size_of(s.media)) is not None)
