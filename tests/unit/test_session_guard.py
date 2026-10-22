"""scripts/session_guard.py reads the conversation size from the transcript's own usage figures."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import session_guard as guard  # noqa: E402


def _line(tokens: int, *, sidechain: bool = False, kind: str = "assistant") -> str:
    usage = {"input_tokens": 2, "cache_creation_input_tokens": 100, "cache_read_input_tokens": tokens - 102,
             "output_tokens": 50}
    return json.dumps({"type": kind, "isSidechain": sidechain, "message": {"model": "claude-sonnet-5-5", "usage": usage}})


def _transcript(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "s.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_the_size_is_the_prefix_the_last_main_thread_call_read(tmp_path: Path) -> None:
    path = _transcript(tmp_path, _line(100_000), _line(250_000), _line(900_000, sidechain=True), _line(1, kind="user"))
    size = guard.context_size(path)
    assert size is not None and size.tokens == 250_000 and size.model == "claude-sonnet-5-5"


def test_exit_codes_follow_the_limit(tmp_path: Path) -> None:
    for tokens, code in ((100_000, 0), (260_000, 1), (310_000, 3)):
        path = _transcript(tmp_path, _line(tokens))
        assert guard.main(["--transcript", str(path)]) == code


def test_the_limit_can_be_set_by_flag_or_environment(tmp_path: Path, monkeypatch) -> None:
    path = _transcript(tmp_path, _line(150_000))
    assert guard.main(["--transcript", str(path), "--limit", "120000"]) == 3
    monkeypatch.setenv("CF_SESSION_TOKEN_LIMIT", "400000")
    assert guard.main(["--transcript", str(path)]) == 0


def test_no_usage_yet_is_exit_two(tmp_path: Path) -> None:
    assert guard.main(["--transcript", str(_transcript(tmp_path, _line(5, kind="user")))]) == 2


def test_a_long_transcript_is_read_from_the_tail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(guard, "TAIL_BYTES", 2_000)
    filler = [json.dumps({"type": "user", "message": {"content": "x" * 200}}) for _ in range(100)]
    path = _transcript(tmp_path, _line(10), *filler, _line(333_333))
    assert guard.context_size(path).tokens == 333_333


def test_the_hook_nudges_only_over_the_limit(tmp_path: Path, monkeypatch, capsys) -> None:
    for tokens, nudged in ((100_000, False), (320_000, True)):
        path = _transcript(tmp_path, _line(tokens))
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"transcript_path": str(path)})))
        assert guard.main(["--hook"]) == 0
        out = capsys.readouterr().out
        assert bool(out) is nudged
        if nudged:
            text = json.loads(out)["hookSpecificOutput"]["additionalContext"]
            assert "320,0" in text and "handoff" in text


def test_the_project_directory_matches_claude_codes_naming() -> None:
    cwd = Path("/Users/x/project/content-farm/.claude/worktrees/cf-cost-fix")
    assert guard.project_dir(cwd).name == "-Users-x-project-content-farm--claude-worktrees-cf-cost-fix"
