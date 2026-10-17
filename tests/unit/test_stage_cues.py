"""Narration-cued staging: reveals follow the words, no hold longer than MAX_HOLD."""

from __future__ import annotations

from content_farm.explainer.deck import Slide
from content_farm.explainer.media import staged_html
from content_farm.explainer.stage_cues import MAX_HOLD, add_pulses, plan


def _bullets() -> Slide:
    return Slide.model_validate({
        "id": "s18", "layout": "bullets", "heading": "常被忽略的兩條線",
        "body": {"items": ["ABF 基板：最底下的多層板", "欣興資本支出 340 億", "設備：濕製程、點膠、檢測"]},
        "narration": "還有兩條常被忽略的供應線。一條是 ABF 基板，也就是最底下那塊多層板。欣興把資本支出提高到 340 億元以上。"
                     "另一條是設備，濕製程、點膠、檢測，有不少台灣設備商。"})


def test_reveals_follow_the_narration() -> None:
    sentences = [(0.5, "還有兩條常被忽略的供應線。"), (4.0, "一條是 ABF 基板，也就是最底下那塊多層板。"),
                 (11.0, "欣興把資本支出提高到 340 億元以上。"), (19.0, "另一條是設備，濕製程、點膠、檢測，有不少台灣設備商。")]
    stage = plan(_bullets(), sentences, 30.0)
    assert [round(t, 1) for t in stage.reveals] == [3.7, 10.7, 18.7]
    assert stage.longest_hold <= MAX_HOLD


def test_pulses_fill_long_holds() -> None:
    pulses, longest = add_pulses([1.0], 40.0, unit_count=1)
    assert longest <= MAX_HOLD
    assert all(idx == 0 for _, idx in pulses)
    assert len(pulses) >= 5


def test_slide_without_units_still_gets_pulses() -> None:
    quote = Slide.model_validate({"id": "s13", "layout": "quote", "heading": "黃仁勳的一句話",
                                  "body": {"text": "那是百分之百 NVIDIA 的錯", "who": "黃仁勳"},
                                  "narration": "這段時間也不是一路順利。" * 4})
    stage = plan(quote, [(0.5, "這段時間也不是一路順利。")], 25.0)
    assert stage.reveals == () and stage.pulses and all(idx == -1 for _, idx in stage.pulses)
    assert stage.longest_hold <= MAX_HOLD


def test_staged_html_sets_body_data() -> None:
    stage = plan(_bullets(), [], 20.0)
    html = staged_html('<html><body class="x">', stage)
    assert "data-cues='[" in html and "data-pulses='[" in html
    assert staged_html("<body>", None) == "<body>"
