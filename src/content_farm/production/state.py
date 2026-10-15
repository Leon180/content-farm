"""``<run-dir>/production.json``: what ran, what is waiting, who approved what.

Approvals are bound to a fingerprint of the artifacts the reviewer looked at.
If any of those files change afterwards (deck edited, B-roll swapped), the
approval no longer matches and the runner stops at the gate again.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = "production.json"
_SMALL_FILE = 5 * 1024 * 1024  # hash contents below this; size+mtime above (videos)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fingerprint(run_dir: Path, patterns: tuple[str, ...]) -> str:
    """Stable digest of every file matching ``patterns`` (globs relative to run_dir).

    Missing files simply do not contribute, so "nothing there yet" has its own
    digest that differs from "file exists"."""
    digest = hashlib.sha256()
    for pattern in patterns:
        for path in sorted(run_dir.glob(pattern)):
            if not path.is_file():
                continue
            digest.update(path.relative_to(run_dir).as_posix().encode())
            stat = path.stat()
            if stat.st_size <= _SMALL_FILE:
                digest.update(hashlib.sha256(path.read_bytes()).digest())
            else:
                digest.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode())
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class StepRecord:
    status: str                 # done | failed | skipped | waiting
    finished_at: str
    seconds: float = 0.0
    exit_code: int | None = None
    inputs: str = ""            # fingerprint of the step's inputs when it ran
    note: str = ""


@dataclass(frozen=True)
class Decision:
    gate: str
    verdict: str                # approved | rejected
    fingerprint: str
    at: str
    by: str = "leon"
    note: str = ""


@dataclass(frozen=True)
class RunState:
    channel: str
    steps: dict[str, StepRecord] = field(default_factory=dict)
    decisions: dict[str, Decision] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    def with_step(self, name: str, record: StepRecord) -> RunState:
        return replace(self, steps={**self.steps, name: record})

    def with_decision(self, decision: Decision) -> RunState:
        return replace(self, decisions={**self.decisions, decision.gate: decision})

    def approved(self, gate: str, current_fingerprint: str) -> bool:
        decision = self.decisions.get(gate)
        return (decision is not None and decision.verdict == "approved"
                and decision.fingerprint == current_fingerprint)

    def to_json(self) -> str:
        return json.dumps({
            "version": 1,
            "channel": self.channel,
            "created_at": self.created_at,
            "steps": {name: vars(rec) for name, rec in self.steps.items()},
            "decisions": {gate: vars(dec) for gate, dec in self.decisions.items()},
        }, ensure_ascii=False, indent=2)


def load_state(run_dir: Path, channel: str) -> RunState:
    path = run_dir / STATE_FILE
    if not path.is_file():
        return RunState(channel=channel)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("channel") != channel:
        raise ValueError(f"{path} belongs to channel {data.get('channel')!r}, not {channel!r}")
    return RunState(
        channel=channel,
        created_at=data.get("created_at", now_iso()),
        steps={name: StepRecord(**rec) for name, rec in data.get("steps", {}).items()},
        decisions={gate: Decision(**dec) for gate, dec in data.get("decisions", {}).items()},
    )


def read_channel_code(run_dir: Path) -> str:
    path = run_dir / STATE_FILE
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found; start the run with `produce.py run --channel …`")
    channel = json.loads(path.read_text(encoding="utf-8")).get("channel")
    if not isinstance(channel, str) or not channel:
        raise ValueError(f"{path} has no channel")
    return channel


def save_state(run_dir: Path, state: RunState) -> Path:
    path = run_dir / STATE_FILE
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(state.to_json(), encoding="utf-8")
    tmp.replace(path)
    return path
