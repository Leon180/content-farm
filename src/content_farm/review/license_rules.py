"""Licence check as program rules (Leon 2026-10-24: no panel for the media gate any more).

Rules, all on ``credits.json``:
- every entry's ``kind`` is on the source whitelist (``review.license_rules.allowed_kinds`` in review_panels.yaml);
- nothing is still ``pending``;
- every entry has a licence; stock needs a ``source_url``; artwork needs a ``license_url`` and no non-commercial licence;
- every AI frame carries the 「AI 示意圖」 badge and records model / prompt / seed, and no prompt asks for photo-realism
  or an artist's style (``production.qc.ai_image_findings``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from content_farm.review.config import PANELS_FILE

DEFAULT_ALLOWED_KINDS = ("ai_image", "artwork", "stock", "wikimedia", "news_card", "title_card", "parallax", "wan",
                         "article", "discussion")
_NON_COMMERCIAL = ("nc", "non-commercial", "noncommercial")


def allowed_kinds(path: Path = PANELS_FILE) -> tuple[str, ...]:
    raw = (yaml.safe_load(path.read_text(encoding="utf-8")).get("review") or {}).get("license_rules") or {}
    return tuple(raw.get("allowed_kinds") or DEFAULT_ALLOWED_KINDS)


def problems(credits: dict[str, Any] | None, allowed: tuple[str, ...] | None = None) -> list[str]:
    """Why ``credits`` may not ship ([] = fine)."""
    if credits is None:
        return ["credits.json 不存在（先跑 media）"]
    allowed = allowed or allowed_kinds()
    entries = credits.get("entries") or []
    out: list[str] = []
    if credits.get("pending"):
        out.append(f"還有 {len(credits['pending'])} 筆授權未確定")
    off_list = sorted({str(e.get("kind")) for e in entries if e.get("kind") not in allowed})
    if off_list:
        out.append(f"素材來源不在白名單：{', '.join(off_list)}")
    for e in entries:
        sid, kind, licence = e.get("slide_id", "?"), e.get("kind"), str(e.get("license") or "")
        if not licence:
            out.append(f"{sid}: 沒有授權")
        if kind == "stock" and not e.get("source_url"):
            out.append(f"{sid}: stock 沒有 source_url")
        if kind == "artwork" and (not e.get("license_url") or any(n in licence.lower() for n in _NON_COMMERCIAL)):
            out.append(f"{sid}: artwork 授權不可營利或缺授權網址")
    from content_farm.production.qc import ai_image_findings

    out += [f.message for f in ai_image_findings(entries) if f.level == "error"]
    return out


def check(run_dir: Path) -> list[str]:
    path = run_dir / "credits.json"
    return problems(json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None)
