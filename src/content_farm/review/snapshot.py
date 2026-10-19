"""Keep the exact version each review round judged: ``review/<stage>/round-N/snapshot/<path>``.

A stage's ``reviews`` files (the fingerprinted inputs, e.g. ``deck.json``) are overwritten by every
rework, so without a copy there is no way back to the version a round scored best (2026-10-19:
the 九尾狐 deck that scored 7.2/7.0 was gone one rewrite later). Only text-like files are kept —
videos and images are large and are rebuilt from the text files plus the step cache.
"""

from __future__ import annotations

import shutil
from pathlib import Path

SNAPSHOT_DIR = "snapshot"
TEXT_SUFFIXES = (".json", ".md", ".txt")
MAX_BYTES = 5 * 1024 * 1024


def snapshot_reviewed(run_dir: Path, round_dir: Path, patterns: tuple[str, ...]) -> list[str]:
    """Copy the reviewed text files into ``round_dir/snapshot/``; returns their run-dir paths."""
    kept: list[str] = []
    for pattern in patterns:
        for src in sorted(run_dir.glob(pattern)):
            if not src.is_file() or src.suffix not in TEXT_SUFFIXES or src.stat().st_size > MAX_BYTES:
                continue
            rel = src.relative_to(run_dir)
            target = round_dir / SNAPSHOT_DIR / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            kept.append(rel.as_posix())
    return kept


def restore(round_dir: Path, run_dir: Path) -> list[str]:
    """Put a round's snapshot back into the run-dir (e.g. to restart from the best-scored deck)."""
    base = round_dir / SNAPSHOT_DIR
    if not base.is_dir():
        raise FileNotFoundError(f"{round_dir}: no {SNAPSHOT_DIR}/ (round predates snapshots)")
    restored = []
    for src in sorted(p for p in base.rglob("*") if p.is_file()):
        rel = src.relative_to(base)
        target = run_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        restored.append(rel.as_posix())
    return restored
