"""A step whose outputs are all there takes no machine slot (Step.has_work)."""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.production.channels import load_channel
from content_farm.production.runner import Runner
from content_farm.production.state import load_state
from content_farm.production.steps import Command, Context, RunOptions, Step, _illustrate_pending

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "explainer-cowos"


class Executor:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, command: Command, log_path: Path) -> int:
        self.calls += 1
        return 0


def _runner(tmp_path: Path, executor: Executor) -> Runner:
    ctx = Context(load_channel("chipcat"), tmp_path, RunOptions(panels=False))
    return Runner(ctx, executor=executor, log=lambda _: None)


def _step(has_work) -> Step:
    return Step("illustrate", "cmd", "t", command=lambda c: Command(("python", "x.py"), {}), heavy=True, has_work=has_work)


def test_idle_step_is_done_without_a_slot(tmp_path):
    executor = Executor()
    runner = _runner(tmp_path, executor)
    state, result = runner._cmd(load_state(tmp_path, "chipcat"), _step(lambda c: False), False)
    assert result is None and executor.calls == 0
    assert state.steps["illustrate"].status == "done"
    events = [json.loads(line) for line in (tmp_path / "production.log.jsonl").read_text().splitlines()]
    assert events[-1]["skipped"] == "no work" and events[-1]["seconds"] == 0.0


def test_step_with_work_runs(tmp_path):
    executor = Executor()
    state, result = _runner(tmp_path, executor)._cmd(load_state(tmp_path, "chipcat"), _step(lambda c: True), False)
    assert result is None and executor.calls == 1 and state.steps["illustrate"].status == "done"


def test_a_broken_check_never_skips_work(tmp_path):
    def broken(ctx):
        raise RuntimeError("boom")

    executor = Executor()
    _runner(tmp_path, executor)._cmd(load_state(tmp_path, "chipcat"), _step(broken), False)
    assert executor.calls == 1


def test_forced_step_ignores_the_check(tmp_path):
    executor = Executor()
    _runner(tmp_path, executor)._cmd(load_state(tmp_path, "chipcat"), _step(lambda c: False), True)
    assert executor.calls == 1


def test_illustrate_pending_follows_missing_images(tmp_path):
    (tmp_path / "deck.json").write_text((EXAMPLE / "deck.json").read_text(encoding="utf-8"), encoding="utf-8")
    ctx = Context(load_channel("chipcat"), tmp_path, RunOptions(panels=False))
    assert _illustrate_pending(ctx) is False          # the example deck draws no ai_image slide
    (tmp_path / "deck.json").write_text("{not json", encoding="utf-8")
    assert _illustrate_pending(ctx) is True           # an unreadable deck: let the command report it
