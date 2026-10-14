"""AI illustrations for ``media.kind == "ai_image"`` slides — file contract only.

We never drive a browser here. Instead:

1. :func:`write_prompt_files` writes ``<run_dir>/ai_image_prompts.md`` in the
   exact storyboard format ``scripts/generate_visuals.py`` already parses
   (one variant, one shot per slide, shot file name ``<slide_id>.png``) plus a
   machine-readable ``ai_image_prompts.json``.
2. The user runs ``generate_visuals.py --storyboard ai_image_prompts.md
   --out-dir <run_dir>/assets/ai_images --variant 0``; Gemini downloads land as
   ``<slide_id>.png`` (or ``<slide_id>_01.png`` … when it returns several).
3. :func:`find_image` picks the file up on the next ``media_to_visual`` run;
   until then the slide gets a loud placeholder.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from content_farm.explainer.deck import Deck, MediaKind

AI_IMAGE_DIR = Path("assets") / "ai_images"
PROMPTS_MD = "ai_image_prompts.md"
PROMPTS_JSON = "ai_image_prompts.json"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
# Appended to every prompt so the picture matches the 16:9 frame and leaves the
# lower third (where our text overlay sits) uncluttered.
STYLE_SUFFIX = (
    "Landscape 16:9, 1920x1080. Clean editorial illustration, no text, no logos, "
    "no watermarks; keep the lower third calm for a caption."
)


@dataclass(frozen=True)
class AiImageRequest:
    index: int
    slide_id: str
    heading: str
    prompt: str

    @property
    def filename(self) -> str:
        return f"{self.slide_id}.png"


def requests_for(deck: Deck) -> tuple[AiImageRequest, ...]:
    return tuple(
        AiImageRequest(index=i, slide_id=s.id, heading=s.heading,
                       prompt=f"{s.media.prompt.strip()} {STYLE_SUFFIX}")
        for i, s in enumerate(deck.slides, start=1)
        if s.media_kind == MediaKind.AI_IMAGE and s.media is not None
    )


def find_image(image_dir: Path, slide_id: str) -> Path | None:
    """``<id>.<ext>`` wins; otherwise the lowest ``<id>_NN.<ext>`` Gemini candidate."""
    if not image_dir.is_dir():
        return None
    for ext in IMAGE_EXTS:
        exact = image_dir / f"{slide_id}{ext}"
        if exact.is_file():
            return exact
    pattern = re.compile(rf"^{re.escape(slide_id)}_(\d+)({'|'.join(re.escape(e) for e in IMAGE_EXTS)})$",
                         re.IGNORECASE)
    candidates = sorted(
        (int(m.group(1)), p) for p in image_dir.iterdir() if (m := pattern.match(p.name))
    )
    return candidates[0][1] if candidates else None


def render_prompts_md(deck: Deck, requests: tuple[AiImageRequest, ...]) -> str:
    lines = [
        f"# AI 插圖提示詞 — {deck.title}",
        "",
        "由 media_to_visual 產生。執行 generate-visuals 時選 Variant 0，",
        f"輸出目錄指到 `<run_dir>/{AI_IMAGE_DIR.as_posix()}`。",
        "",
        "## Variant AI — 投影片插圖",
        "",
    ]
    for n, req in enumerate(requests, start=1):
        lines += [
            f"### Shot {n} — `{req.filename}`",
            "",
            f"**目的：** 第 {req.index:02d} 張「{req.heading}」的插圖",
            "",
            "**Prompt：**",
            "```",
            req.prompt,
            "```",
            "",
        ]
    return "\n".join(lines)


def write_prompt_files(deck: Deck, run_dir: Path) -> tuple[AiImageRequest, ...]:
    """Write both prompt files (or nothing when the deck has no ai_image slides)."""
    requests = requests_for(deck)
    if not requests:
        return requests
    (run_dir / PROMPTS_MD).write_text(render_prompts_md(deck, requests), encoding="utf-8")
    payload = [
        {"index": r.index, "slide_id": r.slide_id, "heading": r.heading,
         "file": (AI_IMAGE_DIR / r.filename).as_posix(), "prompt": r.prompt}
        for r in requests
    ]
    (run_dir / PROMPTS_JSON).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    return requests
