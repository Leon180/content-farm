"""Per-channel illustration style file: ``channels/styles/<channel>.md`` (quality v5 item 4).

One file per channel says how its pictures look, in four sections (the structure follows lemo-opuscar's per-style
``STYLE.md``; the content is ours)::

    # <channel> 插圖風格
    ## 畫風
    - Traditional East Asian ink wash painting on aged rice paper
    ## 色彩
    - muted grey ink with light colour washes
    ## 構圖
    - generous negative space, one clear focal subject
    ## 禁用
    - text
    - seal

``畫風`` / ``色彩`` / ``構圖`` bullets are prompt fragments (English: the image models are prompted in English); ``禁用``
bullets are things no picture of this channel may contain: they are appended as ``no ...`` and a slide prompt that
asks for one of them is refused (see ``illustrate``). The photo-realism / named-artist rule still applies to the whole file.
Turned off per channel with ``quality.style_file: false``; without a file the channel's ``ai_illustration.style_prefix`` is used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

STYLES_DIR = Path(__file__).resolve().parents[3] / "channels" / "styles"
SECTIONS = {"畫風": "look", "色彩": "colour", "構圖": "composition", "禁用": "forbidden"}
CLOSING = "illustration, not a photograph"


class StyleFileError(ValueError):
    """A style file that does not follow the format."""


@dataclass(frozen=True)
class StyleGuide:
    channel: str
    look: tuple[str, ...]
    colour: tuple[str, ...]
    composition: tuple[str, ...]
    forbidden: tuple[str, ...]

    def prefix(self) -> str:
        """The channel style as the leading part of every illustration prompt."""
        positive = ", ".join((*self.look, *self.colour, *self.composition))
        banned = f", no {', no '.join(self.forbidden)}" if self.forbidden else ""
        return f"{positive}, {CLOSING}{banned}."

    def forbidden_in(self, prompt: str) -> list[str]:
        """Forbidden things a slide prompt asks for (negated mentions such as "no text" are fine)."""
        found = []
        for term in self.forbidden:
            for match in re.finditer(rf"\b{re.escape(term)}\b", prompt, re.IGNORECASE):
                before = prompt[max(0, match.start() - 12):match.start()].lower()
                if not re.search(r"\b(no|without|never)\s+(?:\w+\s+)?$", before):
                    found.append(term)
                    break
        return found


def parse(channel: str, text: str) -> StyleGuide:
    bucket: dict[str, list[str]] = {name: [] for name in SECTIONS.values()}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            heading = line[3:].strip()
            if heading not in SECTIONS:
                raise StyleFileError(f"{channel}: unknown section {heading!r}; use {', '.join(SECTIONS)}")
            current = SECTIONS[heading]
        elif line.startswith("- "):
            if current is None:
                raise StyleFileError(f"{channel}: a bullet before any section")
            bucket[current].append(line[2:].strip())
    for needed in ("look", "colour"):
        if not bucket[needed]:
            raise StyleFileError(f"{channel}: section {'畫風' if needed == 'look' else '色彩'} is empty")
    return StyleGuide(channel, *(tuple(bucket[k]) for k in ("look", "colour", "composition", "forbidden")))


def load(channel: str, directory: Path = STYLES_DIR) -> StyleGuide | None:
    path = directory / f"{channel}.md"
    if not path.is_file():
        return None
    guide = parse(channel, path.read_text(encoding="utf-8"))
    from content_farm.explainer.illustrate import forbidden_prompt_terms

    bad = forbidden_prompt_terms(guide.prefix())
    if bad:
        raise StyleFileError(f"{channel}: style asks for {bad} (rule: 非擬真、不模仿畫家)")
    return guide
