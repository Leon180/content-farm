"""Thumbnail layouts (character / keyart / compare), A/B variants and Shorts covers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from content_farm.production import thumbnail as th
from content_farm.production.channels import load_channel

KEYART = {"lines": ["一條尾巴？"], "visual": {"kind": "image", "path": "art.png"}, "promise": ["一條尾巴"],
          "layout": "keyart"}
COMPARE = {"lines": ["多大？"], "visual": {"kind": "mascot", "pose": "shocked"}, "promise": ["7,722"],
           "layout": "compare", "compare": [{"value": "7,722", "label": "mm²"}]}


def _run(tmp_path: Path, variants: dict, narration: str, *, vertical: bool = False) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / th.VARIANTS_FILE).write_text(json.dumps({"vertical": vertical, "variants": variants},
                                                        ensure_ascii=False), encoding="utf-8")
    scenes = [{"narration": narration, "duration_seconds": 20.0}]
    (tmp_path / "script.json").write_text(json.dumps({"scenes": scenes}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "thumbnails").mkdir(exist_ok=True)
    return tmp_path


def test_layouts_validate_their_inputs() -> None:
    assert th.ThumbnailSpec.model_validate(KEYART).layout == "keyart"
    assert th.ThumbnailSpec.model_validate(COMPARE).compare[0].value == "7,722"
    with pytest.raises(ValidationError, match="compare"):
        th.ThumbnailSpec.model_validate({**COMPARE, "compare": []})
    with pytest.raises(ValidationError, match="image visual"):
        th.ThumbnailSpec.model_validate({**KEYART, "visual": {"kind": "brand"}})
    assert th.ThumbnailSpec.model_validate({**KEYART, "layout": "character"}).layout == "character"   # default kept


def test_compare_numbers_must_be_in_the_narration(tmp_path: Path) -> None:
    spec = th.ThumbnailSpec.model_validate(COMPARE)
    ok = _run(tmp_path / "ok", {"c": COMPARE}, "中介層面積是 7722 平方毫米。")   # thousands separator is fine
    assert th.promise_findings(ok, spec) == []
    bad = th.ThumbnailSpec.model_validate({**COMPARE, "compare": [{"value": "9", "label": "倍"}, {"value": "1"}]})
    msgs = [f.message for f in th.promise_findings(ok, bad, "variant c")]
    assert any("variant c" in m and "9" in m for m in msgs)


def test_variant_findings_check_every_variant(tmp_path: Path) -> None:
    good = {**KEYART, "promise": ["尾巴"]}
    run = _run(tmp_path, {"a": good, "b": {**good, "promise": ["沒講過的話"]}}, "原典裡只有一條尾巴。")
    findings = th.variant_findings(run, load_channel("yokai"))
    assert [f.level for f in findings] == ["error"] and "variant b" in findings[0].message
    assert th.variant_findings(tmp_path / "nothing", load_channel("yokai")) == []     # no variants file: no check


def test_variants_file_allows_at_most_three(tmp_path: Path) -> None:
    run = _run(tmp_path, {k: KEYART for k in "abcd"}, "一條尾巴")
    assert th.variant_findings(run, load_channel("yokai"))[0].check == "thumbnail_variants"


def test_save_under_limit_shrinks_quality(tmp_path: Path) -> None:
    noisy = Image.effect_noise((1280, 720), 120).convert("RGB")
    png = tmp_path / "x.png"
    noisy.save(png)
    noisy.save(tmp_path / "q92.jpg", "JPEG", quality=92)
    assert (tmp_path / "q92.jpg").stat().st_size > 600_000          # control: the first quality does not fit
    out = th.save_under_limit(png, tmp_path / "x.jpg", limit=600_000)
    assert out.stat().st_size <= 600_000
    with pytest.raises(ValueError, match="quality"):
        th.save_under_limit(png, tmp_path / "y.jpg", limit=1_000)


@pytest.mark.parametrize("brand", ["chipcat", "yokai", "cel", "offwork"])
@pytest.mark.parametrize("spec", [KEYART, COMPARE, {**COMPARE, "compare": [{"value": "9", "label": "條"},
                                                                         {"value": "1", "label": "條"}]}])
def test_layout_templates_render_for_every_brand(brand: str, spec: dict) -> None:
    channel = load_channel(brand)
    parsed = th.ThumbnailSpec.model_validate(spec)
    for vertical in (False, True):
        html = th.thumbnail_html(parsed, channel, "file:///x.png", vertical=vertical)
        assert parsed.lines[0] in html and channel.name in html
        assert ("1920px" in html) == vertical
        for side in parsed.compare:
            assert side.value in html
