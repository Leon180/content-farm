"""Subject share of a thumbnail is measured from its HTML, for every layout (yokai-kyubi-v2, 2026-10-19:
the panel layout's picture was not matched by the selector and scored 0.0 whatever the image)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from content_farm.evaluation.homepage import measure_page
from content_farm.production.channels import load_channel
from content_farm.production.thumbnail import ThumbnailSpec, thumbnail_html

pytest.importorskip("playwright.sync_api")

FRAME = 1280 * 720


def _share(tmp_path: Path, layout: str, size: tuple[int, int]) -> float:
    image = tmp_path / f"art_{size[0]}x{size[1]}.png"
    Image.new("RGB", size, (180, 120, 60)).save(image)
    spec = ThumbnailSpec(lines=("九尾狐", "會吃人？"), highlight="吃人", promise=("牠會吃人",), layout=layout,
                         visual={"kind": "image", "path": image.name})
    html = tmp_path / f"{layout}_{size[0]}x{size[1]}.html"
    html.write_text(thumbnail_html(spec, load_channel("yokai"), image.resolve().as_uri()), encoding="utf-8")
    return measure_page(html)["subject_area"] / FRAME


@pytest.mark.parametrize(("size", "expected"), [
    ((800, 800), 560 * 560 / FRAME),     # square painting fills the 560x560 panel
    ((1600, 900), 560 * 315 / FRAME),    # 16:9 is letterboxed by object-fit: contain
    ((600, 1200), 280 * 560 / FRAME),    # tall scroll painting is pillarboxed
])
def test_panel_layout_counts_its_picture(tmp_path: Path, size: tuple[int, int], expected: float) -> None:
    assert _share(tmp_path, "panel", size) == pytest.approx(expected, abs=0.002)


def test_keyart_and_character_unchanged(tmp_path: Path) -> None:
    assert _share(tmp_path, "keyart", (800, 1200)) == pytest.approx(1.0)
    assert _share(tmp_path, "character", (800, 1200)) == pytest.approx(720 * 680 / FRAME)
