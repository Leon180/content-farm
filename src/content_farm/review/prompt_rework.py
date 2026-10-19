"""Media-panel reworks of AI illustrations (orchestrator decision 2026-10-19).

The media panel flags an ``ai_image`` slide → the image moves to ``assets/ai_images/rejected/`` and the
deck agent rewrites only that slide's ``media.prompt`` (narration and every other field untouched); a
prompt that contradicts itself ("no seal" + "a large red seal") is refused before it reaches the model;
each regeneration uses a new seed (base + number of rejected attempts), so a redo never reproduces
the rejected picture (九尾狐 s08b: same prompt + seed 42 gave the same fake seal three times).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from content_farm.explainer.ai_images import AI_IMAGE_DIR

REJECTED_DIR = "rejected"
_NEGATION = re.compile(r"\b(?:no|without|never)\s+([a-z][a-z-]*)", re.I)


def _stem(word: str) -> str:
    word = word.lower()
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def contradictions(prompt: str) -> list[str]:
    """Words a prompt both forbids ("no seal") and asks for ("red square seal") elsewhere."""
    forbidden = {_stem(m.group(1)) for m in _NEGATION.finditer(prompt)}
    remainder = _NEGATION.sub(" ", prompt)
    asked = {_stem(w) for w in re.findall(r"[a-z][a-z-]*", remainder.lower())}
    return sorted(forbidden & asked)


def _slides(deck: dict) -> dict[str, dict]:
    return {s["id"]: s for sec in deck.get("sections", []) for s in sec.get("slides", [])}


def prompt_only_problems(before: dict, after: dict, ids: set[str], style_prefix: str = "") -> list[str]:
    """Why ``after`` is not a prompt-only rewrite of ``before`` for slides ``ids`` ([] = it is)."""
    old, new = _slides(before), _slides(after)
    problems = []
    if list(old) != list(new):
        problems.append("投影片的數量或順序變了（只准改被點名投影片的 media.prompt）")
    for sid, slide in new.items():
        prev = old.get(sid)
        if prev is None:
            continue
        if sid not in ids:
            if slide != prev:
                problems.append(f"{sid} 沒被點名卻被改了")
            continue
        media_old, media_new = dict(prev.get("media") or {}), dict(slide.get("media") or {})
        if {k: v for k, v in slide.items() if k != "media"} != {k: v for k, v in prev.items() if k != "media"}:
            problems.append(f"{sid}：只准改 media.prompt，旁白或其他欄位被改了")
        if {k: v for k, v in media_new.items() if k != "prompt"} != {k: v for k, v in media_old.items() if k != "prompt"}:
            problems.append(f"{sid}：media 除了 prompt 以外的欄位被改了")
        clash = contradictions(f"{style_prefix} {media_new.get('prompt', '')}")
        if clash:
            problems.append(f"{sid}：提示詞自相矛盾，同時禁止又要求 {', '.join(clash)}（頻道風格前綴：{style_prefix.strip()}）")
    if {k: v for k, v in after.items() if k != "sections"} != {k: v for k, v in before.items() if k != "sections"}:
        problems.append("deck 的標題、說明等頂層欄位被改了")
    return problems


def reject_images(run_dir: Path, ids: list[str]) -> list[str]:
    """Move the flagged slides' images (and sidecars) to ``assets/ai_images/rejected/<id>.<n>.*``."""
    image_dir = run_dir / AI_IMAGE_DIR
    target = image_dir / REJECTED_DIR
    moved = []
    for sid in ids:
        attempt = attempts(run_dir, sid) + 1
        for path in sorted(image_dir.glob(f"{sid}.*")):
            if path.is_file():
                target.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(target / f"{sid}.{attempt}{path.suffix}"))
                moved.append(f"{path.name} → {REJECTED_DIR}/{sid}.{attempt}{path.suffix}")
    return moved


def attempts(run_dir: Path, slide_id: str) -> int:
    """How many images of this slide were rejected so far."""
    target = run_dir / AI_IMAGE_DIR / REJECTED_DIR
    return len({p.name.split(".")[1] for p in target.glob(f"{slide_id}.*.png")}) if target.is_dir() else 0


def seed_for(run_dir: Path, slide_id: str, base: int) -> int:
    return base + attempts(run_dir, slide_id)
