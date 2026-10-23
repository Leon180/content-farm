#!/usr/bin/env python3
"""Run the same script_structure viewer / writer prompts of already-reviewed drafts through sonnet and opus,
then summarise the gap (``content_farm.review.calibrate``). Paid (claude -p, notional cost recorded).

    PYTHONPATH=src python scripts/calibrate_audience.py run --out docs/story-calibrate/data \
        --budget 15 name=<round dir> [name=<round dir> ...]
    PYTHONPATH=src python scripts/calibrate_audience.py summarize --out docs/story-calibrate/data
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from content_farm.review import calibrate as cal
from content_farm.review.client import Call, run_call
from content_farm.review.schemas import schema_for

MODELS = ("sonnet", "opus")
EFFORT = "low"
WRITERS = ("writer_story-1", "writer_density-1")


def seat_ids(round_dir: Path) -> list[str]:
    names = sorted(p.stem for p in (round_dir / "prompts").glob("*.md"))
    return [n for n in names if n.startswith("viewer-") or n in WRITERS]


def kind_of(rid: str) -> str:
    return "viewer" if rid.startswith("viewer-") else "pro"


class Spend:
    def __init__(self, limit: float) -> None:
        self.limit, self.total, self._lock = limit, 0.0, threading.Lock()

    def add(self, usd: float) -> None:
        with self._lock:
            self.total += usd

    def over(self) -> bool:
        with self._lock:
            return self.total >= self.limit


def one_call(draft: str, round_dir: Path, rid: str, model: str, out: Path, spend: Spend) -> dict:
    target = out / draft / model / f"{rid}.json"
    if target.is_file():
        return json.loads(target.read_text(encoding="utf-8"))
    if spend.over():
        return {"rid": rid, "ok": False, "errors": ["budget stop"], "cost_usd": 0.0}
    prompt = (round_dir / "prompts" / f"{rid}.md").read_text(encoding="utf-8")
    call = Call(f"{draft}:{rid}:{model}", prompt, schema_for("script_structure", kind_of(rid)), model, EFFORT,
                tools=("Read",), cwd=round_dir, timeout_s=900, retries=1)
    result = run_call(call)
    spend.add(result.cost_usd)
    record = result.to_json() | {"output": result.output, "draft": draft, "round_dir": str(round_dir)}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{draft} {rid} {model} ok={result.ok} ${result.cost_usd:.3f} total=${spend.total:.2f}", flush=True)
    return record


def run(args: argparse.Namespace) -> int:
    out, spend = Path(args.out), Spend(args.budget)
    jobs = []
    for spec in args.drafts:
        name, _, path = spec.partition("=")
        round_dir = Path(path)
        # same persona, same order: seats are taken in the original roster order, sonnet and opus alternately
        for rid in seat_ids(round_dir):
            for model in MODELS:
                jobs.append((name, round_dir, rid, model))
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        list(pool.map(lambda j: one_call(j[0], j[1], j[2], j[3], out, spend), jobs))
    print(f"spent ${spend.total:.2f} of ${args.budget:.2f}")
    return 0


def load(out: Path) -> dict[str, dict[str, dict[str, dict]]]:
    data: dict[str, dict[str, dict[str, dict]]] = {}
    for path in sorted(out.glob("*/*/*.json")):
        draft, model = path.parent.parent.name, path.parent.name
        data.setdefault(draft, {}).setdefault(model, {})[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return data


def summarize(args: argparse.Namespace) -> int:
    data = load(Path(args.out))
    pairs, scores, rows, cost = [], [], [], 0.0
    for draft, by_model in data.items():
        record = next(iter(by_model.get("sonnet", {}).values()), None)
        sentences = cal.load_listing(Path(record["round_dir"])) if record else []
        for rid in sorted(by_model.get("sonnet", {})):
            s, o = by_model["sonnet"][rid], by_model.get("opus", {}).get(rid)
            cost += s.get("cost_usd", 0) + (o or {}).get("cost_usd", 0)
            if not (s.get("ok") and o and o.get("ok")):
                continue
            if rid.startswith("viewer-"):
                ls, lo = cal.leave_share(s["output"], sentences), cal.leave_share(o["output"], sentences)
                pairs.append(cal.PairedSeat(draft, rid, ls, lo))
                rows.append({"draft": draft, "seat": rid, "sonnet": ls, "opus": lo})
            else:
                scores.append((f"{draft}/{rid}", float(s["output"]["score"]), float(o["output"]["score"])))
                rows.append({"draft": draft, "seat": rid, "sonnet": s["output"]["score"], "opus": o["output"]["score"]})
    gaps = cal.draft_gaps(pairs)
    conv = cal.convert_threshold(cal.OPUS_LEAVE_MEDIAN, [g["gap"] for g in gaps.values()])
    seat_gap = cal.bootstrap_ci([p.opus - p.sonnet for p in pairs])
    result = {"per_draft": gaps, "conversion": conv, "seat_gap_ci90": list(seat_gap),
              "writer": cal.score_bias(scores), "rows": rows, "cost_usd_notional": round(cost, 3)}
    (Path(args.out) / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False, indent=1))
    return 0


OLD = {"leave": 0.40, "writer": 6.5}
NEW = {"leave": 0.35, "writer": 6.0}


def _passes(leave: float, writers: list[float], bar: dict[str, float]) -> bool:
    return leave >= bar["leave"] and all(w >= bar["writer"] for w in writers)


def replay(args: argparse.Namespace) -> int:
    """Offline: re-judge already-recorded script_structure rounds under the old and the calibrated bars (no calls)."""
    rows = []
    for spec in args.rounds:
        name, _, path = spec.partition("=")
        card = json.loads((Path(path) / "scorecard.json").read_text(encoding="utf-8"))
        scores = card["verdict"]["scores"]
        leave, writers = float(scores["leave_median_pct"]), [float(v) for v in scores["writers"].values()]
        rows.append({"round": name, "leave_median": leave, "writers": scores["writers"],
                     "recorded_pass": card["verdict"]["pass"], "old_bar_pass": _passes(leave, writers, OLD),
                     "new_bar_pass": _passes(leave, writers, NEW),
                     "leave_gap_to_new_bar": round(leave - NEW["leave"], 3)})
    print(json.dumps(rows, ensure_ascii=False, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--out", required=True)
    runner.add_argument("--budget", type=float, default=15.0)
    runner.add_argument("--parallel", type=int, default=6)
    runner.add_argument("drafts", nargs="+")
    runner.set_defaults(fn=run)
    summary = sub.add_parser("summarize")
    summary.add_argument("--out", required=True)
    summary.set_defaults(fn=summarize)
    again = sub.add_parser("replay")
    again.add_argument("--out")
    again.add_argument("rounds", nargs="+")
    again.set_defaults(fn=replay)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
