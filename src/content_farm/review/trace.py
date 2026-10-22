"""Where a producer agent's minutes go (Leon 2026-10-23: one deck rewrite takes 11–17 min).

``claude -p --output-format stream-json --verbose`` prints one JSON event per line as the agent works. This
runner reads them live, stamps each with the seconds since the start, and returns the final ``result`` event
(the same envelope ``--output-format json`` gives) with a compact ``cf_trace`` list added, so the caller
parses it exactly as before. ``summarize`` turns that list into turn counts, per-tool counts and seconds,
and how long the model itself spent between tool results.

Trace rows: ``[t, kind, name, detail]`` with kind ``model`` (an assistant message), ``tool_use`` or
``tool_result``; ``name`` is the tool for ``tool_use`` / ``tool_result``.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

DETAIL_CHARS = 90


def _detail(tool_input: dict[str, Any]) -> str:
    for key in ("file_path", "path", "command", "pattern", "url", "query"):
        if tool_input.get(key):
            return str(tool_input[key])[:DETAIL_CHARS]
    return ""


def rows_of(event: dict[str, Any], at: float) -> list[list[Any]]:
    """Trace rows for one stream event (empty for events that carry no step of the agent's work)."""
    kind = event.get("type")
    blocks = (event.get("message") or {}).get("content")
    if kind not in ("assistant", "user") or not isinstance(blocks, list):
        return []
    rows: list[list[Any]] = []
    if kind == "assistant":
        usage = (event["message"].get("usage") or {})
        rows.append([at, "model", "", {"out": usage.get("output_tokens"),
                                       "blocks": [b.get("type") for b in blocks if isinstance(b, dict)]}])
        rows += [[at, "tool_use", b.get("name", ""), {"id": b.get("id"), "arg": _detail(b.get("input") or {})}]
                 for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
    else:
        rows += [[at, "tool_result", "", {"id": b.get("tool_use_id"), "error": bool(b.get("is_error"))}]
                 for b in blocks if isinstance(b, dict) and b.get("type") == "tool_result"]
    return rows


def stream_runner(argv: list[str], stdin: str, cwd: Path, env: dict[str, str], timeout: int) -> tuple[int, str, str]:
    """Same contract as ``client._subprocess``; stdout is the final result envelope plus ``cf_trace``."""
    started = time.monotonic()
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=cwd, env=env, text=True)
    except OSError as exc:
        return 127, "", f"{type(exc).__name__}: {exc}"
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    errors: list[str] = []
    drain = threading.Thread(target=lambda: errors.append(proc.stderr.read() if proc.stderr else ""), daemon=True)
    drain.start()
    try:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(stdin)
        proc.stdin.close()
        trace: list[list[Any]] = []
        result: dict[str, Any] | None = None
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("type") == "result":
                result = event
            elif isinstance(event, dict):
                trace += rows_of(event, round(time.monotonic() - started, 2))
        code = proc.wait()
    finally:
        timer.cancel()
        drain.join(timeout=5)
    if time.monotonic() - started >= timeout:
        return 124, "", f"timeout after {timeout}s"
    stderr = "".join(errors)
    if result is None:
        return code or 1, "", stderr or "stream-json ended without a result event"
    return code, json.dumps({**result, "cf_trace": trace}, ensure_ascii=False), stderr


def summarize(trace: list[list[Any]]) -> dict[str, Any]:
    """Turns, tool counts / seconds, and the time between a tool result and the model's next message
    (the model thinking and writing) for one call."""
    uses: dict[str, tuple[float, str, str]] = {}
    tools: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0, "seconds": 0.0})
    model_messages, model_seconds, last_boundary, written = 0, 0.0, 0.0, []
    for at, kind, name, detail in trace:
        if kind == "model":
            model_messages += 1
            model_seconds += max(at - last_boundary, 0.0)
            last_boundary = at
        elif kind == "tool_use":
            uses[detail.get("id") or f"{at}"] = (at, name, detail.get("arg", ""))
            tools[name]["count"] += 1
            if name in ("Write", "Edit"):
                written.append(detail.get("arg", ""))
        elif kind == "tool_result":
            began = uses.get(detail.get("id") or "")
            if began is not None:
                tools[began[1]]["seconds"] += max(at - began[0], 0.0)
            last_boundary = at
    ended = trace[-1][0] if trace else 0.0
    return {"model_messages": model_messages, "model_seconds": round(model_seconds, 1), "ended_at_s": ended,
            "tools": {k: {"count": int(v["count"]), "seconds": round(v["seconds"], 1)} for k, v in tools.items()},
            "writes": {path: written.count(path) for path in sorted(set(written)) if path},
            "tool_errors": sum(1 for r in trace if r[1] == "tool_result" and r[3].get("error"))}
