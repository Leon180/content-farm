"""Pictures of slides that a later deck merged away are not delivered: not reviewed, not asked for credits."""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.review import materials


def _run_dir(tmp_path: Path, report_slides: list[str] | None) -> Path:
    images = tmp_path / "assets" / "ai_images"
    images.mkdir(parents=True)
    for name in ("s06", "s08b", "s10"):
        (images / f"{name}.png").write_bytes(name.encode())
    if report_slides is not None:
        (tmp_path / "media").mkdir()
        (tmp_path / "media" / "media_report.json").write_text(
            json.dumps({"slides": [{"slide_id": s, "identity": "x"} for s in report_slides]}), encoding="utf-8")
    return tmp_path


def test_images_of_slides_missing_from_the_media_report_are_not_listed(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path, ["s06", "s08"])
    assert [p.stem for p in materials._live_ai_images(run_dir)] == ["s06"]


def test_orphans_do_not_change_the_media_identity(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path, ["s06"])
    before = materials._media_identity(run_dir)
    (run_dir / "assets" / "ai_images" / "s10.png").write_bytes(b"changed")
    assert materials._media_identity(run_dir) == before


def test_without_a_report_every_picture_is_listed(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path, None)
    assert [p.stem for p in materials._live_ai_images(run_dir)] == ["s06", "s08b", "s10"]
