"""Is a shell command heavy local work, and did it come through the queue? (for the
orchestrator's PreToolUse hook, Leon 2026-10-18). Patterns live in ``heavy_work.json``.

Rule: inside content-farm, a Bash command that matches a heavy pattern is blocked unless the
program it runs is an allowed wrapper (``scripts/heavy …`` or ``scripts/produce.py …``), or it is a
read-only probe (``ffprobe``, ``ffmpeg -version`` …). Stdlib only.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[3] / "channels" / "shared" / "heavy_work.json"
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SEPARATORS = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")


@dataclass(frozen=True)
class Verdict:
    heavy: bool
    allowed: bool
    matched: str = ""
    why: str = ""

    @property
    def block(self) -> bool:
        return self.heavy and not self.allowed


def _config(path: Path = CONFIG) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _program(segment: str) -> list[str]:
    try:
        words = shlex.split(segment)
    except ValueError:
        words = segment.split()
    while words and (_ASSIGN.match(words[0]) or words[0] in ("env", "nohup", "time", "exec", "command")):
        words = words[1:]
    if words and Path(words[0]).name.startswith("python") and len(words) > 1:
        rest = words[1:]
        while rest and rest[0].startswith("-") and rest[0] != "-m":    # interpreter flags (-u, -I, -X …) only
            rest = rest[2:] if rest[0] in ("-X", "-W") else rest[1:]
        return rest
    return words


def _wrapped(words: list[str], wrappers: list[str]) -> bool:
    return bool(words) and any(words[0].endswith(w) for w in wrappers)


def classify(command: str, config: dict | None = None) -> Verdict:
    config = config or _config()
    wrappers = config.get("allowed_wrappers", [])
    read_only = config.get("read_only_commands", [])
    for segment in (s for s in _SEPARATORS.split(command.strip()) if s):
        words = _program(segment)
        text = " ".join(words)
        if _wrapped(words, wrappers):
            continue                                  # this part goes through the queue
        if any(text.startswith(r) or text == r.strip() for r in read_only):
            continue
        for rule in config.get("commands", []):
            if re.search(rule["pattern"], text):
                return Verdict(True, False, rule["name"],
                               f"heavy ({rule['name']}) outside the queue: run it as `scripts/heavy --label … -- {text[:60]}`")
    return Verdict(False, True)
