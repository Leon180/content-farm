"""Score ledger (Leon 2026-10-23): with ``policy.score_only`` no score blocks anything, so each gate's judged scores and
comments are kept per run in ``review/score_ledger.json`` next to empty fields for what the real audience did —
``views`` / ``retention`` / ``ctr`` are filled by hand after the video is up and compared with the scores later.
Also ``review/auto_fix.jsonl``: one line per fact / licence stage that was fixed without a re-check."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from content_farm.production.state import now_iso

LEDGER = "score_ledger.json"
AUTO_FIX_LOG = "auto_fix.jsonl"
AFTER_UPLOAD = {"views": None, "retention": None, "ctr": None}     # filled after the real upload


def _ledger_path(run_dir: Path) -> Path:
    return run_dir / "review" / LEDGER


def load(run_dir: Path) -> dict[str, Any]:
    path = _ledger_path(run_dir)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"version": 1, "after_upload": dict(AFTER_UPLOAD),
                                                                                 "stages": {}}


def record(run_dir: Path, gate: str, stage_name: str, card: dict[str, Any], *, waived: bool = False) -> Path:
    """Add / replace this gate's entry; the after-upload fields already filled in are kept."""
    ledger = load(run_dir)
    verdict = card.get("verdict") or {}
    entry = {"gate": gate, "stage": stage_name, "round": card.get("round"), "recorded_at": now_iso(),
             "scores": verdict.get("scores"), "passed_thresholds": bool(verdict.get("pass")), "waived": waived,
             "unmet": list(verdict.get("reasons", [])),
             # concrete observations (what the reviewers saw, quoted) kept apart from the scores above
             "observations": list(card.get("observations") or []),
             "comments": [{k: i.get(k) for k in ("ref", "category", "severity", "problem", "fix", "who")}
                          for i in verdict.get("issues", [])]}
    ledger["stages"] = {**ledger["stages"], gate: entry}
    path = _ledger_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path


def record_qc(run_dir: Path, name: str, data: dict[str, Any]) -> Path:
    """Keep an automatic QC measurement (e.g. ``static_scan`` dead zones) in the ledger next to the judged scores, so it can
    be compared with what the audience did. Replaces the entry of the same name; everything else is kept."""
    ledger = load(run_dir)
    ledger["qc"] = {**ledger.get("qc", {}), name: {"recorded_at": now_iso(), **data}}
    path = _ledger_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path


def log_auto_fix(run_dir: Path, gate: str, stage_name: str, **fields: Any) -> None:
    path = run_dir / "review" / AUTO_FIX_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps({"at": now_iso(), "gate": gate, "stage": stage_name, **fields}, ensure_ascii=False,
                             default=str) + "\n")


def auto_fix_issued(run_dir: Path, gate: str, round_no: int, inputs: str) -> bool:
    """Was the one automatic fix for the material this round judged (``inputs``) already handed to a producer?"""
    path = run_dir / "review" / AUTO_FIX_LOG
    if not path.is_file():
        return False
    rows = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return any(r.get("gate") == gate and r.get("round") == round_no and r.get("inputs") == inputs and r.get("event") == "fix_issued" for r in rows)
