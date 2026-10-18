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
    python scripts/produce.py short-from-long --from output/cowos --slide s09 --channel offwork \
        --run-dir output/offwork-7722 --title "…" --number 7,722 --unit mm²   # 9:16 Short (R5)
    python scripts/produce.py manual-kit --run-dir output/cowos [--out DIR]  # Studio upload kit + preview.html
    python scripts/produce.py eval-loop --run-dir output/cowos --max-rounds 3  # review panel → fix loop (one step)

Exit codes for ``run``: 0 all steps done, 1 a step failed, 3 waiting (gate, agent
step, or paid step without --allow-paid). Each stop prints the next command.
Paid steps (TTS) never run without --allow-paid; --mock-voice uses macOS `say`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import yaml
from pydantic import ValidationError

from content_farm.production.channels import Gate, load_all, load_channel
from content_farm.production.manual_kit import KitOptions, write_kit
from content_farm.production.runner import SCHEDULE_FILE, Outcome, Runner, decide
from content_farm.production.schedule import load_backlog, plan_week
from content_farm.production.shorts_cut import short_spec_from_long, write_spec
from content_farm.production.state import STATE_FILE, load_state, read_channel_code
from content_farm.production.steps import Context, RunOptions, steps_for


MAX_REWORK_LOOPS = 12   # every stage caps its own rounds; this only stops a runaway loop


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
    run.add_argument("--no-panels", action="store_true",
                     help="old behaviour: gates wait for produce.py approve (needs --override) instead of review panels")
    run.add_argument("--auto-agents", action="store_true",
                     help="run producer agents (claude -p) for topic/article/deck/titles and their rework")
    run.add_argument("--competitors", type=Path, help="dir with competitors.json for the homepage feeds")
    run.add_argument("--review-tier", default="", help='lift every reviewer, e.g. "opus:high" (comparison runs)')

    for name in ("approve", "reject"):
        p = sub.add_parser(name)
        p.add_argument("--run-dir", type=Path, required=True)
        p.add_argument("--gate", choices=[g.value for g in Gate], required=True)
        p.add_argument("--note", default="")
        p.add_argument("--by", default="leon", help="who decided (recorded in production.json)")
        if name == "approve":
            p.add_argument("--override", default="",
                           help="required: why a person approves instead of the review panel (logged)")

    short = sub.add_parser("short-from-long", help="cut a 9:16 「一個數字」 Short from a long run")
    short.add_argument("--from", dest="long_run_dir", type=Path, required=True, help="the long run-dir")
    short.add_argument("--slide", required=True, help="slide id, e.g. s09")
    short.add_argument("--channel", required=True, help="channel that publishes the Short")
    short.add_argument("--run-dir", type=Path, required=True, help="new run-dir for the Short")
    short.add_argument("--title", required=True, help="YouTube title (#Shorts is appended)")
    short.add_argument("--number", help="hero number; default: the slide's big_number value")
    short.add_argument("--unit", help="default: the slide's unit")
    short.add_argument("--caption", help="default: the slide's caption")
    short.add_argument("--aside", default="", help="optional derived comparison shown under the number")
    short.add_argument("--hook", default="這是多大？")
    short.add_argument("--label", default="一個數字")
    short.add_argument("--long-title", help="default: the long deck's title")
    short.add_argument("--beats", type=Path, help="JSON {answer, beats:[...]} → scripted Short with its own narration")
    short.add_argument("--publish-at", help="ISO datetime with offset")
    short.add_argument("--max-load", type=float, default=None)

    kit = sub.add_parser("manual-kit", help="upload/manual/: YouTube Studio checklist, texts, preview.html")
    kit.add_argument("--run-dir", type=Path, required=True)
    kit.add_argument("--out", type=Path, help="write the kit here instead of <run-dir>/upload/manual")
    kit.add_argument("--voice", choices=("auto", "machine", "fish"), default="auto",
                     help="voice for the banner; auto reads logs/voice.log")
    kit.add_argument("--playlist", default="", help="default: the channel's playlist name")
    kit.add_argument("--thumbnail-at", type=float, help="use the video frame at this second as thumbnail")

    loop = sub.add_parser("eval-loop", help="pre-launch eval → fix loop (review panel + objective metrics)")
    loop.add_argument("--run-dir", type=Path, required=True)
    loop.add_argument("--max-rounds", type=int, default=None, help="default: review_panels.yaml (3)")
    loop.add_argument("--competitors", type=Path, help="dir with competitors.json for the homepage feeds")
    loop.add_argument("--change", action="append", default=[], help="what was fixed since the last round")
    loop.add_argument("--minutes", type=float, help="minutes spent on the round being scored")

    status = sub.add_parser("status")
    status.add_argument("--run-dir", type=Path, required=True)
    inbox = sub.add_parser("inbox")
    inbox.add_argument("--root", type=Path, default=Path("output"))
    plan = sub.add_parser("plan")
    plan.add_argument("--week", required=True, help="ISO week, e.g. 2026-W43")
    plan.add_argument("--today", type=date.fromisoformat, default=date.today())
    sub.add_parser("channels")
    review = sub.add_parser("review", help="side round of one stage's panel (e.g. all-opus comparison); never opens a gate")
    review.add_argument("--run-dir", type=Path, required=True)
    review.add_argument("--stage", required=True, help="topic|article|script|title_thumb|media|final")
    review.add_argument("--tier", default="", help='lift every reviewer, e.g. "opus:high"')
    review.add_argument("--round", type=int, default=1, help="round number to mirror (holdout sits in the last)")
    review.add_argument("--suffix", default="-compare")
    review.add_argument("--competitors", type=Path)
    sub.add_parser("queue", help="machine-wide heavy-work queue (renders, local TTS, image/video models)")
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
                         mascot_workers=args.mascot_workers, panels=not args.no_panels,
                         auto_agents=args.auto_agents, competitors=args.competitors,
                         review_tier=args.review_tier,
                         **({"env_file": args.env_file} if args.env_file else {}))
    runner = Runner(Context(channel, args.run_dir.resolve(), options), max_load=args.max_load)
    result = runner.run(until=args.until, force=frozenset(args.force))
    loops = 0
    while args.auto_agents and result.outcome is Outcome.REWORK and loops < MAX_REWORK_LOOPS:
        loops += 1   # rework routed back by a panel: the producer agents redo it, then the run goes on
        print(f"[rework {loops}] {result.step}: {result.message}")
        result = runner.run(until=args.until)
    print(f"[{result.outcome.value}] {result.step}: {result.message}")
    if result.review_page:
        print(f"審核頁：{result.review_page}")
    if result.outcome is Outcome.GATE:
        gate = result.step.removeprefix("gate_")
        print(f"手動核可（後門）：python scripts/produce.py approve --run-dir {args.run_dir} --gate {gate} "
              f'--override "理由"')
    if result.outcome is Outcome.REWORK:
        print(f"退回：修改清單在 {args.run_dir}/review/{result.step.removeprefix('gate_')}.fixes.json；"
              f"改完重跑 run（--auto-agents 會自動呼叫產出 agent）")
    if result.outcome is Outcome.COMPLETE and not args.until:
        print(f"下一步：/upload（讀 {args.run_dir}/upload/youtube_meta.json）")
    return result.exit_code


def cmd_short_from_long(args: argparse.Namespace) -> int:
    long_dir = args.long_run_dir.resolve()
    long_channel = load_channel(read_channel_code(long_dir))
    spec = short_spec_from_long(long_dir, long_channel, vars(args))
    if args.beats:
        scripted = json.loads(args.beats.read_text(encoding="utf-8"))
        spec = spec.model_validate({**spec.model_dump(), "answer": scripted.get("answer", ""),
                                    "beats": scripted["beats"]})
    channel = _channel_for(args.run_dir, args.channel)
    write_spec(args.run_dir, spec)
    if args.publish_at:
        _write_schedule(args.run_dir, args.publish_at)
    runner = Runner(Context(channel, args.run_dir.resolve(), RunOptions()), max_load=args.max_load)
    result = runner.run(force=frozenset({"cut"}))  # the long run may have changed (e.g. real voice)
    print(f"[{result.outcome.value}] {result.step}: {result.message}")
    if result.review_page:
        print(f"審核頁：{result.review_page}")
    if result.outcome is Outcome.GATE:
        gate = result.step.removeprefix("gate_")
        print(f"核可：python scripts/produce.py approve --run-dir {args.run_dir} --gate {gate}")
    return result.exit_code


def cmd_manual_kit(args: argparse.Namespace) -> int:
    options = KitOptions(out_dir=args.out, playlist=args.playlist, thumbnail_at=args.thumbnail_at,
                         machine_voice={"auto": None, "machine": True, "fish": False}[args.voice])
    kit = write_kit(args.run_dir.resolve(), load_channel(read_channel_code(args.run_dir)), options)
    flags = [*(["成片閘門未核可：預覽版"] if kit.preview else []), *(["暫用機器聲"] if kit.machine_voice else [])]
    print(f"{kit.directory}/README.md, preview.html{'  ⚠ ' + '、'.join(flags) if flags else ''}")
    return 0


def cmd_eval_loop(args: argparse.Namespace) -> int:
    """One step of eval → fix: prepare a round / wait for reviewers / score / say what to fix.
    Exit 0 pass, 3 waiting or fix needed, 4 stopped at max rounds (report the gap)."""
    from content_farm.evaluation.flow import advance

    channel = load_channel(read_channel_code(args.run_dir))
    step = advance(args.run_dir.resolve(), channel, max_rounds=args.max_rounds, competitors_dir=args.competitors,
                   changes=args.change, minutes=args.minutes)
    print(f"[{step.status}] {step.message}")
    return step.exit_code


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
    for step in steps_for(channel, args.run_dir):
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


def cmd_review(args: argparse.Namespace) -> int:
    from content_farm.production import panel_flow
    from content_farm.review.rounds import run_round
    from content_farm.review.scorecard_html import render

    channel = load_channel(read_channel_code(args.run_dir))
    ctx = Context(channel, args.run_dir.resolve(), RunOptions(review_tier=args.tier, competitors=args.competitors))
    config = panel_flow.review_config(ctx)
    stage = config.stages[args.stage]
    competitors = panel_flow.competitors_for(ctx)
    card = run_round(ctx.run_dir, stage_name=args.stage, config=config, channel=channel.code, channel_name=channel.name,
                     round_no=args.round, with_holdout=args.round == stage.max_rounds, competitors=competitors,
                     vertical=panel_flow._short(ctx), suffix=args.suffix,  # noqa: SLF001
                     judge_context=panel_flow._judge_context(ctx, args.stage, competitors)(ctx.run_dir))  # noqa: SLF001
    render(ctx.run_dir, channel.name)
    verdict = card["verdict"]
    print(f"[{'pass' if verdict['pass'] else 'fail'}] {card['label']}: {'；'.join(verdict['reasons']) or 'all thresholds met'}")
    print(json.dumps(verdict["scores"], ensure_ascii=False, default=str)[:1500])
    return 0


def cmd_queue(_: argparse.Namespace) -> int:
    from content_farm.lanes.queue import QUEUE_DIR, status

    rows = status()
    for n, row in enumerate(rows, 1):
        mark = "▶" if row["holding"] else f"{n}."
        print(f"{mark:>3} {row['kind']:<5} {row['progress']:>4.0%}  {row['job']:<40} pid {row['pid']}  since {row['enqueued_at']}")
    print(f"{len(rows)} job(s) in {QUEUE_DIR}" if rows else f"queue empty ({QUEUE_DIR})")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    handlers = {"run": cmd_run, "status": cmd_status, "inbox": cmd_inbox, "plan": cmd_plan,
                "channels": cmd_channels, "short-from-long": cmd_short_from_long,
                "manual-kit": cmd_manual_kit, "eval-loop": cmd_eval_loop, "queue": cmd_queue, "review": cmd_review,
                "approve": lambda a: cmd_decide(a, "approved"),
                "reject": lambda a: cmd_decide(a, "rejected")}
    try:
        return handlers[args.command](args)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError, yaml.YAMLError,
            subprocess.SubprocessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
