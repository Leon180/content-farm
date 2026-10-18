"""Scene identity helpers of the media step (no browser)."""

from __future__ import annotations

from pathlib import Path

from content_farm.explainer.deck import Deck
from content_farm.explainer.media_cache import stable_narration
from tests.unit.explainer_helpers import deck_dict


def test_stored_timing_wins_while_audio_and_text_are_unchanged(tmp_path: Path) -> None:
    deck = Deck.model_validate(deck_dict())
    audio = tmp_path / "audio"
    audio.mkdir()
    for i in range(1, len(deck.slides) + 1):
        (audio / f"scene_{i:03d}.mp3").write_bytes(f"take {i}".encode())
    first_id = deck.slides[0].id
    timing = {s.id: [(0.5, "甲。"), (2.31, "乙。")] for s in deck.slides}
    assert stable_narration(tmp_path, tmp_path / "media", deck, timing)[first_id] == [(0.5, "甲。"), (2.31, "乙。")]

    nudged = {s.id: [(0.5, "甲。"), (2.32, "乙。")] for s in deck.slides}   # realignment rounding noise
    again = stable_narration(tmp_path, tmp_path / "media", deck, nudged)
    assert again[first_id] == [(0.5, "甲。"), (2.31, "乙。")]

    (audio / "scene_001.mp3").write_bytes(b"new take")                      # re-voiced: take the new timing
    third = stable_narration(tmp_path, tmp_path / "media", deck, nudged)
    assert third[first_id] == [(0.5, "甲。"), (2.32, "乙。")]
    assert third[deck.slides[1].id] == [(0.5, "甲。"), (2.31, "乙。")]
    assert stable_narration(tmp_path, tmp_path / "media", deck, None) is None
