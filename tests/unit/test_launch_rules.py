"""Launch-fix rules (policy review 2026-10): channel identity, template wording, commentary,
mascot presence, news-card headline split, and thumbnail spec/promise checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from content_farm.explainer.cards import title_card_html
from content_farm.explainer.deck import Deck, load_deck
from content_farm.explainer.lint import lint_deck
from content_farm.production import channel_rules, identity, qc, thumbnail
from content_farm.production.channels import load_all, load_channel, other_identities

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "explainer-cowos"


def _deck_data() -> dict:
    return json.loads((EXAMPLE / "deck.json").read_text(encoding="utf-8"))


def _slides(data: dict) -> list[dict]:
    return [slide for section in data["sections"] for slide in section["slides"]]


# --- channel identity -------------------------------------------------------

def test_every_explainer_channel_has_its_own_identity() -> None:
    channels = [c for c in load_all() if c.identity is not None]
    assert {c.code for c in channels} >= {"chipcat", "cel", "yokai"}
    assert identity.collisions([(c.code, c.identity) for c in channels]) == []


def test_collision_detector_catches_a_shared_line() -> None:
    chipcat, cel = load_channel("chipcat"), load_channel("cel")
    copied = cel.identity.model_copy(update={"outro": chipcat.identity.outro})  # control: same sign-off
    found = identity.collisions([("chipcat", chipcat.identity), ("cel", copied)])
    assert any("我們下一關見" in line for line in found)


def test_long_channels_aim_for_eight_minutes() -> None:
    for code in ("chipcat", "cel", "yokai"):
        fmt = load_channel(code).format
        assert fmt.target_seconds == (420, 600) and fmt.goal_seconds == 480


def test_template_phrases_are_detected() -> None:
    assert identity.template_phrases("今天用二十四張圖，拆給你看") == ["用二十四張圖"]
    assert identity.template_phrases("晶片貓用 24 張圖拆解") == ["用 24 張圖"]
    assert identity.template_phrases("這張圖很清楚") == []  # control: ordinary wording


# --- deck rules -------------------------------------------------------------

def test_example_deck_passes_every_channel_rule() -> None:
    chipcat = load_channel("chipcat")
    findings = channel_rules.deck_rule_findings(chipcat, load_deck(EXAMPLE / "deck.json"),
                                                other_identities(chipcat))
    assert [f for f in findings if f.level == "error"] == []


def test_template_and_foreign_wording_are_errors() -> None:
    data = _deck_data()
    slides = _slides(data)
    slides[0]["narration"] += "今天用二十四張圖拆給你看。"
    slides[5]["narration"] += "這裡是賽璐璐研究室。"
    chipcat = load_channel("chipcat")
    checks = {f.check: f.level for f in channel_rules.deck_rule_findings(
        chipcat, Deck.model_validate(data), other_identities(chipcat))}
    assert checks["template_phrase"] == "error" and checks["foreign_phrase"] == "error"


def test_missing_opening_outro_take_and_mascot_are_errors() -> None:
    data = _deck_data()
    slides = _slides(data)
    slides[0]["narration"] = slides[0]["narration"].replace("我是晶片貓", "我是一隻貓")
    slides[-1]["narration"] = slides[-1]["narration"].replace("我們下一關見", "再會")
    for slide in slides:
        slide["take"] = False
        slide["mascot"] = None
    chipcat = load_channel("chipcat")
    checks = {f.check: f.level for f in channel_rules.deck_rule_findings(
        chipcat, Deck.model_validate(data), other_identities(chipcat))}
    assert checks == {"identity_opening": "error", "identity_outro": "error", "template_phrase": "ok",
                      "commentary": "error", "mascot_presence": "error"}


def test_mascot_rule_skips_channels_without_a_rig() -> None:
    deck = load_deck(EXAMPLE / "deck.json")
    assert channel_rules.mascot_findings(load_channel("cel"), deck) == []


def test_policy_step_runs_the_channel_rules() -> None:
    data = _deck_data()
    for slide in _slides(data):
        slide["take"] = False
    findings = qc.deck_findings(load_channel("chipcat"), Deck.model_validate(data))
    assert any(f.check == "commentary" and f.level == "error" for f in findings)


# --- news card: outlet headline vs channel summary --------------------------

def _card_deck(headline: str) -> tuple[Deck, object]:
    data = _deck_data()
    for source in data["sources"]:
        if source["id"] == "register-2023":
            source["headline"] = headline
    deck = Deck.model_validate(data)
    slide = next(s for s in deck.slides if s.media and s.media.source_id == "register-2023")
    return deck, slide


def test_title_card_separates_outlet_headline_from_channel_summary() -> None:
    deck, slide = _card_deck("TSMC warns AI chip crunch will last another 18 months")
    section = next(sec for sec in deck.sections if slide in sec.slides)
    html = title_card_html(deck, section, slide, 2, brand="chipcat")
    assert "媒體原標題" in html and "TSMC warns AI chip crunch will last another 18 months" in html
    assert "本頻道摘要" in html and "（非媒體原標題）" not in html


def test_title_card_without_recorded_headline_says_so_and_lint_flags_it() -> None:
    deck, slide = _card_deck("")
    section = next(sec for sec in deck.sections if slide in sec.slides)
    html = title_card_html(deck, section, slide, 2, brand="chipcat")
    assert "本頻道摘要（非媒體原標題）" in html and "媒體原標題</div>" not in html
    assert any(issue.code == "title-card-headline" for issue in lint_deck(deck))


# --- thumbnail --------------------------------------------------------------

def test_thumbnail_text_is_capped_at_ten_characters() -> None:
    ok = {"lines": ["CoWoS", "卡住 AI？"], "visual": {"kind": "mascot"}, "promise": ["卡住出貨"]}
    assert thumbnail.ThumbnailSpec.model_validate(ok).text == "CoWoS卡住 AI？"
    with pytest.raises(ValidationError, match="<= 10"):
        thumbnail.ThumbnailSpec.model_validate({**ok, "lines": ["AI 晶片為什麼", "卡在封裝這一關"]})
    with pytest.raises(ValidationError, match="highlight"):
        thumbnail.ThumbnailSpec.model_validate({**ok, "highlight": "HBM"})


def _thumb_run(tmp_path: Path, spec: dict, narrations: list[tuple[str, float]]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "thumbnail.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    scenes = [{"narration": text, "duration_seconds": seconds} for text, seconds in narrations]
    (tmp_path / "script.json").write_text(json.dumps({"scenes": scenes}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "thumbnails").mkdir()
    (tmp_path / "thumbnails" / "thumbnail.png").write_bytes(b"png")
    return tmp_path


def test_thumbnail_promise_must_be_paid_off_in_the_first_minute(tmp_path: Path) -> None:
    spec = {"lines": ["CoWoS", "卡住 AI？"], "visual": {"kind": "mascot"}, "promise": ["卡住出貨"]}
    early = _thumb_run(tmp_path / "early", spec, [("真正卡住出貨的，是封裝。", 12.0), ("後面。", 60.0)])
    assert [f.level for f in thumbnail.thumbnail_findings(early, load_channel("chipcat"))] == ["ok"]
    late = _thumb_run(tmp_path / "late", spec, [("開場閒聊。", 70.0), ("真正卡住出貨的，是封裝。", 10.0)])
    finding = thumbnail.thumbnail_findings(late, load_channel("chipcat"))[0]
    assert finding.level == "error" and "60" in finding.message


def test_thumbnail_numbers_must_be_in_the_narration(tmp_path: Path) -> None:
    spec = {"lines": ["卡住", "3 年？"], "visual": {"kind": "mascot"}, "promise": ["卡住"]}
    run = _thumb_run(tmp_path, spec, [("卡住了很久。", 10.0)])
    findings = thumbnail.thumbnail_findings(run, load_channel("chipcat"))
    assert any("numbers not in the narration: 3" in f.message for f in findings)


def test_mascot_channel_thumbnail_needs_the_cat(tmp_path: Path) -> None:
    spec = {"lines": ["卡住"], "visual": {"kind": "brand"}, "promise": ["卡住"]}
    run = _thumb_run(tmp_path, spec, [("卡住了。", 10.0)])
    chipcat = [f.message for f in thumbnail.thumbnail_findings(run, load_channel("chipcat"))]
    assert any("must be on the thumbnail" in m for m in chipcat)
    cel = thumbnail.thumbnail_findings(run, load_channel("cel"))  # control: no rig → brand art is fine
    assert [f.level for f in cel] == ["ok"]


def test_missing_spec_is_an_error(tmp_path: Path) -> None:
    assert thumbnail.thumbnail_findings(tmp_path, load_channel("cel"))[0].level == "error"


def test_thumbnail_html_uses_brand_tokens_and_highlight() -> None:
    spec = thumbnail.ThumbnailSpec.model_validate(
        {"lines": ["九尾狐", "原本會吃人"], "highlight": "吃人", "visual": {"kind": "image", "path": "x.jpg"},
         "promise": ["吃人"]})
    html = thumbnail.thumbnail_html(spec, load_channel("yokai"), "file:///x.jpg")
    assert '<span class="hl">吃人</span>' in html and "yokai-title" in html and "--bg" in html


def test_render_writes_full_and_phone_size_pngs(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    from PIL import Image

    spec = {"lines": ["動畫賣爆", "公司還虧？"], "number": "6成", "number_note": "業績變差",
            "visual": {"kind": "brand"}, "promise": ["虧錢"]}
    (tmp_path / "thumbnail.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    try:
        out = thumbnail.render_thumbnail(tmp_path, load_channel("cel"))
    except Exception as exc:  # chromium missing on this machine
        pytest.skip(f"browser unavailable: {exc}")
    assert Image.open(out).size == thumbnail.SIZE
    assert Image.open(tmp_path / thumbnail.SMALL_FILE).size == thumbnail.PHONE_SIZE
