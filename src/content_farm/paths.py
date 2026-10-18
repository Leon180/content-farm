"""Machine-wide paths shared by every checkout and worker: the heavy-work queue, the legacy
render / local-TTS locks and the orchestrator's mailbox.

Each one resolves at call time and has an environment override, so a test run (tests/conftest.py)
can point all of them at a temporary directory and nothing written there reaches the real ones.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else default


def cache_root() -> Path:
    """``~/.cache/content-farm`` (``CF_CACHE_ROOT``): locks and the heavy queue live here."""
    return _env_path("CF_CACHE_ROOT", Path.home() / ".cache" / "content-farm")


def heavy_queue_dir() -> Path:
    """Tickets, ``heavy.lock`` and ``history.jsonl`` of the machine-wide queue (``CF_HEAVY_QUEUE_DIR``)."""
    return _env_path("CF_HEAVY_QUEUE_DIR", cache_root() / "heavy-queue")


def render_lock_path() -> Path:
    """The legacy ``runner.render_lock`` file, still taken so branches without the queue see the machine busy."""
    return cache_root() / "render.lock"


def local_tts_lock_path() -> Path:
    """The legacy ``voice.local_worker`` lock (``CF_LOCAL_TTS_LOCK_PATH`` also overrides it via Settings)."""
    return _env_path("CF_LOCAL_TTS_LOCK_PATH", cache_root() / "local_tts.lock")


def orch_mail_script() -> Path:
    """``~/orchestrator/orch_mail.py`` (``CF_ORCH_MAIL``); a missing file means no mail is sent."""
    return _env_path("CF_ORCH_MAIL", Path.home() / "orchestrator" / "orch_mail.py")


def orch_mail_dir() -> Path:
    """The personal pointer store the queue reports stalls to (``CF_ORCH_MAIL_DIR``)."""
    return _env_path("CF_ORCH_MAIL_DIR", Path.home() / ".claude" / "orch-mail-personal")
