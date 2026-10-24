"""Animals keep animal bodies: no human hands in fable pictures (Leon 2026-10-24)."""

from __future__ import annotations

from pathlib import Path

import pytest

from content_farm.explainer import illustrate as il
from content_farm.production.channels import load_channel
from content_farm.production.fable import check, images
from tests.unit.test_fable import fable_dict, load


@pytest.mark.parametrize("prompt", [
    "an owl holding a notebook open to one page",
    "an owl writing with a feather pen at a desk",
    "an owl reading a book at a desk",
    "close view of an owl's hands on a book",
])
def test_prompts_that_give_an_animal_hands_are_refused(prompt: str) -> None:
    data = fable_dict()
    data["beats"][1]["shots"][0] = {"image_prompt": prompt}
    assert any("人手" in p for p in check.picture_problems(load(data)))


def test_a_prop_beside_the_animal_is_fine() -> None:
    data = fable_dict()
    data["beats"][1]["shots"][0] = {"image_prompt": "an owl with folded wings on a branch, an open book beside it"}
    assert check.picture_problems(load(data)) == []


def test_the_fable_channel_draws_animals_with_the_body_rule_and_a_negative_prompt() -> None:
    channel = load_channel("fable")
    assert channel.ai_illustration.animal_characters
    request = images.requests_for(load(fable_dict()), channel)[0]
    assert il.ANIMAL_BODY_RULE in request.prompt
    assert "human hands" in request.negative_prompt and "fingers" in request.negative_prompt


def test_a_redraw_moves_the_seed_and_other_pictures_keep_theirs() -> None:
    channel, fable = load_channel("fable"), load(fable_dict())
    base = images.requests_for(fable, channel)
    again = images.requests_for(fable, channel, {base[1].slide_id: 2})
    assert again[1].seed == base[1].seed + 2 * images.RESEED_STEP
    assert [r.seed for r in again if r.slide_id != base[1].slide_id] == [r.seed for r in base if r.slide_id != base[1].slide_id]


def test_the_negative_prompt_reaches_the_mflux_command(tmp_path: Path) -> None:
    provider = il.LocalMflux(il.MODELS["z-image-turbo"], tmp_path, tmp_path)
    plain = provider.argv(il.IllustrationRequest("s1", "p", 1, 720, 1280), tmp_path / "s1.png")
    rule = provider.argv(il.IllustrationRequest("s1", "p", 1, 720, 1280, il.ANIMAL_NEGATIVE), tmp_path / "s1.png")
    assert "--negative-prompt" not in plain
    assert rule[rule.index("--negative-prompt") + 1] == il.ANIMAL_NEGATIVE
