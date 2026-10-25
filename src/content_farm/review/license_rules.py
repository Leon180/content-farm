"""Licence check as program rules (Leon 2026-10-24: no panel for the media gate any more).

Rules, all on ``credits.json``:
- every entry's ``kind`` is on the source whitelist (``review.license_rules.allowed_kinds`` in review_panels.yaml);
- nothing is still ``pending``;
- every entry has a licence; stock needs a ``source_url``; artwork needs a ``license_url`` and no non-commercial licence;
- every AI frame carries the 「AI 示意圖」 badge and records model / prompt / seed, and no prompt asks for photo-realism
  or an artist's style (``production.qc.ai_image_findings``).

Outside footage (``kind: stock_video``, Leon 2026-10-24 decision bdce0ad57f09 = A): only free-to-use licences go on
screen — public domain, CC0, CC BY, CC BY-SA and the Pexels / Pixabay licences. Anything NC / ND / unknown is refused
(:func:`classify_license`). Every clip needs a sidecar (source, author, licence, URL, retrieved date), a source label burned
into the frame, and — for CC BY / BY-SA — the credit line in the description (:func:`footage_problems`).
Copyrighted web video (YouTube, MBARI, TV stations…) never goes on screen; it is linked from ``reference_links`` only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from content_farm.review.config import PANELS_FILE

DEFAULT_ALLOWED_KINDS = ("ai_image", "artwork", "stock", "stock_video", "wikimedia", "news_card", "title_card",
                         "parallax", "wan", "article", "discussion")
_NON_COMMERCIAL = ("nc", "non-commercial", "noncommercial")
FOOTAGE_KIND = "stock_video"
SIDECAR_FIELDS = ("provider", "author", "license", "source_url", "retrieved_at")


@dataclass(frozen=True)
class LicenseVerdict:
    ok: bool
    code: str                       # normalised: pd | cc0 | cc-by | cc-by-sa | pexels | pixabay | "" when refused
    attribution_required: bool      # CC BY / BY-SA: label on screen AND credit line in the description
    share_alike: bool
    reason: str = ""


def _refuse(reason: str) -> LicenseVerdict:
    return LicenseVerdict(False, "", False, False, reason)


def classify_license(name: str, url: str = "") -> LicenseVerdict:
    """Is ``name`` (a Commons ``LicenseShortName``, an API's licence string…) one we may put on screen?

    Whitelist: public domain (incl. US-government works), CC0, CC BY, CC BY-SA, Pexels, Pixabay.
    Refused: any NC / ND variant, GFDL-only, fair use, all rights reserved, and everything unrecognised.
    """
    text = f"{name} {url}".lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    if not name.strip():
        return _refuse("沒有授權標示")
    if tokens & {"nc", "nd", "noncommercial"} or "non-commercial" in text or "no derivative" in text \
            or "noderivs" in text or "by-nc" in text or "by-nd" in text:
        return _refuse(f"授權含 NC／ND：{name!r}")
    if "fair use" in text or "all rights reserved" in text or ("copyright" in tokens and "public" not in tokens):
        return _refuse(f"版權保留或合理使用：{name!r}")
    if "pexels" in tokens:
        return LicenseVerdict(True, "pexels", False, False)
    if "pixabay" in tokens:
        return LicenseVerdict(True, "pixabay", False, False)
    if "cc0" in tokens or ("zero" in tokens and "cc" in tokens):
        return LicenseVerdict(True, "cc0", False, False)
    if ("public" in tokens and "domain" in tokens) or "pd" in tokens:
        return LicenseVerdict(True, "pd", False, False)
    is_cc = "cc" in tokens or "creativecommons" in tokens or "creative" in tokens
    has_by = "by" in tokens or "attribution" in tokens
    if (is_cc or "attribution" in tokens) and has_by:
        if "sa" in tokens or "sharealike" in tokens or "share" in tokens:
            return LicenseVerdict(True, "cc-by-sa", True, True)
        return LicenseVerdict(True, "cc-by", True, False)
    return _refuse(f"授權不在白名單：{name!r}")


def allowed_kinds(path: Path = PANELS_FILE) -> tuple[str, ...]:
    raw = (yaml.safe_load(path.read_text(encoding="utf-8")).get("review") or {}).get("license_rules") or {}
    return tuple(raw.get("allowed_kinds") or DEFAULT_ALLOWED_KINDS)


def footage_problems(entry: dict[str, Any], description_text: str = "", run_dir: Path | None = None) -> list[str]:
    """Why one ``stock_video`` credits entry may not ship ([] = fine)."""
    sid = entry.get("slide_id", "?")
    out: list[str] = []
    missing = [f for f in SIDECAR_FIELDS if not str(entry.get(f) or "").strip()]
    if missing:
        out.append(f"{sid}: 素材 sidecar 缺 {', '.join(missing)}")
    verdict = classify_license(str(entry.get("license") or ""), str(entry.get("license_url") or ""))
    if not verdict.ok:
        out.append(f"{sid}: {verdict.reason}")
    if not (entry.get("label") and entry.get("label_burned")):
        out.append(f"{sid}: 畫面沒有來源標示（label／label_burned）")
    if verdict.attribution_required:
        source_url = str(entry.get("source_url") or "")
        if source_url and source_url not in description_text:
            out.append(f"{sid}: {verdict.code.upper()} 素材沒有列在說明欄（缺 {source_url}）")
    if run_dir is not None:
        sidecar = str(entry.get("sidecar") or "")
        if not sidecar or not (run_dir / sidecar).is_file():
            out.append(f"{sid}: sidecar 檔不存在（{sidecar or '未記錄'}）")
    return out


def problems(credits: dict[str, Any] | None, allowed: tuple[str, ...] | None = None,
             run_dir: Path | None = None) -> list[str]:
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
    description = str(credits.get("description_text") or "")
    for e in entries:
        sid, kind, licence = e.get("slide_id", "?"), e.get("kind"), str(e.get("license") or "")
        if kind == FOOTAGE_KIND:
            out += footage_problems(e, description, run_dir)
            continue
        if not licence:
            out.append(f"{sid}: 沒有授權")
        if kind == "stock" and not e.get("source_url"):
            out.append(f"{sid}: stock 沒有 source_url")
        if kind == "artwork" and (not e.get("license_url") or any(n in licence.lower() for n in _NON_COMMERCIAL)):
            out.append(f"{sid}: artwork 授權不可營利或缺授權網址")
    from content_farm.explainer.wan import run_limit
    from content_farm.production.qc import ai_image_findings

    out += [f.message for f in ai_image_findings(entries, run_limit(run_dir)) if f.level == "error"]
    return out


def check(run_dir: Path) -> list[str]:
    path = run_dir / "credits.json"
    return problems(json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None, run_dir=run_dir)
