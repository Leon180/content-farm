"""Item 1 (cf-pipeline-speed): the deck brief carries rubric + channel rules + Bash use from the first call, and
``apply_deck_patch`` applies ``{id: text, deletes: [...]}`` to deck.json without touching anything else."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from content_farm.review import deck_patch
from content_farm.review.brief import bash_text, channel_rules_text, deck_brief, rubric_text
from content_farm.review.config import load_review
from content_farm.review.producers import SCRIPTS, produce

CONFIG = load_review()
DECK = {"title": "t", "sections": [{"title": "A", "slides": [
    {"id": "s01", "narration": "第一句。第二句！第三句？", "sentence_ids": ["a1", "a2", "a3"], "layout": "title"},
    {"id": "s02", "narration": "只有一句。", "sentence_ids": ["b1"], "layout": "bullets"}]}]}


def _channel_code() -> str:
    return sorted(p.stem for p in (Path(__file__).resolve().parents[2] / "channels").glob("*.yaml")
                  if p.stem not in ("shared",))[0]


def test_rubric_lists_the_panel_roles_and_bars() -> None:
    text = rubric_text(CONFIG)
    assert "編劇" in text and "導演" in text
    assert "過關門檻" in text and "6.5" in text


def test_bash_text_names_both_scripts_and_forbids_wrappers() -> None:
    text = bash_text("/py", "/repo")
    assert "/py /repo/scripts/deck_to_script.py --run-dir" in text
    assert "/py /repo/scripts/apply_deck_patch.py --run-dir" in text
    assert "env -C" in text and "heredoc" in text


def test_channel_rules_states_the_take_threshold() -> None:
    text = channel_rules_text(_channel_code())
    assert "take: true" in text and "80" in text
    assert channel_rules_text("no-such-channel") == ""


def test_apply_deck_patch_is_whitelisted() -> None:
    assert "apply_deck_patch.py" in SCRIPTS


def test_deck_brief_reaches_first_prompt(tmp_path: Path) -> None:
    from content_farm.review.client import CallResult

    seen = {}

    def fake(call):
        seen["prompt"] = call.prompt
        return CallResult(call.rid, True, {"files": ["deck.json"], "summary": "ok"}, (), "sonnet", "medium")

    produce("deck", tmp_path, channel=_channel_code(), config=CONFIG, python="/py", client=fake)
    assert "take: true" in seen["prompt"] and "apply_deck_patch.py" in seen["prompt"] and "rubric" in seen["prompt"]


def test_patch_replaces_and_deletes_only_named() -> None:
    result = deck_patch.apply_patch(DECK, {"a2": "改過的第二句！"}, ["a3"])
    slide1, slide2 = result.deck["sections"][0]["slides"]
    assert slide1["narration"] == "第一句。改過的第二句！"
    assert slide1["sentence_ids"] == ["a1", "a2"]
    assert slide2 == DECK["sections"][0]["slides"][1]                    # untouched slide is the same object content
    assert DECK["sections"][0]["slides"][0]["narration"] == "第一句。第二句！第三句？"   # input not mutated


def test_patch_rejects_unknown_ids_and_empty_text() -> None:
    with pytest.raises(deck_patch.PatchError, match="unknown"):
        deck_patch.apply_patch(DECK, {"zz": "x。"}, [])
    with pytest.raises(deck_patch.PatchError):
        deck_patch.parse_patch({"a1": "  "})
    with pytest.raises(deck_patch.PatchError, match="both"):
        deck_patch.parse_patch({"a1": "x。", "deletes": ["a1"]})
    with pytest.raises(deck_patch.PatchError):
        deck_patch.parse_patch(["a1"])


def test_patch_requires_aligned_ids() -> None:
    deck = json.loads(json.dumps(DECK))
    deck["sections"][0]["slides"][0]["sentence_ids"] = ["a1"]
    with pytest.raises(deck_patch.PatchError, match="line up"):
        deck_patch.apply_patch(deck, {"a1": "x。"}, [])


def test_cli_applies_patch_and_refuses_bad_patch(tmp_path: Path, capsys) -> None:
    spec = importlib.util.spec_from_file_location(
        "apply_deck_patch", Path(__file__).resolve().parents[2] / "scripts" / "apply_deck_patch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "deck.json").write_text(json.dumps(DECK, ensure_ascii=False), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"nope": "x。"}), encoding="utf-8")
    assert module.main(["--run-dir", str(tmp_path), "--patch", str(bad), "--no-check"]) == 1
    assert json.loads((tmp_path / "deck.json").read_text(encoding="utf-8")) == DECK     # refused patch leaves deck alone
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"b1": "換掉了。"}), encoding="utf-8")
    assert module.main(["--run-dir", str(tmp_path), "--patch", str(good), "--no-check"]) == 0
    assert "換掉了。" in (tmp_path / "deck.json").read_text(encoding="utf-8")
