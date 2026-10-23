"""``news.py audit``: the run step around :mod:`claims` — check once, fix once, go on (Leon 2026-10-23).

Order of events for a script with problems under ``policy.fact_on_fail = auto_fix_then_pass``:

1. ``claims.audit`` lists every sentence of fact without a verifiable source;
2. ``claims.auto_fix`` deletes what cannot be sourced and rewrites what is sourced but badly attributed;
3. the corrected ``news_script.json`` replaces the draft (the draft is kept as ``news_script.draft.json``);
4. ``review/auto_fix.jsonl`` gets ``fix_issued`` + ``passed_without_recheck`` rows, ``review/fact_audit.json`` the
   errors and the fixes — and the run goes on. Nothing is re-checked by a reviewer.

With ``fact_on_fail = stop`` the same errors stop the run (exit 1) and nothing is touched.
The step is idempotent: the corrected script audits clean, and a re-run on it leaves the report alone.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from content_farm.production.news import claims
from content_farm.production.news import script as ns
from content_farm.production.news.series import NewsSeries
from content_farm.review import score_ledger

REPORT = "review/fact_audit.json"
HISTORY = "review/fact_audit.jsonl"
DRAFT = "news_script.draft.json"
GATE, STAGE = "script", "news_claims"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def was_fixed(run_dir: Path) -> bool:
    """Did the audit rewrite this run's script (then the usual length ranges are relaxed)?"""
    path = run_dir / REPORT
    if not path.is_file():
        return False
    report = json.loads(path.read_text(encoding="utf-8"))
    return bool(report.get("fixes")) and report.get("after_sha") == _sha(run_dir / ns.SCRIPT_FILE)


def _page(item: dict) -> str:
    path = (item.get("read") or {}).get("text_path") or ""
    if not path or not Path(path).is_file():
        raise RuntimeError("fact audit: the cached original (read.text_path) is missing; re-run the news daily fetch")
    return claims.squash(Path(path).read_text(encoding="utf-8"))


def _write(run_dir: Path, report: dict) -> None:
    (run_dir / "review").mkdir(parents=True, exist_ok=True)
    (run_dir / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (run_dir / HISTORY).open("a", encoding="utf-8") as out:
        out.write(json.dumps(report, ensure_ascii=False) + "\n")


def run(run_dir: Path, channel_code: str, series: NewsSeries | None) -> int:
    from content_farm.review.config import load_review

    if series is None or not series.claims_audit:
        print("OK: this channel has no claim audit")
        return 0
    script_path = run_dir / ns.SCRIPT_FILE
    current = _sha(script_path)
    previous = run_dir / REPORT
    if previous.is_file() and json.loads(previous.read_text(encoding="utf-8")).get("after_sha") == current:
        print("OK: already audited (and fixed, if needed); nothing to do")
        return 0
    news, item = ns.load_script(run_dir), ns.load_item(run_dir)
    problems = claims.audit(news, item, _page(item), series)
    errors = [p.line() for p in problems]
    base = {"version": 1, "at": score_ledger.now_iso(), "channel": channel_code, "errors": errors,
            "problems": [asdict(p) for p in problems], "before_sha": current}
    if not problems:
        _write(run_dir, {**base, "fixes": [], "after_sha": current, "outcome": "clean"})
        print(f"OK: {sum(len(b.claims) for b in news.beats)} claims, every factual sentence has a verifiable source")
        return 0
    policy = load_review(channel_code).policy
    for line in errors:
        print(f"✗ {line}")
    if policy.fact_on_fail != "auto_fix_then_pass":
        _write(run_dir, {**base, "fixes": [], "after_sha": None, "outcome": "stopped"})
        print(f"FAIL: {len(problems)} unsourced / badly attributed sentence(s); policy fact_on_fail=stop")
        return 1
    fixed, fixes = claims.auto_fix(news, problems, item, series)
    (run_dir / DRAFT).write_text(script_path.read_text(encoding="utf-8"), encoding="utf-8")
    script_path.write_text(json.dumps(fixed.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    after = _sha(script_path)
    summary = "；".join(errors)
    score_ledger.log_auto_fix(run_dir, GATE, STAGE, event="fix_issued", round=1, inputs=current, errors=summary,
                              fixes=str(run_dir / REPORT), restart="fact_audit")
    score_ledger.log_auto_fix(run_dir, GATE, STAGE, event="passed_without_recheck", round=1, inputs=current,
                              errors=errors, content_changed=after != current, fixes=str(run_dir / REPORT))
    _write(run_dir, {**base, "fixes": [asdict(f) for f in fixes], "after_sha": after, "outcome": "auto_fixed_then_passed"})
    print(f"AUTO-FIXED: {len(problems)} error(s) → {sum(f.action == 'deleted' for f in fixes)} deleted, "
          f"{sum(f.action == 'rewritten' for f in fixes)} rewritten as 「據…報導」; passing without re-check")
    return 0
