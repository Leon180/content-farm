#!/usr/bin/env python3
"""How big is this session's conversation? Exit 3 when it is time to write the handoff and end (cf-cost-fix item 6).

Why: 73% of the 10-17..19 spend was cache re-reads of long conversations (worker prefixes 440-570k tokens). Each tool
call re-reads the whole prefix, so a conversation past ~300k tokens costs more per call than a fresh session that
reads a written handoff. The size is read, not guessed: the last main-thread assistant message in the transcript
carries the API's own usage (input + cache_creation + cache_read = the prefix that call read).

    python3 scripts/session_guard.py                       # newest transcript for the current directory
    python3 scripts/session_guard.py --transcript X.jsonl  # a specific session (e.g. the orchestrator's)
    python3 scripts/session_guard.py --hook                # PostToolUse hook: stdin JSON in, nudge out when over

Exit codes: 0 under the warn line, 1 over the warn line (80% of the limit), 3 over the limit, 2 cannot tell.
The limit comes from --limit, ``CF_SESSION_TOKEN_LIMIT`` or 300,000.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LIMIT = 300_000
WARN_SHARE = 0.8
TAIL_BYTES = 4 * 1024 * 1024        # the last assistant line is always near the end
PROJECTS = Path.home() / ".claude" / "projects"

HANDOFF_NUDGE = (
    "This conversation's context is {tokens:,} tokens (limit {limit:,}). Every tool call re-reads all of it. At the end of "
    "the current work segment: write the handoff into the progress log of your REPORT (what is done, what is next, exact "
    "commands, open decisions), commit, tell main to continue in a new session, and stop. Do not start a new segment here.")


@dataclass(frozen=True)
class Size:
    tokens: int
    model: str
    lines: int
    path: Path


def project_dir(cwd: Path) -> Path:
    """Claude Code keeps a project's transcripts in ~/.claude/projects/<cwd with / and . replaced by ->."""
    return PROJECTS / str(cwd).replace("/", "-").replace(".", "-")


def newest_transcript(cwd: Path) -> Path | None:
    files = sorted(project_dir(cwd).glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _tail_lines(path: Path) -> list[str]:
    with path.open("rb") as handle:
        size = path.stat().st_size
        handle.seek(max(0, size - TAIL_BYTES))
        data = handle.read()
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[1:] if size > TAIL_BYTES else lines       # the first line of a cut chunk is partial


def context_size(path: Path) -> Size | None:
    """Prefix tokens the last main-thread assistant message read; None when the transcript has no usage yet."""
    lines = _tail_lines(path)
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = row.get("message") if isinstance(row, dict) else None
        usage = message.get("usage") if isinstance(message, dict) else None
        if row.get("type") != "assistant" or row.get("isSidechain") or not isinstance(usage, dict):
            continue
        tokens = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                       "cache_read_input_tokens"))
        return Size(tokens, str(message.get("model") or ""), len(lines), path)
    return None


def limit_from(arg: int | None) -> int:
    return arg if arg is not None else int(os.environ.get("CF_SESSION_TOKEN_LIMIT", DEFAULT_LIMIT))


def verdict(size: Size, limit: int) -> int:
    return 3 if size.tokens >= limit else 1 if size.tokens >= WARN_SHARE * limit else 0


def run_hook(limit: int) -> int:
    """PostToolUse hook: reads the hook payload, prints additionalContext once the session is over the limit."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    transcript = payload.get("transcript_path")
    size = context_size(Path(transcript)) if transcript else None
    if size is None or verdict(size, limit) < 3:
        return 0
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": HANDOFF_NUDGE.format(tokens=size.tokens, limit=limit)}}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--hook", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    limit = limit_from(args.limit)
    if args.hook:
        return run_hook(limit)
    path = args.transcript or newest_transcript(Path.cwd())
    size = context_size(path) if path is not None and path.is_file() else None
    if size is None:
        print("session_guard: no transcript with usage found", file=sys.stderr)
        return 2
    code = verdict(size, limit)
    if args.json:
        print(json.dumps({"tokens": size.tokens, "limit": limit, "model": size.model, "exit": code,
                          "transcript": str(size.path)}))
    else:
        label = {0: "ok", 1: "WARN: approaching the limit", 3: "OVER: write the handoff and end this session"}[code]
        print(f"{size.tokens:,} tokens of {limit:,} ({size.tokens / limit:.0%}) — {label}")
    return code


if __name__ == "__main__":
    sys.exit(main())
