"""Compare a read-back videos resource with the metadata we meant to send."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from content_farm.youtube.pack import PackItem


@dataclass(frozen=True)
class FieldCheck:
    field: str
    expected: Any
    actual: Any

    @property
    def ok(self) -> bool:
        return self.expected == self.actual


def compare_video(item: PackItem, video: dict[str, Any]) -> list[FieldCheck]:
    """Field-by-field comparison. ``video`` is one item of a videos.list(snippet,status) response."""
    snippet = video.get("snippet", {})
    status = video.get("status", {})
    return [
        FieldCheck("title", item.title, snippet.get("title")),
        FieldCheck("description", item.description.strip(), snippet.get("description", "").strip()),
        # YouTube returns tags in its own (sorted) order, so compare as sets.
        FieldCheck("tags", sorted(item.tags), sorted(snippet.get("tags", []))),
        FieldCheck("categoryId", item.category_id, snippet.get("categoryId")),
        FieldCheck("defaultLanguage", "zh-TW", snippet.get("defaultLanguage")),
        FieldCheck("madeForKids", False, status.get("madeForKids")),
        FieldCheck("selfDeclaredMadeForKids", False, status.get("selfDeclaredMadeForKids")),
        FieldCheck(
            "containsSyntheticMedia",
            item.contains_synthetic_media,
            status.get("containsSyntheticMedia", False),
        ),
        FieldCheck("privacyStatus", "private", status.get("privacyStatus")),
    ]
