"""Stable sentence ids across deck edits (explainer.sentence_ids)."""

from __future__ import annotations

import json

from content_farm.explainer.sentence_ids import (
    LEDGER_FILE,
    assign,
    load_ledger,
    stamp_deck,
    stamp_run,
)


def _deck(slides: list[tuple[str, str]]) -> dict:
    return {"title": "t", "sections": [{"title": "a", "slides": [
        {"id": sid, "narration": text} for sid, text in slides]}]}


def test_migration_numbers_sentences_per_slide():
    stamp = assign([("s01", ["一。", "二。"]), ("s02", ["三！"])])
    assert stamp.ids == {"s01": ("s01.1", "s01.2"), "s02": ("s02.1",)}
    assert stamp.added == ("s01.1", "s01.2", "s02.1")


def test_unchanged_sentences_keep_ids_rewritten_get_new():
    first = assign([("s01", ["一。", "二。", "三。"])])
    second = assign([("s01", ["一。", "二改。", "三。"])], first.ledger)
    assert second.ids["s01"] == ("s01.1", "s01.4", "s01.3")
    assert second.added == ("s01.4",)
    assert second.retired == ("s01.2",)


def test_retired_id_is_never_reused_but_undo_revives_it():
    first = assign([("s01", ["一。", "二。"])])
    cut = assign([("s01", ["一。"])], first.ledger)
    added = assign([("s01", ["一。", "新。"])], cut.ledger)
    assert added.ids["s01"] == ("s01.1", "s01.3")
    undo = assign([("s01", ["一。", "二。"])], cut.ledger)
    assert undo.ids["s01"] == ("s01.1", "s01.2")


def test_reorder_and_moved_sentence_keep_ids():
    first = assign([("s01", ["甲。"]), ("s02", ["乙。", "丙。"])])
    second = assign([("s02", ["乙。"]), ("s01", ["甲。", "丙。"])], first.ledger)
    assert second.ids == {"s02": ("s02.1",), "s01": ("s01.1", "s02.2")}
    assert second.moved == ("s02.2",)


def test_identical_sentences_get_one_id_each():
    stamp = assign([("s01", ["好。", "好。"])])
    again = assign([("s01", ["好。", "好。"])], stamp.ledger)
    assert again.ids["s01"] == ("s01.1", "s01.2")


def test_stamp_deck_does_not_mutate_input_and_seeds_from_deck_ids():
    raw = _deck([("s01", "一。二。")])
    stamped, _ = stamp_deck(raw, None)
    assert "sentence_ids" not in raw["sections"][0]["slides"][0]
    # No ledger file: rebuilt from the deck's own ids (where they line up with the narration).
    moved = _deck([("s00", "零。"), ("s01", "一。二。")])
    moved["sections"][0]["slides"][1]["sentence_ids"] = ["x.7", "x.8"]
    restamped, stamp = stamp_deck(moved, None)
    assert restamped["sections"][0]["slides"][1]["sentence_ids"] == ["x.7", "x.8"]
    assert stamp.added == ("s00.1",)


def test_stamp_run_writes_deck_and_ledger(tmp_path):
    (tmp_path / "deck.json").write_text(json.dumps(_deck([("s01", "一。二。")])), encoding="utf-8")
    stamp_run(tmp_path)
    deck = json.loads((tmp_path / "deck.json").read_text(encoding="utf-8"))
    assert deck["sections"][0]["slides"][0]["sentence_ids"] == ["s01.1", "s01.2"]
    assert set(load_ledger(tmp_path / LEDGER_FILE)) == {"s01.1", "s01.2"}
    deck["sections"][0]["slides"][0]["narration"] = "一。改。"
    (tmp_path / "deck.json").write_text(json.dumps(deck), encoding="utf-8")
    stamp = stamp_run(tmp_path)
    assert stamp.ids["s01"] == ("s01.1", "s01.3")
    assert load_ledger(tmp_path / LEDGER_FILE)["s01.2"].retired
