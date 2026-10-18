"""Per-scene render cache: identity hashing and a directory store.

A scene's *identity* is a hash of everything its rendered piece depends on (texts,
media, stage directions, timing, the code that draws it). Same identity = same pixels,
so a re-run reuses the stored piece and only scenes whose identity changed are drawn.
The cache lives inside the run dir (``media/cache``, ``assembly/mascot_cache``) so
deleting a run deletes its cache; deleting the cache only costs a full re-render.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path

KEY_LENGTH = 20


def digest(payload: object) -> str:
    """Stable hash of a JSON-able payload (key order and float repr fixed)."""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:KEY_LENGTH]


def file_digest(path: Path) -> str | None:
    """Content hash of one file (None when missing)."""
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:KEY_LENGTH]


def files_digest(paths: Iterable[Path]) -> dict[str, str | None]:
    return {path.name: file_digest(path) for path in sorted(paths)}


@lru_cache(maxsize=16)
def _tree_digest(root: str, suffixes: tuple[str, ...], skip: tuple[str, ...]) -> str:
    h = hashlib.sha256()
    base = Path(root)
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(base).as_posix()
        if not path.is_file() or path.suffix not in suffixes or any(rel.startswith(s) for s in skip):
            continue
        h.update(rel.encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:KEY_LENGTH]


def code_digest(root: Path, *, suffixes: tuple[str, ...] = (".py", ".html", ".j2", ".css", ".js", ".svg"),
                skip: tuple[str, ...] = ()) -> str:
    """Hash of the source that draws a piece: any code or template edit re-renders everything
    (safe default; the cost is one full render after a code change)."""
    return _tree_digest(str(root.resolve()), suffixes, skip)


class SceneCache:
    """``root/<key>/`` holds one piece: its files plus ``meta.json``."""

    META = "meta.json"

    def __init__(self, root: Path) -> None:
        self.root = root

    def entry(self, key: str) -> Path:
        return self.root / key

    def get(self, key: str) -> dict | None:
        """The stored meta when every file it lists is still there, else None."""
        meta_path = self.entry(key) / self.META
        if not meta_path.is_file():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        files = meta.get("files", [])
        if not all((self.entry(key) / name).is_file() for name in files):
            return None
        return meta

    def put(self, key: str, files: Mapping[str, Path], meta: Mapping, *, move: bool = False) -> dict:
        """Store ``files`` (name in entry -> source) and ``meta``; meta is written last, so a
        crash mid-store leaves an entry ``get`` ignores."""
        entry = self.entry(key)
        entry.mkdir(parents=True, exist_ok=True)
        (entry / self.META).unlink(missing_ok=True)
        for name, source in files.items():
            target = entry / name
            if source.resolve() == target.resolve():
                continue
            tmp = target.with_name(f".{target.name}.part")
            if move:
                shutil.move(str(source), tmp)
            else:
                shutil.copy2(source, tmp)
            os.replace(tmp, target)
        stored = {**meta, "files": sorted(files)}
        (entry / self.META).write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        return stored

    def path(self, key: str, name: str) -> Path:
        return self.entry(key) / name

    def prune(self, keep: Iterable[str]) -> list[str]:
        """Remove entries not in ``keep``; returns the removed keys."""
        keep = set(keep)
        removed = []
        if not self.root.is_dir():
            return removed
        for entry in self.root.iterdir():
            if entry.is_dir() and entry.name not in keep:
                shutil.rmtree(entry, ignore_errors=True)
                removed.append(entry.name)
        return sorted(removed)
