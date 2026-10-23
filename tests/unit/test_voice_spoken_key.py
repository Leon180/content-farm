"""Voice re-runs only for spoken changes, and a re-time with nothing to synthesize queues light
(orchestrator 2026-10-19: yokai waited hours for 18 GB after an image-prompt edit)."""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.production.channels import load_channel
from content_farm.production.runner import Runner
from content_farm.production.steps import (VOICE_SPOKEN_FILE, Context, RunOptions, steps_for, voice_nothing_to_synthesize,
                                           voice_spoken_key)
from tests.unit.test_production_runner import FakeExecutor
from tests.unit.test_production_runner import run_dir as run_dir  # noqa: F401  (fixture)


def _ctx(run_dir: Path) -> Context:
    return Context(load_channel("yokai"), run_dir, RunOptions())


def _edit(run_dir: Path, change) -> None:
    deck = json.loads((run_dir / "deck.json").read_text(encoding="utf-8"))
    change(deck["sections"][0]["slides"][0])
    (run_dir / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")


def test_an_image_prompt_edit_keeps_the_spoken_key_and_a_narration_edit_changes_it(run_dir: Path) -> None:  # noqa: F811
    ctx = _ctx(run_dir)
    key = voice_spoken_key(ctx)
    _edit(run_dir, lambda s: s.update(media={"kind": "ai_image", "prompt": "a fox under a golden sky"},
                                      heading="新的畫面標題"))
    assert voice_spoken_key(ctx) == key
    _edit(run_dir, lambda s: s.update(narration=s["narration"] + "多一句。"))
    assert voice_spoken_key(ctx) != key


def test_the_voice_step_does_not_fingerprint_whole_deck_or_script():
    voice = next(s for s in steps_for(load_channel("yokai"), Path("/nonexistent")) if s.name == "voice")
    assert "deck.json" not in voice.inputs and "script.json" not in voice.inputs and voice.identity is voice_spoken_key


def test_nothing_to_synthesize_queues_light_without_the_tts_lock(run_dir: Path) -> None:  # noqa: F811
    ctx = _ctx(run_dir)
    runner = Runner(ctx, executor=FakeExecutor(run_dir), log=lambda _: None)
    voice = next(s for s in steps_for(ctx.channel, run_dir) if s.name == "voice")
    heavy = runner._need(voice)                                  # noqa: SLF001 — nothing voiced yet
    assert heavy.mem_gb >= 16 and "local_tts" in heavy.locks
    (run_dir / VOICE_SPOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
    (run_dir / VOICE_SPOKEN_FILE).write_text(json.dumps({"key": voice_spoken_key(ctx)}), encoding="utf-8")
    assert voice_nothing_to_synthesize(ctx)
    light = runner._need(voice)                                  # noqa: SLF001
    assert light.mem_gb <= 1.0 and "local_tts" not in light.locks and light.gpu != "exclusive"
    _edit(run_dir, lambda s: s.update(narration=s["narration"] + "多一句。"))
    assert runner._need(voice).mem_gb >= 16                      # noqa: SLF001 — a spoken change needs the model
