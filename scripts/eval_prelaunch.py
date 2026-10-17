"""Pre-launch eval: objective metrics + review panel (synthetic viewers, editor, director) + scorecard.

Usage:
    python scripts/eval_prelaunch.py metrics  --run-dir output/cowos-v3 [--out FILE]
    python scripts/eval_prelaunch.py prepare  --run-dir output/cowos-v3 --channel chipcat --round 1 [--stage rough_cut]
    python scripts/eval_prelaunch.py score    --run-dir output/cowos-v3 --channel chipcat --round 1 [--change "…"]
    python scripts/eval_prelaunch.py baseline --run-dir output/cowos-v3 --results DIR [--objective-from RUN_DIR]
    python scripts/eval_prelaunch.py loop     --run-dir output/cowos-v3 --channel chipcat [--max-rounds 3]

``loop`` is the same state machine as ``produce.py eval-loop``. Reviewers are Claude sub-agents:
the session running this dispatches each brief in ``eval/round-N/briefs/`` with the Agent tool,
then calls ``loop`` again. Exit codes: 0 pass, 3 waiting / fix needed, 4 stopped at max rounds.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from content_farm.evaluation import loop
from content_farm.evaluation.flow import advance, thumbs_for, video_fingerprint
from content_farm.evaluation.panel import load_panels
from content_farm.evaluation.prepare import EVAL_DIR, prepare_round
from content_farm.production.channels import load_channel
from content_farm.retention.report import build_report, write_report


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    metrics = sub.add_parser("metrics")
    metrics.add_argument("--run-dir", type=Path, required=True)
    metrics.add_argument("--out", type=Path)
    for name in ("prepare", "score", "loop"):
        p = sub.add_parser(name)
        p.add_argument("--run-dir", type=Path, required=True)
        p.add_argument("--channel", required=True)
        p.add_argument("--competitors", type=Path, help="dir with competitors.json (homepage feeds)")
        if name != "loop":
            p.add_argument("--round", type=int, required=True)
        p.add_argument("--change", action="append", default=[], help="what changed since the last round")
        p.add_argument("--minutes", type=float, help="wall-clock minutes spent on this round")
        if name == "prepare":
            p.add_argument("--stage", default="rough_cut")
            p.add_argument("--final", action="store_true", help="last round: add the holdout viewer")
        if name == "loop":
            p.add_argument("--max-rounds", type=int)
    base = sub.add_parser("baseline", help="import an earlier eval (e.g. the 2026-10-17 trial) as round 'baseline'")
    base.add_argument("--run-dir", type=Path, required=True)
    base.add_argument("--results", type=Path, required=True, help="dir with result-<persona>.json")
    base.add_argument("--duration", type=float, required=True, help="length of the video that was reviewed (s)")
    base.add_argument("--objective-from", type=Path, help="run-dir whose video gets the objective metrics")
    base.add_argument("--label", default="baseline")
    return parser.parse_args(argv)


def cmd_baseline(args: argparse.Namespace) -> int:
    out = args.run_dir / EVAL_DIR / "baseline"
    (out / "results").mkdir(parents=True, exist_ok=True)
    reviewers = []
    for path in sorted(args.results.glob("result-*.json")):
        rid = f"viewer-{path.stem.removeprefix('result-')}"
        shutil.copy2(path, out / "results" / f"{rid}.json")
        reviewers.append({"rid": rid, "kind": "viewer", "role": rid, "holdout": False, "brief": "",
                          "result": str(out / "results" / f"{rid}.json")})
    if args.objective_from:
        write_report(args.objective_from, build_report(args.objective_from.resolve()), out / "objective.json")
    manifest = {"round": "baseline", "stage": "trial", "video": "(earlier version)", "duration": args.duration,
                "variants": ["A"], "reviewers": reviewers, "final_round": False}
    (out / "round.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    score = loop.score_round(args.run_dir, "baseline", load_panels().thresholds, label=args.label)
    print(json.dumps({k: score[k] for k in ("audience", "columns", "verdict")}, ensure_ascii=False)[:1500])
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    try:
        if args.command == "metrics":
            path = write_report(args.run_dir, build_report(args.run_dir.resolve()), args.out)
            print(path)
            return 0
        if args.command == "baseline":
            return cmd_baseline(args)
        channel = load_channel(args.channel)
        run_dir = args.run_dir.resolve()
        panels = load_panels()
        if args.command == "prepare":
            manifest = prepare_round(run_dir, round_no=args.round, panels=panels, stage=args.stage,
                                     channel_code=channel.code, channel_name=channel.name, final_round=args.final,
                                     competitors_dir=args.competitors)
            manifest["video_fingerprint"] = video_fingerprint(run_dir)
            (run_dir / EVAL_DIR / f"round-{args.round}" / "round.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
            for entry in manifest["reviewers"]:
                print(f"{entry['rid']}: {entry['brief']}")
            return 0
        if args.command == "score":
            score = loop.score_round(run_dir, args.round, panels.thresholds,
                                     thumbs=thumbs_for(run_dir, args.competitors))
            loop.append_log(run_dir, loop.log_entry(score, minutes=args.minutes, changes=args.change))
            print(loop.redraw(run_dir, channel.name, ["baseline", f"round-{args.round}"]))
            print(json.dumps(score["verdict"], ensure_ascii=False))
            return 0
        step = advance(run_dir, channel, max_rounds=args.max_rounds, panels=panels, competitors_dir=args.competitors,
                       changes=args.change, minutes=args.minutes)
        print(f"[{step.status}] {step.message}")
        return step.exit_code
    except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
