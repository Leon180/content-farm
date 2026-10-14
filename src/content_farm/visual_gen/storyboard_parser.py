"""Parse storyboard_prompts.md → list of Shot objects.

Expected format per shot:

    ### Shot N — `MM:SS~MM:SS.png`
    **字幕對應：** ...
    **風格：** ...
    **目的：** ...

    **Prompt:**
    ```
    ...prompt text...
    ```

Shots are grouped under `## Variant X — ...` headers. We extract shots
per variant and let the caller pick which variant to process.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Shot:
    """A single shot in a storyboard variant."""

    shot_number: int
    filename: str  # MM:SS~MM:SS.png or .mp4
    prompt: str  # Full Nano Banana prompt text
    subtitle_ref: str = ""  # 字幕對應 (optional context)
    style: str = ""  # Style key used
    purpose: str = ""  # 目的

    @property
    def is_video(self) -> bool:
        return self.filename.endswith(".mp4")

    @property
    def is_image(self) -> bool:
        return self.filename.endswith(".png")


@dataclass(frozen=True)
class Variant:
    """A full storyboard variant with multiple shots."""

    name: str  # e.g. "A — 寫實情緒向"
    shots: tuple[Shot, ...]

    @property
    def image_shots(self) -> tuple[Shot, ...]:
        return tuple(s for s in self.shots if s.is_image)

    @property
    def video_shots(self) -> tuple[Shot, ...]:
        return tuple(s for s in self.shots if s.is_video)


# --- regex patterns ---
_VARIANT_HEADER = re.compile(r"^##\s+Variant\s+(.+?)$", re.MULTILINE)
_SHOT_HEADER = re.compile(
    r"###\s+Shot\s+(\d+)\s+[—-]\s+[`']([^`']+)[`']",
)
_SUBTITLE_REF = re.compile(r"\*\*字幕對應[：:]\*\*\s*[「『]?(.+?)[」』]?\s*$", re.MULTILINE)
_STYLE = re.compile(r"\*\*風格[：:]\*\*\s*(.+?)\s*$", re.MULTILINE)
_PURPOSE = re.compile(r"\*\*目的[：:]\*\*\s*(.+?)\s*$", re.MULTILINE)
_PROMPT_BLOCK = re.compile(r"\*\*Prompt[：:]\*\*\s*\n```\n(.*?)\n```", re.DOTALL)


def parse_storyboard(path: Path) -> list[Variant]:
    """Parse a storyboard_prompts.md file into a list of Variant objects.

    Returns a list preserving order. Variants without any shots are skipped.
    """
    content = path.read_text(encoding="utf-8")

    # Split by variant headers. First piece before any header is discarded.
    variant_headers = list(_VARIANT_HEADER.finditer(content))
    if not variant_headers:
        return []

    variants: list[Variant] = []
    for i, match in enumerate(variant_headers):
        name = match.group(1).strip().rstrip("（✅ Selected）").strip()
        start = match.end()
        end = (
            variant_headers[i + 1].start()
            if i + 1 < len(variant_headers)
            else len(content)
        )
        block = content[start:end]
        shots = _parse_shots(block)
        if shots:
            variants.append(Variant(name=name, shots=shots))

    return variants


def _parse_shots(block: str) -> tuple[Shot, ...]:
    """Extract all shots from a variant's markdown block."""
    shots: list[Shot] = []
    shot_matches = list(_SHOT_HEADER.finditer(block))

    for i, match in enumerate(shot_matches):
        shot_num = int(match.group(1))
        filename = match.group(2).strip()
        start = match.end()
        end = (
            shot_matches[i + 1].start()
            if i + 1 < len(shot_matches)
            else len(block)
        )
        section = block[start:end]

        prompt_match = _PROMPT_BLOCK.search(section)
        if not prompt_match:
            continue  # Skip malformed shots
        prompt = prompt_match.group(1).strip()

        subtitle_ref = _first_match(_SUBTITLE_REF, section)
        style = _first_match(_STYLE, section)
        purpose = _first_match(_PURPOSE, section)

        shots.append(Shot(
            shot_number=shot_num,
            filename=filename,
            prompt=prompt,
            subtitle_ref=subtitle_ref,
            style=style,
            purpose=purpose,
        ))

    return tuple(shots)


def _first_match(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    return m.group(1).strip() if m else ""
