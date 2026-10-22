"""Per-seat result cache (cf-cost-fix, Leon 2026-10-22: "不要在重複任務上花 token").

A reviewer's answer is a function of what it saw. The key is a hash of: the stage, the seat (``rid``, which carries
the persona id — not its per-round wording), the prompt with the persona wording neutralised (role brief, rubric,
task and rules, so editing a rubric changes the key), the *content* of the files that seat is shown, its schema,
tools, model and effort. Same key → the earlier answer is reused at no cost; nothing else is.

Volatile bookkeeping inside the material (timestamps, build timings) is stripped before hashing, and derived files
(a contact sheet is a picture of other files) are left out, so a "rework" that changed nothing hits the cache.
Only valid answers are cached; a seat that failed is run again.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CACHE_DIR = Path("review") / ".cache"
VOLATILE_KEYS = frozenset({"generated_at", "build_seconds", "at", "built_at", "reused", "elapsed", "elapsed_s"})
JSON_SUFFIX = ".json"


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in sorted(value.items()) if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def file_digest(path: Path) -> str:
    """Content hash of one file; JSON files without their volatile bookkeeping fields."""
    data = path.read_bytes()
    if path.suffix == JSON_SUFFIX:
        try:
            data = json.dumps(_strip(json.loads(data)), ensure_ascii=False, sort_keys=True).encode("utf-8")
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return hashlib.sha256(data).hexdigest()[:16]


def content_digest(root: Path, names: list[str], *, derived: frozenset[str] = frozenset(),
                   override: str | None = None) -> str:
    """Digest of the files a seat is shown (paths relative to ``root``). ``override``: a digest the material
    builder computed itself (shuffled candidate lists, media identities); ``derived`` files are skipped."""
    if override:
        return override
    parts = [f"{name}={file_digest(root / name)}" for name in names if name not in derived and (root / name).is_file()]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:24]


def seat_key(*, stage: str, rid: str, prompt: str, schema: dict[str, Any], tools: tuple[str, ...], model: str,
             effort: str, content: str, extra: str = "") -> str:
    blob = json.dumps({"stage": stage, "rid": rid, "prompt": prompt, "schema": schema, "tools": list(tools),
                       "model": model, "effort": effort, "content": content, "extra": extra},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _path(run_dir: Path, key: str) -> Path:
    return run_dir / CACHE_DIR / f"{key}.json"


def load(run_dir: Path, key: str) -> dict[str, Any] | None:
    path = _path(run_dir, key)
    if not path.is_file():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return entry if isinstance(entry, dict) and isinstance(entry.get("output"), dict) else None


def save(run_dir: Path, key: str, *, output: dict[str, Any], result: dict[str, Any], label: str) -> None:
    """Remember a valid answer: its output plus what it cost (so a hit can report what it saved)."""
    path = _path(run_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: result.get(k) for k in ("model", "effort", "models_used", "seconds", "cost_usd", "tokens")}
    path.write_text(json.dumps({"output": output, "result": keep, "from": label}, ensure_ascii=False), encoding="utf-8")
