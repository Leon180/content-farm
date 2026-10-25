"""Hooks ledger (quality v5 item 7): every thread the piece opens, and whether it was closed.

A video that asks "why has nobody filmed one alive?" in the first minute and never answers has cheated its viewer
(the retention report calls this the loudest reason people feel misled). The article stage writes ``hooks_ledger.json``
next to ``article.md``; the deck stage fills in which slide plants and which slide pays off each hook. The script panel's
professional reads the rendered ``hooks.txt`` and is told to flag every hook still open at the end. (The "foreshadowing
ledger" idea is InkOS's; the format and the checks here are ours.)

    {"version": 1, "hooks": [
      {"id": "h1", "kind": "question", "text": "為什麼這麼晚才拍到活的？",
       "planted": "s02", "payoff": "s24", "status": "paid", "note": ""}]}

``kind``: question | promise | foreshadow | tease.  ``status``: open | paid | dropped (dropped = deliberately removed,
needs a ``note``).  ``planted`` / ``payoff``: a slide id once the deck exists (an article section title before that).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

LEDGER = "hooks_ledger.json"
KINDS = ("question", "promise", "foreshadow", "tease")
STATUSES = ("open", "paid", "dropped")
DEFAULT_MAX_OPEN = 0          # a finished script leaves no open hook unless it says why


@dataclass(frozen=True)
class HookIssue:
    code: str
    hook_id: str
    message: str
    severity: str = "error"


def load(run_dir: Path) -> dict | None:
    path = run_dir / LEDGER
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("hooks"), list):
        raise ValueError(f"{LEDGER}: expected an object with a 'hooks' list")
    return data


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate(data: dict) -> list[HookIssue]:
    """Structure only: unique ids, known kind / status, text present, a note for every dropped hook."""
    issues: list[HookIssue] = []
    seen: set[str] = set()
    for index, hook in enumerate(data.get("hooks", [])):
        hid = _text(hook.get("id")) if isinstance(hook, dict) else ""
        if not hid:
            issues.append(HookIssue("hook-id", f"#{index}", "hook without an id"))
            continue
        if hid in seen:
            issues.append(HookIssue("hook-duplicate", hid, "duplicate hook id"))
        seen.add(hid)
        if hook.get("kind") not in KINDS:
            issues.append(HookIssue("hook-kind", hid, f"kind must be one of {', '.join(KINDS)}"))
        if hook.get("status") not in STATUSES:
            issues.append(HookIssue("hook-status", hid, f"status must be one of {', '.join(STATUSES)}"))
        if not _text(hook.get("text")):
            issues.append(HookIssue("hook-text", hid, "hook has no text"))
        if hook.get("status") == "dropped" and not _text(hook.get("note")):
            issues.append(HookIssue("hook-dropped-note", hid, "a dropped hook needs a note saying why"))
    return issues


def check_against_deck(data: dict, slide_order: list[str]) -> list[HookIssue]:
    """Does the deck keep what the ledger promises? Open hooks, payoffs before plants, ids that match no slide."""
    position = {sid: i for i, sid in enumerate(slide_order)}
    issues: list[HookIssue] = []
    for hook in data.get("hooks", []):
        if not isinstance(hook, dict):
            continue
        hid, status = _text(hook.get("id")), hook.get("status")
        planted, payoff = _text(hook.get("planted")), _text(hook.get("payoff"))
        if status == "open":
            issues.append(HookIssue("hook-open", hid, f"hook {hid} ({_text(hook.get('text'))[:30]}) is planted"
                                                      f"{' at ' + planted if planted else ''} and never paid off"))
        if status == "paid" and not payoff:
            issues.append(HookIssue("hook-no-payoff", hid, "status is paid but no payoff slide is named"))
        for label, ref in (("planted", planted), ("payoff", payoff)):
            if ref and slide_order and ref not in position and ref.startswith("s"):
                issues.append(HookIssue("hook-missing-slide", hid, f"{label} slide {ref!r} is not in the deck"))
        if planted in position and payoff in position and position[payoff] <= position[planted]:
            issues.append(HookIssue("hook-order", hid, f"payoff {payoff} does not come after planting {planted}"))
    return issues


def render(data: dict, slide_order: list[str] | None = None) -> str:
    """The text the script reviewer reads: one line per hook with its status, then what is still open."""
    lines = ["伏筆帳本（每條線：誰埋、誰收、狀態）"]
    for hook in data.get("hooks", []):
        lines.append(f"- {hook.get('id')} [{hook.get('kind')}] {hook.get('text')} ｜ 埋：{hook.get('planted') or '?'} "
                     f"｜ 收：{hook.get('payoff') or '（未收）'} ｜ {hook.get('status')}"
                     + (f" ｜ {hook['note']}" if hook.get("note") else ""))
    problems = check_against_deck(data, slide_order or [])
    if problems:
        lines.append("")
        lines.append("機器檢查到的問題：")
        lines += [f"- {p.message}" for p in problems]
    return "\n".join(lines) + "\n"
