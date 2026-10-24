"""Parse an upload pack (INDEX.md + per-video metadata.md) into upload plans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from content_farm.youtube.channel_tokens import CHANNELS, normalize_channel
from content_farm.youtube.schemas import UploadSettings

TITLE_MAX_CHARS = 100
DESCRIPTION_MAX_BYTES = 5000  # YouTube counts bytes, not characters
TAGS_MAX_CHARS = 500

_CATEGORY_IDS = {"教育": "27", "科學與技術": "28"}
_CHANNEL_ID_RE = re.compile(r"（([A-Za-z]+)[，）]")
_FENCE_RE = re.compile(r"```text\n(.*?)\n```", re.DOTALL)
_SKIP_MARK = "不建議上傳"
_INDEX_FILE_RE = re.compile(r"([^/\s]+)/video\.mp4")


_ANGLE_TABLE = str.maketrans({"<": "＜", ">": "＞"})


def sanitize_angle_brackets(text: str) -> tuple[str, int]:
    """YouTube rejects ``<``/``>`` in title, description and tags; use full-width forms."""
    count = text.count("<") + text.count(">")
    return text.translate(_ANGLE_TABLE), count


@dataclass(frozen=True)
class PackItem:
    """One video ready to be planned or uploaded."""

    folder: Path
    channel: str
    title: str
    description: str
    tags: tuple[str, ...]
    category_id: str
    contains_synthetic_media: bool | None
    video_path: Path
    thumbnail_path: Path | None
    pinned_comment_path: Path | None
    listed_in_index: bool
    index_note: str = ""
    notes: tuple[str, ...] = ()

    @property
    def description_bytes(self) -> int:
        return len(self.description.encode("utf-8"))

    @property
    def is_short(self) -> bool:
        return self.thumbnail_path is None

    def settings(self) -> UploadSettings:
        """Upload settings. Always private: unaudited API projects can't publish."""
        return UploadSettings(
            privacy_status="private",
            category_id=self.category_id,
            made_for_kids=False,
            contains_synthetic_media=self.contains_synthetic_media,
        )

    def problems(self) -> tuple[str, ...]:
        """Blocking issues (YouTube would reject, or the file is missing)."""
        found: list[str] = []
        if not self.video_path.is_file():
            found.append(f"missing video: {self.video_path}")
        if not self.title:
            found.append("empty title")
        if len(self.title) > TITLE_MAX_CHARS:
            found.append(f"title {len(self.title)} > {TITLE_MAX_CHARS} chars")
        if self.description_bytes > DESCRIPTION_MAX_BYTES:
            found.append(f"description {self.description_bytes} > {DESCRIPTION_MAX_BYTES} bytes")
        if len(",".join(self.tags)) > TAGS_MAX_CHARS:
            found.append(f"tags exceed {TAGS_MAX_CHARS} chars")
        if self.contains_synthetic_media is None:
            found.append("synthetic-media flag not found in metadata.md")
        return tuple(found)


def parse_index(index_path: Path) -> tuple[list[tuple[str, str]], set[str]]:
    """Return ``([(folder, note), ...] in INDEX order, {folders marked do-not-upload})``."""
    rows: list[tuple[str, str]] = []
    skipped: set[str] = set()
    for line in index_path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        found = _INDEX_FILE_RE.match(cells[4]) if len(cells) >= 7 else None
        if not found:
            continue
        if _SKIP_MARK in line:
            skipped.add(found.group(1))
        else:
            rows.append((found.group(1), cells[6]))
    return rows, skipped


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1) if match else ""


def _table_value(text: str, key: str) -> str:
    match = re.search(rf"^\|\s*{re.escape(key)}\s*\|\s*(.*?)\s*\|\s*$", text, re.M)
    return match.group(1) if match else ""


def _parse_channel(text: str, folder: str) -> str:
    header = text.splitlines()[0] if text else ""
    found = _CHANNEL_ID_RE.search(header)
    candidate = found.group(1) if found else folder.split("-")[0]
    try:
        return normalize_channel(candidate)
    except ValueError as err:
        raise ValueError(f"{folder}: cannot determine channel ({err})") from err


def _parse_synthetic(text: str) -> bool | None:
    raw = _table_value(text, "「經過修改或合成的內容」")
    if raw.startswith("**是"):
        return True
    if raw.startswith("**否"):
        return False
    return None


def _parse_title(text: str) -> str:
    for line in _section(text, "標題").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _parse_tags(text: str) -> tuple[str, ...]:
    body = " ".join(line.strip() for line in _section(text, "標籤").splitlines() if line.strip())
    return tuple(t.strip() for t in re.split(r"[,，、]", body) if t.strip())


def _parse_description(text: str) -> str:
    match = _FENCE_RE.search(_section(text, "說明欄"))
    return match.group(1).strip() if match else ""


def parse_metadata(folder: Path, *, listed_in_index: bool, note: str = "") -> PackItem:
    """Build a PackItem from ``folder/metadata.md`` and the files next to it."""
    text = (folder / "metadata.md").read_text(encoding="utf-8")
    thumb = folder / "thumbnail.jpg"
    pinned = folder / "pinned-comment.txt"
    title, title_n = sanitize_angle_brackets(_parse_title(text))
    description, desc_n = sanitize_angle_brackets(_parse_description(text))
    tags_raw = _parse_tags(text)
    tags_clean = tuple(sanitize_angle_brackets(t)[0] for t in tags_raw)
    notes = tuple(
        f"replaced < > with full-width in {name} ({n} char(s))"
        for name, n in (("title", title_n), ("description", desc_n),
                        ("tags", sum(a != b for a, b in zip(tags_raw, tags_clean))))
        if n
    )
    return PackItem(
        folder=folder,
        channel=_parse_channel(text, folder.name),
        title=title,
        description=description,
        tags=tags_clean,
        notes=notes,
        category_id=_CATEGORY_IDS.get(
            re.split(r"[（(]", _table_value(text, "類別"))[0].strip(), "22"
        ),
        contains_synthetic_media=_parse_synthetic(text),
        video_path=folder / "video.mp4",
        thumbnail_path=thumb if thumb.is_file() else None,
        pinned_comment_path=pinned if pinned.is_file() else None,
        listed_in_index=listed_in_index,
        index_note=note,
    )


def load_pack(
    pack_dir: Path,
    *,
    only: str | list[str] | None = None,
    limit: int | None = None,
    include_unlisted: bool = False,
) -> list[PackItem]:
    """Load items in INDEX order; optionally append folders INDEX doesn't list."""
    listed, skipped = parse_index(pack_dir / "INDEX.md")
    items = [
        parse_metadata(pack_dir / name, listed_in_index=True, note=note) for name, note in listed
    ]
    if include_unlisted:
        known = {name for name, _ in listed} | skipped
        extras = sorted(
            p for p in pack_dir.iterdir()
            if p.is_dir() and p.name not in known and (p / "metadata.md").is_file()
        )
        items += [parse_metadata(p, listed_in_index=False) for p in extras]
    if only:
        wanted = [only] if isinstance(only, str) else list(only)
        missing = [w for w in wanted if w not in {i.folder.name for i in items}]
        if missing:
            raise ValueError(f"--only {missing!r}: no such folder in the pack")
        items = [i for i in items if i.folder.name in wanted]
    return items[:limit] if limit is not None else items


def channels_in(items: list[PackItem]) -> tuple[str, ...]:
    """Channels used by the items, in canonical order."""
    used = {i.channel for i in items}
    return tuple(c for c in CHANNELS if c in used)
