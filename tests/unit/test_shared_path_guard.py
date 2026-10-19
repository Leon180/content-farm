"""The test-run guard (tests/_shared_path_guard.py) and the redirect of machine-wide paths."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from content_farm import paths
from content_farm.lanes import queue as q
from content_farm.voice.local_worker import GateConfig
from tests import conftest
from tests._shared_path_guard import Guard, SharedPathWrite, main_checkout, protected_roots

REAL_HOME = Path.home()


def test_shared_paths_point_at_tmp_during_tests():
    tmp = Path(tempfile.gettempdir()).resolve()
    for path in (q.default_queue_dir(), *q.legacy_locks(), Path(GateConfig().lock_path), paths.orch_mail_script(),
                 paths.orch_mail_dir()):
        assert path.resolve().is_relative_to(tmp), path


def test_paths_default_to_the_machine_locations(monkeypatch):
    for name in ("CF_CACHE_ROOT", "CF_HEAVY_QUEUE_DIR", "CF_LOCAL_TTS_LOCK_PATH", "CF_ORCH_MAIL", "CF_ORCH_MAIL_DIR"):
        monkeypatch.delenv(name, raising=False)
    assert paths.heavy_queue_dir() == REAL_HOME / ".cache" / "content-farm" / "heavy-queue"
    assert paths.render_lock_path() == REAL_HOME / ".cache" / "content-farm" / "render.lock"
    assert paths.local_tts_lock_path() == REAL_HOME / ".cache" / "content-farm" / "local_tts.lock"
    assert paths.orch_mail_script() == REAL_HOME / "orchestrator" / "orch_mail.py"


def _guard(tmp_path: Path) -> tuple[Guard, Path]:
    home = tmp_path / "home"
    guard = Guard(protected_roots(tmp_path / "repo", home), (tmp_path / "home" / ".claude" / "jobs",))
    guard.active = True
    return guard, home


@pytest.mark.parametrize("event,args", [
    ("open", ("{home}/.cache/content-farm/heavy-queue/x.json", "w", 0)),
    ("open", ("{home}/.claude/settings.json", None, os.O_WRONLY | os.O_CREAT)),
    ("os.mkdir", ("{home}/orchestrator/new", 0o777, -1)),
    ("os.rename", ("{repo}/x.tmp", "{home}/.local/share/content-farm-music/x", -1, -1)),
    ("shutil.rmtree", ("{repo}/output/cowos", None)),
    ("subprocess.Popen", ("python3", ["python3", "{home}/orchestrator/orch_mail.py", "put"], None, None)),
])
def test_guard_blocks_writes_under_protected_roots(tmp_path, event, args):
    guard, home = _guard(tmp_path)
    filled = tuple(a.format(home=home, repo=tmp_path / "repo") if isinstance(a, str) else
                   [x.format(home=home) for x in a] if isinstance(a, list) else a for a in args)
    with pytest.raises(SharedPathWrite):
        guard(event, filled)
    assert len(guard.violations) == 1


@pytest.mark.parametrize("event,args", [
    ("open", ("{home}/.claude/settings.json", "r", 0)),                 # reads are fine
    ("open", ("{home}/.local/share/voxcpm2/hf/hub/config.json", "rb", os.O_RDONLY)),
    ("open", ("{home}/.claude/jobs/abc/tmp/pytest-1/x", "w", 0)),       # temp dir inside a protected root
    ("os.mkdir", ("{repo}/tests/fixtures/new", 0o777, -1)),
    ("subprocess.Popen", ("{home}/.local/share/qwen3-tts/.venv/bin/python", ["py", "-c", "1"], None, None)),
])
def test_guard_allows_reads_temp_and_repo_writes(tmp_path, event, args):
    guard, home = _guard(tmp_path)
    filled = tuple(a.format(home=home, repo=tmp_path / "repo") if isinstance(a, str) else a for a in args)
    guard(event, filled)
    assert guard.violations == []


def test_installed_guard_stops_a_real_write_before_it_happens():
    """Control: the live hook fires on the real ~/.cache/content-farm (and creates nothing)."""
    probe = REAL_HOME / ".cache" / "content-farm" / "heavy-queue" / "__guard_probe__.json"
    before = len(conftest.SHARED_PATH_GUARD.violations)
    with pytest.raises(SharedPathWrite):
        probe.write_text("{}", encoding="utf-8")
    assert not probe.exists()
    del conftest.SHARED_PATH_GUARD.violations[before:]      # expected hit; keep the teardown check green


def test_main_checkout_of_a_worktree(tmp_path):
    main = tmp_path / "main"
    worktree = main / ".claude" / "worktrees" / "wt"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {main}/.git/worktrees/wt\n", encoding="utf-8")
    assert main_checkout(worktree) == main
    assert main_checkout(main) == main
