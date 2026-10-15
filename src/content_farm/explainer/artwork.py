"""Museum / public-domain artwork for ``media.kind == "artwork"`` slides — file contract.

A run keeps its artwork in ``<run_dir>/assets/artwork/`` next to a manifest
``artwork.json`` that maps an artwork id (what ``slide.media.artwork`` names)
to the image file and its provenance. Every entry must say where the image
came from and under which licence, with a link to each; non-commercial
licences are refused here, before anything is rendered, because the channel
is meant to be monetised.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

ARTWORK_DIR = Path("assets") / "artwork"
ARTWORK_MANIFEST = "artwork.json"
_NON_COMMERCIAL = re.compile(r"\bNC\b|non-?commercial", re.IGNORECASE)


class ArtworkEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    file: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    artist: str = Field(min_length=1, max_length=100)
    date: str = Field(min_length=1, max_length=40)
    institution: str = Field(min_length=1, max_length=120)  # holding museum or repository
    object_id: str = Field(default="", max_length=200)
    license: str = Field(min_length=1, max_length=120)
    license_url: str = Field(pattern=r"^https?://")
    source_url: str = Field(pattern=r"^https?://")
    caption: str = Field(min_length=1, max_length=40)       # shown on screen
    note: str = ""

    @field_validator("license")
    @classmethod
    def _commercial_use(cls, value: str) -> str:
        if _NON_COMMERCIAL.search(value):
            raise ValueError(f"licence {value!r} forbids commercial use")
        return value

    def path(self, run_dir: Path) -> Path:
        return run_dir / ARTWORK_DIR / self.file


def load_manifest(run_dir: Path) -> dict[str, ArtworkEntry]:
    path = run_dir / ARTWORK_DIR / ARTWORK_MANIFEST
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    manifest: dict[str, ArtworkEntry] = {}
    for artwork_id, data in raw.items():
        try:
            manifest[artwork_id] = ArtworkEntry.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"{path}: artwork {artwork_id!r} invalid: {exc}") from exc
    return manifest


def credit_for(entry: ArtworkEntry, artwork_id: str, *, slide_id: str, index: int) -> dict:
    return {"slide_id": slide_id, "slide_index": index, "kind": "artwork", "artwork_id": artwork_id,
            **entry.model_dump(exclude={"caption", "note"})}


def artwork_credits_text(entries: Sequence[dict]) -> str:
    """One line per distinct work, however many slides show it."""
    seen: dict[str, dict] = {}
    for entry in entries:
        if entry.get("kind") == "artwork":
            seen.setdefault(entry["artwork_id"], entry)
    if not seen:
        return ""
    lines = ["畫作 / Artwork:"]
    for e in seen.values():
        lines.append(f"- {e['artist']}〈{e['title']}〉{e['date']}, {e['institution']}: "
                     f"{e['source_url']} ({e['license']})")
    return "\n".join(lines)
