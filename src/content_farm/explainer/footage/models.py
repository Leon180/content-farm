"""Outside-footage candidates and the checks every one must pass before download (Leon 2026-10-24, decision A).

A :class:`FootageCandidate` is what a provider says about one clip; :func:`screen` turns that into an accept / refuse
decision using the licence whitelist (``review.license_rules.classify_license``) and the no-faces rule. Nothing is
downloaded for a refused candidate.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from content_farm.review.license_rules import LicenseVerdict, classify_license

# Real-person close-ups are not used (house rule 避臉). Without a face detector in the venv the screen is metadata only:
# a clip whose title / description / tags name people is refused, and every chosen clip is still flagged for a human look.
FACE_WORDS = frozenset({
    "face", "faces", "portrait", "selfie", "interview", "speaks", "speaking", "talking", "speech", "presenter",
    "reporter", "host", "man", "woman", "boy", "girl", "child", "children", "kid", "kids", "people", "person",
    "crowd", "diver", "divers", "swimmer", "scientist", "scientists", "crew", "astronaut", "astronauts", "team",
    "staff", "visitors", "tourists", "audience", "smile", "smiling",
})


@dataclass(frozen=True)
class FootageCandidate:
    provider: str            # nasa | noaa | wikimedia | pexels | pixabay
    provider_id: str
    title: str
    page_url: str
    download_url: str
    width: int
    height: int
    duration: float
    author: str
    author_url: str
    license_name: str
    license_url: str
    description: str = ""
    tags: str = ""
    size_bytes: int = 0

    @property
    def text(self) -> str:
        """What the provider says the clip shows (for relevance and the no-faces screen)."""
        slug = self.page_url.rstrip("/").rsplit("/", 1)[-1].replace("_", " ").replace("-", " ")
        return f"{self.title} {slug} {self.description} {self.tags}"

    @property
    def screen_label(self) -> str:
        """The on-screen credit, e.g. 「影像：NOAA Ocean Exploration」."""
        return source_label(self)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def short_author(author: str) -> str:
    """Credit name for the frame: NOAA's long institutional strings shrink to the programme name."""
    if re.search(r"ocean exploration|okeanos|\bOER\b", author, re.I):
        return "NOAA Ocean Exploration"
    if re.search(r"NOAA|National Oceanic", author, re.I):
        return "NOAA"
    return author if len(author) <= 40 else author[:38].rstrip() + "…"


def source_label(c: FootageCandidate) -> str:
    """Short, human-readable credit for the corner of the picture (who made it, where it came from, CC licence if any)."""
    names = {"nasa": "NASA", "noaa": "NOAA Ocean Exploration", "wikimedia": "Wikimedia Commons",
             "pexels": "Pexels", "pixabay": "Pixabay"}
    base = names.get(c.provider, c.provider)
    author = short_author(c.author)
    verdict = classify_license(c.license_name, c.license_url)
    if verdict.attribution_required:
        return f"影像：{author} / {base}（{short_licence(c)}）"
    if c.provider in {"nasa", "noaa"} or author == base:
        return f"影像：{base}"
    return f"影像：{author} / {base}"


def short_licence(c: FootageCandidate) -> str:
    verdict = classify_license(c.license_name, c.license_url)
    return {"cc-by": "CC BY", "cc-by-sa": "CC BY-SA"}.get(verdict.code, c.license_name)


def mentions_people(text: str) -> tuple[str, ...]:
    cleaned = re.sub(r"man[\s'-]*o[f']?[\s'-]*war", " ", text.lower())   # Portuguese man o' war is a siphonophore
    return tuple(sorted(set(re.findall(r"[a-z]+", cleaned)) & FACE_WORDS))


@dataclass(frozen=True)
class Screening:
    ok: bool
    reason: str
    verdict: LicenseVerdict


def screen(c: FootageCandidate, *, avoid_faces: bool = True) -> Screening:
    verdict = classify_license(c.license_name, c.license_url)
    if not verdict.ok:
        return Screening(False, verdict.reason, verdict)
    if not c.author.strip():
        return Screening(False, "沒有作者／出處", verdict)
    if not c.page_url.strip():
        return Screening(False, "沒有原始頁面網址", verdict)
    if avoid_faces:
        people = mentions_people(c.text)
        if people:
            return Screening(False, f"標題／說明提到人物（{', '.join(people)}），避臉規則不用", verdict)
    return Screening(True, "", verdict)


def sidecar(c: FootageCandidate, *, retrieved_at: date | None = None) -> dict[str, Any]:
    """The per-clip record kept next to the cached file: source, author, licence, URL, retrieval date."""
    verdict = classify_license(c.license_name, c.license_url)
    return {
        "version": 1,
        **c.to_json(),
        "license": c.license_name,
        "source_url": c.page_url,
        "license_code": verdict.code,
        "attribution_required": verdict.attribution_required,
        "share_alike": verdict.share_alike,
        "retrieved_at": (retrieved_at or date.today()).isoformat(),
    }
