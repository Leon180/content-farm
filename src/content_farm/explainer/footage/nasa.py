"""NASA Image and Video Library (images-api.nasa.gov, no key).

NASA media are generally not copyrighted (https://www.nasa.gov/nasa-brand-center/images-and-media/), but the library also
carries third-party material. A record is accepted only when nothing in its text points at someone else's rights; the
page URL (``images.nasa.gov/details/<id>``) is kept so a human can re-check the credit line.
"""

from __future__ import annotations

import re
from typing import Any

from content_farm.explainer.footage.models import FootageCandidate

SEARCH = "https://images-api.nasa.gov/search"
ASSET = "https://images-api.nasa.gov/asset/"
DETAILS = "https://images.nasa.gov/details/"
LICENSE = ("Public domain (NASA media usage guidelines)",
           "https://www.nasa.gov/nasa-brand-center/images-and-media/")
_THIRD_PARTY = re.compile(
    r"copyright|©|\(c\)|all rights|permission|licen[sc]ed|getty|shutterstock|reuters|associated press|"
    r"\bAP\b|used with|trademark|courtesy of (?!nasa|jpl|esa/nasa|the nasa)", re.I)
_RANK = ("~orig.mp4", "~large.mp4", "~medium.mp4", "~mobile.mp4")


def search_params(query: str, limit: int = 20) -> dict[str, Any]:
    return {"q": query, "media_type": "video", "page_size": limit}


def third_party_marker(text: str) -> str | None:
    match = _THIRD_PARTY.search(text)
    return match.group(0) if match else None


def parse(data: dict) -> list[FootageCandidate]:
    """Search hits → candidates (``download_url`` is filled by :func:`pick_file` from the asset manifest)."""
    out: list[FootageCandidate] = []
    for item in (data.get("collection") or {}).get("items") or []:
        meta = (item.get("data") or [{}])[0]
        nasa_id = str(meta.get("nasa_id", ""))
        if not nasa_id or meta.get("media_type") != "video":
            continue
        text = f"{meta.get('title', '')} {meta.get('description', '')} {meta.get('secondary_creator', '')}"
        marker = third_party_marker(text)
        centre = str(meta.get("center") or "").strip()
        author = str(meta.get("secondary_creator") or "").strip()
        out.append(FootageCandidate(
            provider="nasa",
            provider_id=nasa_id,
            title=str(meta.get("title", "")),
            page_url=DETAILS + nasa_id,
            download_url=str(item.get("href", "")),   # collection.json (resolved to a file later)
            width=0, height=0, duration=0,
            author=f"NASA{f' {centre}' if centre else ''}" if not author else f"NASA / {author}",
            author_url="https://www.nasa.gov",
            license_name=LICENSE[0] if marker is None else f"Third-party rights suspected ({marker})",
            license_url=LICENSE[1],
            description=str(meta.get("description", ""))[:400],
            tags=", ".join(meta.get("keywords") or []),
        ))
    return out


def pick_file(files: list[str]) -> str | None:
    """Best mp4 from a NASA asset manifest (the list of file URLs): original-ish first, never the preview."""
    usable = [f for f in files if f.lower().endswith(".mp4") and "~preview" not in f.lower()]
    for suffix in _RANK:
        for f in usable:
            if f.lower().endswith(suffix):
                return f.replace("http://", "https://")
    return usable[0].replace("http://", "https://") if usable else None
