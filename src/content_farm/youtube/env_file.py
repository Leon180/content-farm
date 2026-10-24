"""Append or replace a single KEY=VALUE line in a .env file (never prints values)."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class EnvVarExistsError(RuntimeError):
    """The variable is already defined and replace was not requested."""


def env_var_exists(path: Path, name: str) -> bool:
    """True if ``name`` has an assignment line in the file."""
    if not path.is_file():
        return False
    prefix = f"{name}="
    return any(
        line.lstrip().removeprefix("export ").startswith(prefix)
        for line in path.read_text(encoding="utf-8").splitlines()
    )


def set_env_var(path: Path, name: str, value: str, *, replace: bool = False) -> str:
    """Append ``name=value``; return ``"appended"`` or ``"replaced"``.

    Raises ``EnvVarExistsError`` if present and ``replace`` is False. Other lines
    are preserved byte-for-byte; the write is atomic and keeps file permissions.
    """
    if not _NAME_RE.match(name):
        raise ValueError(f"Invalid env var name: {name!r}")
    if not value or "\n" in value or "\r" in value:
        raise ValueError("Env var value must be a non-empty single line")

    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    exists = env_var_exists(path, name)
    if exists and not replace:
        raise EnvVarExistsError(f"{name} already exists in {path}; pass replace=True")

    if exists:
        prefix = f"{name}="
        lines = [
            f"{name}={value}\n"
            if line.lstrip().removeprefix("export ").startswith(prefix)
            else line
            for line in existing.splitlines(keepends=True)
        ]
        new_text = "".join(lines)
        outcome = "replaced"
    else:
        sep = "" if not existing or existing.endswith("\n") else "\n"
        new_text = f"{existing}{sep}{name}={value}\n"
        outcome = "appended"

    _atomic_write(path, new_text)
    return outcome


def _atomic_write(path: Path, text: str) -> None:
    mode = path.stat().st_mode & 0o777 if path.is_file() else 0o600
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
