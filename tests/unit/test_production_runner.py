"""Runner walk-through with a fake executor: gates, resume, invalidation, paid consent."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from content_farm.explainer.deck import load_deck
from content_farm.explainer.to_script import deck_to_script
from content_farm.production import runner as runner_mod
from content_farm.production.channels import Gate, load_channel
from content_farm.production.runner import Outcome, Runner, decide
from content_farm.production.state import load_state
from content_farm.production.steps import Command, Context, RunOptions

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "explainer-cowos"


class FakeExecutor:
    """Creates each script's outputs instead of running it."""

    def __init__(self, run_dir: Path, fail: set[str] | None = None) -> None:
        self.run_dir = run_dir
        self.fail = fail or set()
        self.calls: list[str] = []
        self.envs: dict[str, dict[str, str]] = {}

    def __call__(self, command: Command, log_path: Path) -> int:
        script = Path(command.argv[1]).name
        stage = command.argv[command.argv.index("--stage") + 1] if "--stage" in command.argv else ""
        key = stage or script
        self.calls.append(key)
        self.envs[key] = dict(command.env)
        if key in self.fail:
            return 2
        d = self.run_dir
        if script == "deck_to_script.py":
            (d / "script.json").write_text(deck_to_script(load_deck(d / "deck.json")).model_dump_json())
        elif script == "render_slides.py":
            assert "--brand" in command.argv
            _touch(d / "slides" / "contact_sheet.png")
            _touch(d / "slides" / "slide_001.png")
        elif stage == "voice":
            _touch(d / "audio" / "scene_001.mp3")
            _touch(d / "subtitles" / "subtitles.srt", "1\n00:00:00,000 --> 00:00:01,000\n短句\n")
        elif script == "media_to_visual.py":
            (d / "credits.json").write_text(json.dumps({"entries": [], "pending": [], "description_text": ""}))
            _touch(d / "media" / "contact_sheet.png")
            _touch(d / "visual" / "00:00.000~00:01.000.mp4")
        elif stage == "assembly_timeline":
            _touch(d / "assembly" / "draft.mp4")
        elif script == "mascot_overlay.py":
            _touch(d / "assembly" / "final.mp4")
        return 0


def _touch(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(runner_mod, "LOCK_PATH", tmp_path / "render.lock")
    d = tmp_path / "run"
    d.mkdir()
    for name in ("article.md", "sources.json", "deck.json"):
        shutil.copy(EXAMPLE / name, d / name)
    return d


def _runner(run_dir: Path, executor: FakeExecutor, **options: object) -> Runner:
    ctx = Context(load_channel("chipcat"), run_dir, RunOptions(**options))  # type: ignore[arg-type]
    return Runner(ctx, executor=executor, log=lambda _: None)


def _approve(run_dir: Path, gate: Gate, **kw: str) -> None:
    decide(run_dir, load_channel("chipcat"), gate, "approved", by="test", **kw)


def _walk_to_final(run_dir: Path, executor: FakeExecutor) -> None:
    runner = _runner(run_dir, executor, mock_voice=True)
    for gate in (Gate.ARTICLE, Gate.DECK, Gate.MEDIA):
        result = runner.run()
        assert result.outcome is Outcome.GATE and result.step == f"gate_{gate.value}"
        assert result.review_page is not None and result.review_page.is_file()
        _approve(run_dir, gate)
    result = runner.run()
    assert result.outcome is Outcome.GATE and result.step == "gate_final"


def test_full_walk_stops_at_each_gate_and_packages(run_dir: Path) -> None:
    executor = FakeExecutor(run_dir)
    _walk_to_final(run_dir, executor)
    # Fake mp4s cannot be probed, so QC reports errors and final approval needs a reason.
    with pytest.raises(ValueError, match="override"):
        _approve(run_dir, Gate.FINAL)
    _approve(run_dir, Gate.FINAL, override="test fixture video")
    result = _runner(run_dir, executor, mock_voice=True).run()
    assert result.outcome is Outcome.COMPLETE
    meta = json.loads((run_dir / "upload" / "youtube_meta.json").read_text(encoding="utf-8"))
    assert meta["video_path"] == "assembly/final.mp4"
    assert meta["contains_synthetic_media"] is True
    assert meta["credentials_env"]["refresh_token"] == "CF_YT_CHIPCAT_REFRESH_TOKEN"
    state = load_state(run_dir, "chipcat")
    assert "OVERRIDE QC" in state.decisions["final"].note
    assert {state.steps[f"gate_{g}"].status for g in ("article", "deck", "media", "final")} == {"approved"}


def test_resume_skips_finished_steps(run_dir: Path) -> None:
    executor = FakeExecutor(run_dir)
    _walk_to_final(run_dir, executor)
    before = list(executor.calls)
    result = _runner(run_dir, executor, mock_voice=True).run()
    assert result.outcome is Outcome.GATE and executor.calls == before


def test_editing_deck_after_approval_reopens_gate_and_reruns(run_dir: Path) -> None:
    executor = FakeExecutor(run_dir)
    _walk_to_final(run_dir, executor)
    deck = json.loads((run_dir / "deck.json").read_text(encoding="utf-8"))
    deck["title"] = deck["title"] + "（改）"
    (run_dir / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    executor.calls.clear()
    result = _runner(run_dir, executor, mock_voice=True).run()
    assert result.outcome is Outcome.GATE and result.step == "gate_deck"
    assert "已變更" in result.message
    assert executor.calls == ["deck_to_script.py", "render_slides.py"]


def test_paid_voice_needs_consent(run_dir: Path) -> None:
    executor = FakeExecutor(run_dir)
    runner = _runner(run_dir, executor)
    runner.run()
    _approve(run_dir, Gate.ARTICLE)
    runner.run()
    _approve(run_dir, Gate.DECK)
    result = runner.run()
    assert result.outcome is Outcome.PAID and result.step == "voice"
    assert "voice" not in executor.calls and result.exit_code == 3


@pytest.fixture()
def voice_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An env file standing in for .env; the process environment has none of these keys."""
    for key in ("CF_CHIPCAT_VOICE_ID", "CF_FISH_AUDIO_REFERENCE_ID", "CF_FISH_AUDIO_API_KEY",
                "CF_TTS_PROVIDER", "CF_TTS_VOICE_ID"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "voice.env"
    path.write_text("CF_FISH_AUDIO_API_KEY=sk-secret-key\nCF_FISH_AUDIO_REFERENCE_ID=default-ref\n"
                    "CF_TTS_PROVIDER=macos_say\n", encoding="utf-8")
    return path


def _paid_runner(run_dir: Path, executor: FakeExecutor, env_file: Path, log: list[str]) -> Runner:
    ctx = Context(load_channel("chipcat"), run_dir, RunOptions(allow_paid=True, env_file=env_file))
    return Runner(ctx, executor=executor, log=log.append)


def _run_through_voice(run_dir: Path, executor: FakeExecutor, env_file: Path) -> list[str]:
    log: list[str] = []
    runner = _paid_runner(run_dir, executor, env_file, log)
    runner.run()
    _approve(run_dir, Gate.ARTICLE)
    runner.run()
    _approve(run_dir, Gate.DECK)
    assert runner.run(until="voice").outcome is Outcome.COMPLETE
    return log


def test_voice_uses_the_channel_voice_id(run_dir: Path, voice_env_file: Path) -> None:
    with voice_env_file.open("a", encoding="utf-8") as handle:
        handle.write("CF_CHIPCAT_VOICE_ID=chipcat-voice\n")
    executor = FakeExecutor(run_dir)
    log = _run_through_voice(run_dir, executor, voice_env_file)
    env = executor.envs["voice"]
    assert env["CF_TTS_VOICE_ID"] == "chipcat-voice"
    assert env["CF_TTS_PROVIDER"] == "fish_audio"  # the channel's provider, not the file's macos_say
    assert env["CF_FISH_AUDIO_API_KEY"] == "sk-secret-key"  # handed to the subprocess, never logged
    voice_line = next(line for line in log if line.startswith("voice:"))
    assert "chipcat-voice" in voice_line and "CF_CHIPCAT_VOICE_ID" in voice_line
    events = (run_dir / "production.log.jsonl").read_text(encoding="utf-8")
    assert "CF_CHIPCAT_VOICE_ID" in events
    assert all("sk-secret-key" not in line for line in log) and "sk-secret-key" not in events


def test_voice_without_channel_id_falls_back_and_says_so(run_dir: Path, voice_env_file: Path) -> None:
    executor = FakeExecutor(run_dir)
    log = _run_through_voice(run_dir, executor, voice_env_file)
    assert "CF_TTS_VOICE_ID" not in executor.envs["voice"]  # provider default applies
    voice_line = next(line for line in log if line.startswith("voice:"))
    assert "default-ref" in voice_line and "CF_FISH_AUDIO_REFERENCE_ID" in voice_line
    assert "退回預設" in voice_line and "CF_CHIPCAT_VOICE_ID 未設" in voice_line


def test_process_env_voice_id_wins_over_env_file(
    run_dir: Path, voice_env_file: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with voice_env_file.open("a", encoding="utf-8") as handle:
        handle.write("CF_CHIPCAT_VOICE_ID=from-file\n")
    monkeypatch.setenv("CF_CHIPCAT_VOICE_ID", "from-env")
    executor = FakeExecutor(run_dir)
    _run_through_voice(run_dir, executor, voice_env_file)
    assert executor.envs["voice"]["CF_TTS_VOICE_ID"] == "from-env"


def test_changing_the_voice_reruns_the_voice_step(run_dir: Path, voice_env_file: Path) -> None:
    executor = FakeExecutor(run_dir)
    _run_through_voice(run_dir, executor, voice_env_file)
    runner = _paid_runner(run_dir, executor, voice_env_file, [])
    executor.calls.clear()
    runner.run(until="voice")
    assert "voice" not in executor.calls  # same voice, same inputs: resumed
    with voice_env_file.open("a", encoding="utf-8") as handle:
        handle.write("CF_CHIPCAT_VOICE_ID=new-voice\n")
    runner.run(until="voice")
    assert executor.calls == ["voice"]
    assert executor.envs["voice"]["CF_TTS_VOICE_ID"] == "new-voice"


def test_failed_step_stops_and_retries(run_dir: Path) -> None:
    executor = FakeExecutor(run_dir, fail={"check_article.py"})
    result = _runner(run_dir, executor).run()
    assert result.outcome is Outcome.FAILED and result.exit_code == 1
    assert load_state(run_dir, "chipcat").steps["article"].status == "failed"
    executor.fail.clear()
    assert _runner(run_dir, executor).run().step == "gate_article"


def test_missing_agent_output_waits_with_hint(run_dir: Path) -> None:
    (run_dir / "article.md").unlink()
    result = _runner(run_dir, FakeExecutor(run_dir)).run()
    assert result.outcome is Outcome.AGENT and "/article" in result.message


def test_rejection_is_recorded_and_blocks(run_dir: Path) -> None:
    executor = FakeExecutor(run_dir)
    runner = _runner(run_dir, executor)
    runner.run()
    decide(run_dir, load_channel("chipcat"), Gate.ARTICLE, "rejected", note="來源不足")
    result = runner.run()
    assert result.step == "gate_article" and "來源不足" in result.message
    item = json.loads((run_dir / "review" / "article.decision.json").read_text(encoding="utf-8"))
    assert item["status"] == "rejected"  # not back in the inbox until the files change


def test_review_page_escapes_run_content(run_dir: Path) -> None:
    (run_dir / "article.md").write_text("# t\n<script>alert(1)</script>\n" + "字" * 3000, encoding="utf-8")
    executor = FakeExecutor(run_dir)
    result = _runner(run_dir, executor).run()
    html = result.review_page.read_text(encoding="utf-8")  # type: ignore[union-attr]
    assert "<script>alert(1)" not in html and "&lt;script&gt;alert(1)" in html
    assert "approve --run-dir" in html


def test_channel_mismatch_rejected(run_dir: Path) -> None:
    _runner(run_dir, FakeExecutor(run_dir)).run()
    with pytest.raises(ValueError, match="belongs to channel"):
        load_state(run_dir, "yokai")
