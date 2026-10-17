"""Score a round, log it to ``eval/loop.jsonl`` and redraw ``eval/scorecard.html``.

The eval → fix loop (Leon 2026-10-17): produce → prepare round → reviewers (Claude sub-agents,
dispatched by the session that runs ``produce.py eval-loop``) → score → fix from the common
list → re-render → next round; stop when every threshold passes or after ``max_rounds``.
Pronunciation (orchestrator 6b6b317b40f064bb): only words viewers name in ``pronunciation``
send the run back to the voice step; speech_check warnings alone are just logged.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from content_farm.evaluation import aggregate, scorecard
from content_farm.evaluation.panel import Thresholds
from content_farm.evaluation.prepare import EVAL_DIR, round_dir

LOOP_LOG = EVAL_DIR / "loop.jsonl"
SCORECARD = EVAL_DIR / "scorecard.html"


def score_round(run_dir: Path, round_no: int | str, thresholds: Thresholds, *, label: str = "",
                thumbs: dict | None = None) -> dict:
    rdir = run_dir / EVAL_DIR / (f"round-{round_no}" if isinstance(round_no, int) else round_no)
    manifest = json.loads((rdir / "round.json").read_text(encoding="utf-8"))
    viewers, pros = aggregate.load_results(rdir)
    regular = [v for v in viewers if not v["_holdout"]]
    held = [v for v in viewers if v["_holdout"]]
    duration = float(manifest["duration"])
    variants = manifest.get("variants") or ["A"]
    objective = json.loads((rdir / "objective.json").read_text(encoding="utf-8")) \
        if (rdir / "objective.json").is_file() else None
    checks = aggregate.objective_checks(objective, thumbs) if objective else []
    columns = aggregate.column_scores(checks)
    keys_path = run_dir / EVAL_DIR / ".keys" / f"{rdir.name}.json"
    keys = json.loads(keys_path.read_text(encoding="utf-8")) if keys_path.is_file() else {}
    aud = aggregate.audience(regular, duration, variants)
    home = aggregate.homepage_stats(regular, keys)
    result = {
        "round": round_no, "label": label or rdir.name, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "video": manifest.get("video"), "duration": duration,
        "audience": aud, "holdout": aggregate.audience(held, duration, variants) if held else None,
        "pros": [{"role": p.get("role"), "score": p.get("score"), "rubric": p.get("rubric"), "verdict": p.get("verdict")}
                 for p in pros],
        "pro_mean": round(statistics.mean(p["score"] for p in pros if isinstance(p.get("score"), (int, float))), 2)
        if any(isinstance(p.get("score"), (int, float)) for p in pros) else None,
        "homepage": home, "checks": [asdict(c) for c in checks], "columns": columns,
        "fixes": aggregate.fix_list(viewers, pros), "pronunciation": aud.get("pronunciation", []),
        "missing_results": [e["rid"] for e in manifest["reviewers"] if not Path(e["result"]).is_file()],
    }
    result["verdict"] = aggregate.verdict(aud, home, columns, thresholds)
    (rdir / "score.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def append_log(run_dir: Path, entry: dict) -> None:
    path = run_dir / LOOP_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_log(run_dir: Path) -> list[dict]:
    path = run_dir / LOOP_LOG
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def log_entry(score: dict, *, minutes: float | None, changes: list[str]) -> dict:
    aud = score.get("audience") or {}
    return {"round": score["round"], "label": score["label"], "at": score["at"], "minutes": minutes,
            "pass": score["verdict"]["pass"], "reasons": score["verdict"]["reasons"],
            "leave_median_pct": aud.get("leave_median_pct"), "click_best": aud.get("click_best"),
            "engagement_mean": aud.get("engagement_mean"),
            "columns": {k: v.get("score") for k, v in score["columns"].items()},
            "lights": {k: v.get("light") for k, v in score["columns"].items()},
            "homepage": score.get("homepage"), "holdout": (score.get("holdout") or {}).get("leave_median_pct"),
            "changes": changes}


def redraw(run_dir: Path, title: str, labels: list[str]) -> Path:
    """Scorecard of the newest round, with every scored round (in ``labels`` order) as comparison."""
    scores = []
    for name in labels:
        path = run_dir / EVAL_DIR / name / "score.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            minutes = next((e.get("minutes") for e in read_log(run_dir) if e["label"] == data["label"]), None)
            scores.append({**data, "minutes": minutes})
    if not scores:
        raise FileNotFoundError("no scored round yet")
    return scorecard.render(scores, scores[-1], title, run_dir / SCORECARD)


def next_round(run_dir: Path) -> int:
    done = [int(p.name.split("-")[1]) for p in (run_dir / EVAL_DIR).glob("round-*") if p.name.split("-")[1].isdigit()]
    return max(done, default=0) + 1


def round_has_all_results(run_dir: Path, round_no: int) -> bool:
    manifest = json.loads((round_dir(run_dir, round_no) / "round.json").read_text(encoding="utf-8"))
    return all(Path(e["result"]).is_file() for e in manifest["reviewers"])
