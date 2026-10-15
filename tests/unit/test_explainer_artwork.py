"""Public-domain / museum artwork as a media kind (yokai channel)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from content_farm.explainer import ffmpeg_ops
from content_farm.explainer.artwork import (
    ARTWORK_DIR,
    ARTWORK_MANIFEST,
    ArtworkEntry,
    artwork_credits_text,
    credit_for,
    load_manifest,
)
from content_farm.explainer.deck import Media, MediaKind
from content_farm.explainer.media_run import credits_text

ENTRY = {
    "file": "tamamo.jpg",
    "title": "玉藻前（今昔畫圖續百鬼）",
    "artist": "鳥山石燕",
    "date": "1779",
    "institution": "Wikimedia Commons",
    "object_id": "File:SekienTamamo.jpg",
    "license": "Public domain",
    "license_url": "https://creativecommons.org/publicdomain/mark/1.0/",
    "source_url": "https://commons.wikimedia.org/wiki/File:SekienTamamo.jpg",
    "caption": "鳥山石燕〈玉藻前〉1779",
}


def _write_manifest(run_dir: Path, entries: dict) -> None:
    path = run_dir / ARTWORK_DIR / ARTWORK_MANIFEST
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def test_media_artwork_requires_an_id() -> None:
    with pytest.raises(ValidationError, match="artwork"):
        Media(kind=MediaKind.ARTWORK)
    assert Media(kind=MediaKind.ARTWORK, artwork="tamamo").artwork == "tamamo"


@pytest.mark.parametrize("licence", ["CC BY-NC-SA 4.0", "Non-commercial use only"])
def test_non_commercial_licence_rejected(licence: str) -> None:
    with pytest.raises(ValidationError, match="commercial"):
        ArtworkEntry.model_validate({**ENTRY, "license": licence})


@pytest.mark.parametrize("field", ["license_url", "source_url", "artist"])
def test_provenance_fields_required(field: str) -> None:
    with pytest.raises(ValidationError):
        ArtworkEntry.model_validate({**ENTRY, field: ""})


def test_load_manifest_and_credit(tmp_path: Path) -> None:
    _write_manifest(tmp_path, {"tamamo": ENTRY})
    manifest = load_manifest(tmp_path)
    image = tmp_path / ARTWORK_DIR / "tamamo.jpg"
    image.write_bytes(b"jpg")
    assert manifest["tamamo"].path(tmp_path) == image

    credit = credit_for(manifest["tamamo"], "tamamo", slide_id="s05", index=5)
    assert credit["kind"] == "artwork"
    assert credit["license_url"] == ENTRY["license_url"]
    assert credit["source_url"] == ENTRY["source_url"]
    assert credit["artwork_id"] == "tamamo"


def test_missing_manifest_is_empty(tmp_path: Path) -> None:
    assert load_manifest(tmp_path) == {}


def test_bad_manifest_raises(tmp_path: Path) -> None:
    _write_manifest(tmp_path, {"tamamo": {**ENTRY, "license": "CC BY-NC 4.0"}})
    with pytest.raises(ValueError, match="tamamo"):
        load_manifest(tmp_path)


def test_credits_text_lists_artwork_once_per_work() -> None:
    credit = credit_for(ArtworkEntry.model_validate(ENTRY), "tamamo", slide_id="s05", index=5)
    again = {**credit, "slide_id": "s09", "slide_index": 9}
    text = artwork_credits_text([credit, again])
    assert text.count("鳥山石燕") == 1
    assert ENTRY["source_url"] in text and "Public domain" in text
    assert "鳥山石燕" in credits_text([credit])


def test_credits_text_without_artwork_unchanged() -> None:
    assert artwork_credits_text([]) == ""
    assert credits_text([]) == ""


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_artwork_plate_keeps_a_tall_scroll_whole(tmp_path: Path) -> None:
    scroll = tmp_path / "scroll.png"
    Image.new("RGB", (300, 1200), (200, 30, 30)).save(scroll)
    out = ffmpeg_ops.artwork_plate(scroll, None, tmp_path / "clip.mp4", 0.5)
    info = ffmpeg_ops.probe(out)
    assert (info["width"], info["height"]) == (ffmpeg_ops.WIDTH, ffmpeg_ops.HEIGHT)
    frame = Image.open(ffmpeg_ops.first_frame(out, tmp_path / "f.png")).convert("RGB")
    # top and bottom of the scroll are inside the frame (fit, not cover-crop)
    assert frame.getpixel((960, 90))[0] > 150
    assert frame.getpixel((960, 840))[0] > 150
    # the sides are the darkened blur, not the scroll itself
    assert frame.getpixel((100, 540))[0] < 150
