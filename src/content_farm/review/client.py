"""Run one reviewer as a headless ``claude -p`` subprocess on the Claude subscription.

Never ``--bare`` (it reads only ANTHROPIC_API_KEY = metered billing) and never pass an API key
to the child: ``ANTHROPIC_API_KEY`` / ``CF_ANTHROPIC_API_KEY`` / ``ANTHROPIC_AUTH_TOKEN`` are
removed from its environment. model / effort / schema come from review_panels.yaml; output that
does not match the schema is retried, then counted as a failed seat (the gate stays closed).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from content_farm.review.schemas import validate

CLAUDE_BIN = "claude"


def claude_bin() -> str:
    """``CF_CLAUDE_BIN`` overrides the binary (tests point it at a stub so nothing is ever billed)."""
    return os.environ.get("CF_CLAUDE_BIN", CLAUDE_BIN)
PAID_ENV = ("ANTHROPIC_API_KEY", "CF_ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


@dataclass(frozen=True)
class Call:
    rid: str
    prompt: str
    schema: dict[str, Any]
    model: str
    effort: str
    tools: tuple[str, ...] = ("Read",)
    cwd: Path = Path(".")
    add_dirs: tuple[Path, ...] = ()
    timeout_s: int = 1200
    retries: int = 1
    write_tools: bool = False          # producer agents may write files in cwd
    env: tuple[tuple[str, str], ...] = ()   # extra child env (never an API key: PAID_ENV is removed after)


@dataclass(frozen=True)
class CallResult:
    rid: str
    ok: bool
    output: dict[str, Any] | None
    errors: tuple[str, ...]
    model: str
    effort: str
    models_used: tuple[str, ...] = ()
    seconds: float = 0.0
    cost_usd: float = 0.0              # the CLI's notional figure; billed to the subscription
    tokens: dict[str, int] = field(default_factory=dict)
    attempts: int = 1
    infra: bool = False                # failed because the plumbing failed (network, exit, timeout)

    def to_json(self) -> dict[str, Any]:
        return {"rid": self.rid, "ok": self.ok, "errors": list(self.errors), "model": self.model,
                "effort": self.effort, "models_used": list(self.models_used), "seconds": self.seconds,
                "cost_usd": self.cost_usd, "tokens": self.tokens, "attempts": self.attempts, "infra": self.infra}


TOKEN_KEYS = ("input", "output", "cache_read", "cache_write")


def call_usage(result: dict[str, Any]) -> dict[str, Any]:
    """The usage part of a ``CallResult.to_json()`` (a seat in a scorecard, a producers.jsonl line)."""
    return {"model": result.get("model", ""), "effort": result.get("effort", ""),
            "models_used": list(result.get("models_used") or []), "seconds": float(result.get("seconds") or 0),
            "cost_usd": float(result.get("cost_usd") or 0), "attempts": int(result.get("attempts") or 1),
            "tokens": {k: int((result.get("tokens") or {}).get(k) or 0) for k in TOKEN_KEYS}}


Runner = Callable[[list[str], str, Path, dict[str, str], int], tuple[int, str, str]]


def _subprocess(argv: list[str], stdin: str, cwd: Path, env: dict[str, str], timeout: int) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(argv, input=stdin, cwd=cwd, env=env, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except OSError as exc:
        return 127, "", f"{type(exc).__name__}: {exc}"
    return proc.returncode, proc.stdout, proc.stderr


def child_env(base: dict[str, str] | None = None, extra: tuple[tuple[str, str], ...] = ()) -> dict[str, str]:
    env = {**(os.environ if base is None else base), **dict(extra)}
    for key in PAID_ENV:
        env.pop(key, None)
    return env


def argv_for(call: Call) -> list[str]:
    if "--bare" in call.tools:
        raise ValueError("--bare would bill the API key; never allowed")
    names = ",".join(dict.fromkeys(t.split("(")[0] for t in call.tools))   # --tools takes bare names
    allowed = ",".join(call.tools)                                          # --allowed-tools may scope them
    argv = [claude_bin(), "-p", "--model", call.model, "--effort", call.effort, "--output-format", "json",
            "--json-schema", json.dumps(call.schema, ensure_ascii=False), "--no-session-persistence",
            "--strict-mcp-config", "--disable-slash-commands", "--tools", names, "--allowed-tools", allowed,
            "--permission-mode", "acceptEdits" if call.write_tools else "dontAsk"]
    for directory in call.add_dirs:
        argv += ["--add-dir", str(directory)]
    return argv


def _parse(stdout: str) -> tuple[dict[str, Any] | None, dict[str, Any], str]:
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        return None, {}, f"stdout is not JSON: {stdout[:200]!r}"
    if not isinstance(envelope, dict):
        return None, {}, "stdout JSON is not an object"
    if envelope.get("is_error"):
        return None, envelope, f"claude error: {str(envelope.get('result'))[:300]}"
    output = envelope.get("structured_output")
    if output is None and isinstance(envelope.get("result"), str):
        try:
            output = json.loads(envelope["result"])
        except json.JSONDecodeError:
            return None, envelope, "no structured_output and result is not JSON"
    return (output if isinstance(output, dict) else None), envelope, ""


def model_matches(requested: str, used: tuple[str, ...]) -> bool:
    """The requested tier (opus/sonnet/haiku alias) must be among the models that answered."""
    return any(requested in name for name in used)


INFRA_RETRIES = 3          # network drops (2026-10-18 13:32, 15:59): retried, never counted as a review
INFRA_BACKOFF_S = 60.0
_INFRA_HINT = ("ENOTFOUND", "ECONNRESET", "ETIMEDOUT", "ECONNREFUSED", "network", "Connection", "overloaded",
               "rate limit", "529", "503", "502", "timeout", "socket")


def is_infra(code: int, problem: str, envelope: dict[str, Any]) -> bool:
    """A failure of the plumbing (no answer at all), not of the reviewer's answer."""
    if problem.startswith("schema:"):
        return False
    if code != 0 or problem.startswith("stdout is not JSON"):
        return True
    text = f"{problem} {envelope.get('api_error_status') or ''}"
    return any(hint.lower() in text.lower() for hint in _INFRA_HINT)


def run_call(call: Call, *, runner: Runner = _subprocess, log_dir: Path | None = None,
             sleep: Callable[[float], None] = time.sleep) -> CallResult:
    errors: list[str] = []
    started = time.monotonic()
    cost, tokens, used = 0.0, {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}, ()
    attempt, answers, infra_left, infra = 0, 0, INFRA_RETRIES, False
    while answers < call.retries + 1:
        attempt += 1
        code, stdout, stderr = runner(argv_for(call), call.prompt, call.cwd, child_env(extra=call.env), call.timeout_s)
        if log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / f"{call.rid}.attempt{attempt}.json").write_text(stdout or stderr, encoding="utf-8")
        output, envelope, problem = _parse(stdout) if code == 0 else (None, {}, f"exit {code}: {stderr[-300:]}")
        infra = output is None and is_infra(code, problem, envelope)
        if infra and infra_left > 0:
            infra_left -= 1
            errors.append(f"attempt {attempt}: infrastructure, retrying: {problem[:120]}")
            sleep(INFRA_BACKOFF_S * (INFRA_RETRIES - infra_left))
            continue
        answers += 1
        cost += float(envelope.get("total_cost_usd") or 0)
        usage = envelope.get("usage") or {}
        tokens = {"input": tokens["input"] + int(usage.get("input_tokens") or 0),
                  "output": tokens["output"] + int(usage.get("output_tokens") or 0),
                  "cache_read": tokens["cache_read"] + int(usage.get("cache_read_input_tokens") or 0),
                  "cache_write": tokens["cache_write"] + int(usage.get("cache_creation_input_tokens") or 0)}
        used = tuple(sorted(set(used) | set((envelope.get("modelUsage") or {}).keys())))
        if output is not None:
            problems = validate(output, call.schema)
            if not problems:
                seconds = round(time.monotonic() - started, 1)
                if used and not model_matches(call.model, used):
                    return CallResult(call.rid, False, output, (f"model mismatch: asked {call.model}, got {used}",),
                                      call.model, call.effort, used, seconds, round(cost, 4), tokens, attempt)
                return CallResult(call.rid, True, output, (), call.model, call.effort, used, seconds,
                                  round(cost, 4), tokens, attempt)
            problem = "schema: " + "; ".join(problems[:5])
        errors.append(f"attempt {attempt}: {problem}")
    return CallResult(call.rid, False, None, tuple(errors), call.model, call.effort, used,
                      round(time.monotonic() - started, 1), round(cost, 4), tokens, attempt, infra=infra)
