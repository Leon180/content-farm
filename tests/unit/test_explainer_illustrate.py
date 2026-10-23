"""AI illustration: provider contract, channel settings, the 「AI 示意圖」 badge, credits and QC."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from content_farm.explainer import illustrate as il
from content_farm.explainer.cards import overlay_html
from content_farm.explainer.deck import Deck
from content_farm.explainer.media_run import credits_text
from content_farm.production import qc
from content_farm.production.channels import AiIllustration, load_channel
from content_farm.production.steps import step_names
from tests.unit.explainer_helpers import deck_dict

SETTINGS = il.Settings("flux2-klein-4b", "Ink wash, not a photograph.", 7, 320, 192)


def _deck(prompt: str = "a white fox at dawn") -> Deck:
    data = deck_dict()
    data["sections"][1]["slides"][0]["media"] = {"kind": "ai_image", "prompt": prompt}
    return Deck.model_validate(data)


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[il.IllustrationRequest] = []

    def generate(self, request: il.IllustrationRequest, out: Path) -> dict:
        self.calls.append(request)
        Image.new("RGB", (request.width, request.height), (90, 90, 90)).save(out)
        return {"provider": self.name, "model": "flux2-klein-4b", "model_name": "FLUX.2 [klein] 4B (q4)",
                "origin_repo": "black-forest-labs/FLUX.2-klein-4B", "license": "Apache-2.0",
                "license_url": "https://example.test/LICENSE.md", "steps": 4, "seconds": 1.0}


def test_illustrate_writes_image_and_sidecar_then_keeps_it(tmp_path: Path) -> None:
    deck, provider = _deck(), FakeProvider()
    records = il.illustrate(deck, tmp_path, SETTINGS, provider)
    slide_id = provider.calls[0].slide_id
    image = tmp_path / "assets" / "ai_images" / f"{slide_id}.png"
    assert image.is_file() and len(records) == 1
    record = il.load_record(image)
    assert record["prompt"] == "Ink wash, not a photograph. a white fox at dawn"
    assert record["seed"] == 7 and record["size"] == [320, 192] and record["ai_label"] == il.AI_LABEL
    assert il.illustrate(deck, tmp_path, SETTINGS, provider) == [] and len(provider.calls) == 1  # kept
    il.illustrate(deck, tmp_path, SETTINGS, provider, replace=True)
    assert len(provider.calls) == 2


def test_photo_real_or_artist_prompt_is_refused_before_any_model_loads(tmp_path: Path) -> None:
    provider = FakeProvider()
    with pytest.raises(ValueError, match="photoreal"):
        il.illustrate(_deck("a photorealistic fox"), tmp_path, SETTINGS, provider)
    with pytest.raises(ValueError, match="in the style of"):
        il.illustrate(_deck("a fox in the style of a famous painter"), tmp_path, SETTINGS, provider)
    assert provider.calls == []
    assert il.forbidden_prompt_terms("ink wash fox, illustration, not a photograph") == []  # control


def test_local_mflux_needs_its_paths_and_builds_one_image_argv(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="CF_MFLUX_BIN_DIR"):
        il.LocalMflux.from_env("flux2-klein-4b", {})
    (tmp_path / "mflux-generate-z-image-turbo").write_text("#!/bin/sh\n")
    env = {"CF_MFLUX_BIN_DIR": str(tmp_path), "CF_MFLUX_HF_HOME": str(tmp_path / "hf")}
    with pytest.raises(FileNotFoundError):
        il.LocalMflux.from_env("flux2-klein-4b", env)  # its entry point is not there
    provider = il.LocalMflux.from_env("z-image-turbo", env)
    argv = provider.argv(il.IllustrationRequest("s05", "p", 42, 1280, 720), tmp_path / "s05.png")
    assert argv[argv.index("--model") + 1] == "filipstrand/Z-Image-Turbo-mflux-4bit"
    assert argv[argv.index("--steps") + 1] == "9" and argv[argv.index("--seed") + 1] == "42"


def test_waits_while_memory_pressure_is_warn_or_worse() -> None:
    idle = lambda: None  # noqa: E731
    levels, slept = iter([4, 2, 1]), []
    assert il.wait_for_memory(lambda: next(levels), slept.append, busy=idle) == 2 * il.PRESSURE_WAIT_SECONDS
    assert len(slept) == 2
    with pytest.raises(TimeoutError):
        il.wait_for_memory(lambda: 2, lambda _: None, max_wait=60, busy=idle)
    assert il.wait_for_memory(lambda: 1, slept.append, busy=idle) == 0  # normal: no wait


def test_waits_while_another_local_model_runs() -> None:
    """orchestrator 2026-10-16: never overlap with the AI-video worker's mlx_video (swap at 92%)."""
    running, slept = iter(["mlx_video", "mlx_video", None]), []
    assert il.wait_for_memory(lambda: 1, slept.append, busy=lambda: next(running)) == 60
    with pytest.raises(TimeoutError, match="mlx_video is running"):
        il.wait_for_memory(lambda: 1, lambda _: None, max_wait=30, busy=lambda: "mlx_video")
    assert il.other_model_running(("no-such-process-zz9",)) is None  # pgrep miss → free


def test_channels_pick_their_model_and_reject_bad_settings() -> None:
    assert load_channel("yokai").ai_illustration.model == "z-image-turbo"
    assert load_channel("chipcat").ai_illustration.model == "z-image-turbo"   # same klein cache gap (2026-10-24)
    assert load_channel("cel").ai_illustration.model == "z-image-turbo"   # klein weights not cached on this machine (2026-10-23)
    assert "not a photograph" in load_channel("yokai").ai_illustration.style_prefix
    with pytest.raises(ValidationError):
        AiIllustration(model="flux1-schnell")
    with pytest.raises(ValidationError):
        AiIllustration(style_prefix="hyper-realistic DSLR photo")


def test_illustrate_step_runs_before_media_only_where_ai_images_are_allowed() -> None:
    names = step_names(load_channel("chipcat"))
    assert names.index("illustrate") == names.index("media") - 1
    assert "illustrate" not in step_names(load_channel("offwork"))


def test_overlay_badge_only_on_ai_frames() -> None:
    deck = _deck()
    section, slide = deck.sections[1], deck.sections[1].slides[0]
    assert 'class="ai-label">AI 示意圖<' in overlay_html(deck, section, slide, 3, ai_label=il.AI_LABEL)
    assert "ai-label" not in overlay_html(deck, section, slide, 3).split("</style>")[1]


def _ai_entry(**changes: object) -> dict:
    entry = {"slide_id": "s05", "kind": "ai_image", "license": "AI-generated", "ai_label": il.AI_LABEL,
             "model": "z-image-turbo", "model_name": "Z-Image-Turbo (4-bit)", "prompt": "ink wash fox",
             "seed": 42, "origin_repo": "Tongyi-MAI/Z-Image-Turbo", "license_url": "https://x.test/L"}
    return {**entry, **changes}


def test_qc_requires_badge_and_generation_parameters() -> None:
    ok = qc.ai_image_findings([_ai_entry()])
    assert [f.level for f in ok] == ["ok"]
    unlabelled = qc.ai_image_findings([_ai_entry(ai_label=None)])
    assert any(f.check == "ai_label" and f.level == "error" for f in unlabelled)
    no_seed = qc.ai_image_findings([_ai_entry(seed=None)])
    assert any(f.check == "ai_params" and "seed" in f.message for f in no_seed)
    real = qc.ai_image_findings([_ai_entry(prompt="photorealistic fox")])
    assert any(f.check == "ai_style" for f in real)
    channel = load_channel("yokai")
    findings = qc.credits_findings(channel, {"entries": [_ai_entry(ai_label=None)], "pending": []})
    assert "credits" not in [f.check for f in findings]  # no blanket ok next to an error


def test_policy_catches_photo_real_prompts_in_the_deck() -> None:
    channel = load_channel("yokai")
    assert qc.policy_findings(channel, _deck())[0].level == "ok"
    assert qc.policy_findings(channel, _deck("a hyperrealistic fox"))[0].check == "ai_style"


def test_description_credits_name_the_model() -> None:
    text = credits_text([_ai_entry(), _ai_entry(slide_id="s09")])
    assert text.count("Z-Image-Turbo (4-bit)") == 1 and "AI 示意圖" in text
    assert credits_text([]) == ""


def test_media_credit_copies_the_sidecar(tmp_path: Path) -> None:
    from content_farm.explainer.media import _ai_credit

    image = tmp_path / "s05.png"
    Image.new("RGB", (8, 8)).save(image)
    il.sidecar_for(image).write_text(json.dumps({"model": "z-image-turbo", "model_name": "Z-Image-Turbo (4-bit)",
                                                 "license": "Apache-2.0", "prompt": "ink fox", "seed": 42,
                                                 "steps": 9, "size": [1280, 720]}), encoding="utf-8")

    class Job:  # the two fields _ai_credit reads
        index = 5
        slide = _deck().sections[1].slides[0]

    credit = _ai_credit(Job(), image)  # type: ignore[arg-type]
    assert credit["ai_label"] == il.AI_LABEL and credit["seed"] == 42 and credit["steps"] == 9
    assert "Z-Image-Turbo" in credit["license"] and "Apache-2.0" in credit["license"]
    assert [f.level for f in qc.ai_image_findings([credit])] == ["ok"]
    il.sidecar_for(image).unlink()
    bare = _ai_credit(Job(), image)  # type: ignore[arg-type]
    assert "unrecorded" in bare["license"]
    assert any(f.check == "ai_params" for f in qc.ai_image_findings([bare]))
