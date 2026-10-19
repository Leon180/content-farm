"""Fail any test that writes to a real machine-wide path (heavy queue, locks, orchestrator, ~/.claude,
~/.local/share, the main checkout's output/).

A ``sys.addaudithook`` hook sees every write-mode ``open``, ``mkdir``, rename, remove, copy and
subprocess launch in this process. A write under a protected root raises ``SharedPathWrite`` before
it happens and is recorded, so a test whose code swallows the error still fails at teardown.
Writes under the temp dir are always allowed (it can sit inside a protected root, e.g. a job tmp).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
# audit event -> indexes of the path arguments it writes to
PATH_EVENTS: dict[str, tuple[int, ...]] = {
    "os.mkdir": (0,), "os.rename": (0, 1), "os.remove": (0,), "os.rmdir": (0,), "os.symlink": (1,),
    "os.link": (1,), "os.truncate": (0,), "os.chmod": (0,), "os.chown": (0,), "os.utime": (0,),
    "shutil.copyfile": (1,), "shutil.copytree": (1,), "shutil.move": (0, 1), "shutil.rmtree": (0,),
}


class SharedPathWrite(RuntimeError):
    """A test tried to write to a real shared path (not an OSError, so ``except OSError`` cannot hide it)."""


def main_checkout(repo: Path) -> Path:
    """The main checkout of this repo: a worktree's ``.git`` file points into ``<main>/.git/worktrees/``."""
    dot_git = repo / ".git"
    if dot_git.is_file():
        gitdir = Path(dot_git.read_text(encoding="utf-8").split("gitdir:", 1)[1].strip())
        return gitdir.parents[2]
    return repo


def protected_roots(repo: Path, home: Path | None = None) -> tuple[Path, ...]:
    home = home or Path.home()
    return (home / ".cache" / "content-farm", home / ".claude", home / "orchestrator", home / ".local" / "share",
            main_checkout(repo) / "output", repo / "output")


def _forms(path: Path) -> set[str]:
    return {os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.realpath(path))}


def _under(value: str, roots: set[str]) -> bool:
    return any(value == root or value.startswith(root + os.sep) for root in roots)


class Guard:
    def __init__(self, protected: tuple[Path, ...], allowed: tuple[Path, ...]) -> None:
        self.protected = set().union(*(_forms(p) for p in protected))
        self.allowed = set().union(*(_forms(p) for p in allowed))
        self.active = False
        self.violations: list[str] = []

    def blocks(self, raw: object, cwd: object = None) -> str | None:
        if isinstance(raw, int) or raw is None:
            return None
        try:
            text = os.fsdecode(raw)   # type: ignore[arg-type]
            base = os.fsdecode(cwd) if cwd is not None else os.getcwd()   # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        value = os.path.normcase(os.path.abspath(os.path.join(base, text)))
        if _under(value, self.allowed) or not _under(value, self.protected):
            return None
        return value

    def _deny(self, event: str, path: str) -> None:
        message = f"test wrote to a real shared path ({event}): {path}"
        self.violations.append(message)
        raise SharedPathWrite(message)

    def __call__(self, event: str, args: tuple) -> None:
        if not self.active:
            return
        if event == "open":
            path, mode, flags = (tuple(args) + (None, None))[:3]
            writes = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and bool(flags & WRITE_FLAGS))
            hit = self.blocks(path) if writes else None
        elif event in PATH_EVENTS:
            hit = next((h for i in PATH_EVENTS[event] if i < len(args) and (h := self.blocks(args[i]))), None)
        elif event == "subprocess.Popen":
            argv = args[1] if isinstance(args[1], (list, tuple)) else [args[1]]
            cwd = args[2] if len(args) > 2 else None
            hit = self.blocks(cwd) or next((h for a in list(argv)[1:] if (h := self.blocks(a, cwd))), None)
        else:
            return
        if hit:
            self._deny(event, hit)


def install(repo: Path) -> Guard:
    guard = Guard(protected_roots(repo), (Path(tempfile.gettempdir()),))
    sys.addaudithook(guard)
    return guard
