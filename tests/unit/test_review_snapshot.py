"""Each review round keeps the exact files it judged, so a later cycle can restart from it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.review.snapshot import SNAPSHOT_DIR, restore, snapshot_reviewed
from tests.unit.test_production_runner import run_dir as run_dir  # noqa: F401  (fixture)
from tests.unit.test_review_script_stages import Panel, _runner


def test_snapshot_keeps_text_files_and_skips_media(tmp_path: Path) -> None:
    run, out = tmp_path / "run", tmp_path / "round-1"
    (run / "slides").mkdir(parents=True)
    (run / "deck.json").write_text('{"v": 1}', encoding="utf-8")
    (run / "slides" / "contact_sheet.png").write_bytes(b"\x89PNG")
    kept = snapshot_reviewed(run, out, ("deck.json", "slides/contact_sheet.png", "missing/*.json"))
    assert kept == ["deck.json"]
    assert (out / SNAPSHOT_DIR / "deck.json").read_text(encoding="utf-8") == '{"v": 1}'
    assert not (out / SNAPSHOT_DIR / "slides").exists()


def test_restore_puts_the_judged_version_back(tmp_path: Path) -> None:
    run, out = tmp_path / "run", tmp_path / "round-3"
    run.mkdir()
    (run / "deck.json").write_text('{"v": "judged"}', encoding="utf-8")
    snapshot_reviewed(run, out, ("deck.json",))
    (run / "deck.json").write_text('{"v": "rewritten"}', encoding="utf-8")
    assert restore(out, run) == ["deck.json"]
    assert json.loads((run / "deck.json").read_text(encoding="utf-8")) == {"v": "judged"}


def test_restore_without_snapshot_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no snapshot"):
        restore(tmp_path / "round-1", tmp_path)


def test_every_script_round_snapshots_the_deck_it_judged(run_dir: Path) -> None:  # noqa: F811
    judged = (run_dir / "deck.json").read_bytes()
    _runner(run_dir, Panel(writer=5)).run(until="gate_deck_facts")       # structure round 1 fails → rework
    snap = run_dir / "review" / "script_structure" / "round-1" / SNAPSHOT_DIR / "deck.json"
    assert snap.read_bytes() == judged
