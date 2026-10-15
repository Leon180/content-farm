"""One-command production runner: topic → final.mp4 → upload metadata, stopping at human gates.

Usage:
    python scripts/produce.py run --channel chipcat --run-dir output/cowos --mock-voice
    python scripts/produce.py run --run-dir output/cowos            # resume (channel from production.json)
    python scripts/produce.py approve --run-dir output/cowos --gate deck
    python scripts/produce.py reject  --run-dir output/cowos --gate media --note "s22 有 logo"
    python scripts/produce.py approve --run-dir output/cowos --gate final --override "AI 圖佔位，先上 unlisted"
    python scripts/produce.py status  --run-dir output/cowos
    python scripts/produce.py inbox   --root output                 # every run waiting on a person
    python scripts/produce.py plan    --week 2026-W43               # publish calendar + topic picks
    python scripts/produce.py channels                               # validate channels/*.yaml

Exit codes for ``run``: 0 all steps done, 1 a step failed, 3 waiting (gate, agent
step, or paid step without --allow-paid). Each stop prints the next command.
Paid steps (TTS) never run without --allow-paid; --mock-voice uses macOS `say`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from pydantic import ValidationError

from content_farm.production.channels import Gate, load_all, load_channel
from content_farm.production.runner import SCHEDULE_FILE, Outcome, Runner, decide
from content_farm.production.schedule import load_backlog, plan_week
from content_farm.production.state import STATE_FILE, load_state, read_channel_code
from content_farm.production.steps import Context, RunOptions, steps_for


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run / resume until the next stop")
    run.add_argument("--run-dir", type=Path, required=True)
    run.add_argument("--channel", help="channel code; required for a new run-dir")
    run.add_argument("--mock-voice", action="store_true", help="macOS say instead of paid TTS")
    run.add_argument("--allow-paid", action="store_true", help="allow paid API steps (TTS)")
    run.add_argument("--no-stock", action="store_true", help="never call Pexels/Pixabay")
    run.add_argument("--env-file", type=Path, help="default <repo>/.env")
    run.add_argument("--mascot-workers", type=int, default=2)
    run.add_argument("--max-load", type=float, default=None,
                     help="wait before heavy steps while 1-min load average is above this")
    run.add_argument("--until", help="stop after this step")
    run.add_argument("--force", action="append", default=[], help="re-run this step (repeatable)")
    run.add_argument("--publish-at", help="ISO datetime with offset, e.g. 2026-10-22T19:00+08:00")

    for name in ("approve", "reject"):
        p = sub.add_parser(name)
        p.add_argument("--run-dir", type=Path, required=True)
        p.add_argument("--gate", choices=[g.value for g in Gate], required=True)
        p.add_argument("--note", default="")
        p.add_argument("--by", default="leon", help="who decided (recorded in production.json)")
        if name == "approve":
            p.add_argument("--override", default="", help="approve the final gate despite QC errors")

    status = sub.add_parser("status")
    status.add_argument("--run-dir", type=Path, required=True)
    inbox = sub.add_parser("inbox")
    inbox.add_argument("--root", type=Path, default=Path("output"))
    plan = sub.add_parser("plan")
    plan.add_argument("--week", required=True, help="ISO week, e.g. 2026-W43")
    plan.add_argument("--today", type=date.fromisoformat, default=date.today())
    sub.add_parser("channels")
    return parser.parse_args(argv)


def _channel_for(run_dir: Path, code: str | None):
    if (run_dir / STATE_FILE).is_file():
        existing = read_channel_code(run_dir)
        if code and code != existing:
            raise ValueError(f"{run_dir} belongs to channel {existing!r}, not {code!r}")
        code = existing
    if not code:
        raise ValueError("new run-dir: pass --channel")
    return load_channel(code)


def _write_schedule(run_dir: Path, publish_at: str) -> None:
    when = datetime.fromisoformat(publish_at)
    if when.tzinfo is None:
        raise ValueError("--publish-at needs a UTC offset, e.g. +08:00")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / SCHEDULE_FILE).write_text(json.dumps({"publish_at": when.isoformat()}), encoding="utf-8")


def cmd_run(args: argparse.Namespace) -> int:
    channel = _channel_for(args.run_dir, args.channel)
    if args.publish_at:
        _write_schedule(args.run_dir, args.publish_at)
    options = RunOptions(mock_voice=args.mock_voice, allow_paid=args.allow_paid, no_stock=args.no_stock,
                         mascot_workers=args.mascot_workers,
                         **({"env_file": args.env_file} if args.env_file else {}))
    runner = Runner(Context(channel, args.run_dir.resolve(), options), max_load=args.max_load)
    result = runner.run(until=args.until, force=frozenset(args.force))
    print(f"[{result.outcome.value}] {result.step}: {result.message}")
    if result.review_page:
        print(f"審核頁：{result.review_page}")
    if result.outcome is Outcome.GATE:
        gate = result.step.removeprefix("gate_")
        print(f"核可：python scripts/produce.py approve --run-dir {args.run_dir} --gate {gate}")
    if result.outcome is Outcome.COMPLETE and not args.until:
        print(f"下一步：/upload（讀 {args.run_dir}/upload/youtube_meta.json）")
    return result.exit_code


def cmd_decide(args: argparse.Namespace, verdict: str) -> int:
    channel = load_channel(read_channel_code(args.run_dir))
    decision = decide(args.run_dir.resolve(), channel, Gate(args.gate), verdict, note=args.note,
                      override=getattr(args, "override", ""), by=args.by)
    print(f"{decision.gate}: {decision.verdict} @ {decision.fingerprint}")
    print(f"繼續：python scripts/produce.py run --run-dir {args.run_dir}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    channel = load_channel(read_channel_code(args.run_dir))
    state = load_state(args.run_dir, channel.code)
    print(f"{channel.name} ({channel.code}) · {args.run_dir}")
    for step in steps_for(channel):
        record = state.steps.get(step.name)
        status = record.status if record else "-"
        seconds = f"{record.seconds:7.1f}s" if record and record.seconds else " " * 8
        print(f"  {step.name:<13} {status:<8} {seconds}  {step.title}  {record.note if record else ''}")
    return 0


def cmd_inbox(args: argparse.Namespace) -> int:
    items = []
    for path in sorted(args.root.glob("*/review/*.decision.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") == "pending":
            items.append(data)
    for item in items:
        print(f"[{item['channel']}] {item['gate']:<8} {item['run_dir']}\n    {item['review_page']}")
    print(f"{len(items)} pending decision(s)")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    year_text, week_text = args.week.upper().split("-W")
    for channel in load_all():
        backlog = load_backlog(channel.code)
        for item in plan_week(channel, backlog, int(year_text), int(week_text), args.today):
            topic = f"{item.topic.id} 「{item.topic.title}」" if item.topic else "（空）"
            warn = f"  ⚠ {item.warning}" if item.warning else ""
            print(f"{item.slot.publish_at:%a %m-%d %H:%M} {channel.code:<8} {item.slot.kind:<5} "
                  f"開工≤{item.slot.start_by:%m-%d}  {topic}{warn}")
    return 0


def cmd_channels(_: argparse.Namespace) -> int:
    for channel in load_all():
        gates = ",".join(g.value for g in channel.gates)
        print(f"{channel.code:<8} {channel.name:<8} pipeline={channel.pipeline.value:<11} "
              f"brand={channel.brand:<8} long/wk={channel.cadence.long_per_week} "
              f"shorts/wk={channel.cadence.shorts_per_week} gates={gates}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    handlers = {"run": cmd_run, "status": cmd_status, "inbox": cmd_inbox, "plan": cmd_plan,
                "channels": cmd_channels,
                "approve": lambda a: cmd_decide(a, "approved"),
                "reject": lambda a: cmd_decide(a, "rejected")}
    try:
        return handlers[args.command](args)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
