"""Step commands for HN 快報 Shorts (called by the production runner, not by hand).

    python scripts/news.py lint    --run-dir output/hn-2026-10-16-hn-50117451
    python scripts/news.py audit   --run-dir …     # ent: sourced-claim audit, one auto-fix (review/fact_audit.json)
    python scripts/news.py prepare --run-dir …     # news_script.json → script.json
    python scripts/news.py render  --run-dir …     # pages + mascot + subtitles → assembly/final.mp4

The daily/weekly entry point is ``produce.py news daily|weekly``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from content_farm.production.channels import load_channel
from content_farm.production.news import script as ns
from content_farm.production.state import read_channel_code


def _channel_words(run_dir: Path):
    """(branding, chars/second) of the run's channel: chipcat 快報 keeps its defaults."""
    from content_farm.production.news.series import branding_for, news_series

    channel = load_channel(read_channel_code(run_dir))
    cps = news_series(channel).chars_per_second if ("news" in channel.series or "hn" in channel.series) \
        else ns.CHARS_PER_SECOND
    return branding_for(channel), cps


def _series(run_dir: Path):
    from content_farm.production.news.series import news_series

    channel = load_channel(read_channel_code(run_dir))
    return news_series(channel) if ("news" in channel.series or "hn" in channel.series) else None


def cmd_lint(run_dir: Path) -> int:
    from content_farm.production.news import audit_step

    news = ns.load_script(run_dir)
    _, cps = _channel_words(run_dir)
    problems = ns.lint(news, ns.load_item(run_dir), cps=cps, series=_series(run_dir),
                       after_fix=audit_step.was_fixed(run_dir))
    for problem in problems:
        print(f"✗ {problem}")
    print(f"{'FAIL' if problems else 'OK'}: {len(problems)} problem(s), ≈{ns.estimate_seconds(news, cps)}s narration")
    return 1 if problems else 0


def cmd_factcheck(run_dir: Path) -> int:
    from content_farm.production.news import fact_check

    channel = load_channel(read_channel_code(run_dir))
    return fact_check.run(run_dir, channel.code)


def cmd_audit(run_dir: Path) -> int:
    from content_farm.production.news import audit_step

    channel = load_channel(read_channel_code(run_dir))
    return audit_step.run(run_dir, channel.code, _series(run_dir))


def cmd_prepare(run_dir: Path) -> int:
    """script.json + voice_text.json. An edit that does not touch the spoken words (on-screen
    text, title, sources) keeps voice_text.json byte-identical and the measured durations, so
    the paid voice step does not re-run."""
    from content_farm.script_gen.schemas import Script

    path = run_dir / "script.json"
    previous = Script.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None
    branding, cps = _channel_words(run_dir)
    script = ns.keep_measured(ns.to_script(ns.load_script(run_dir), branding=branding, cps=cps), previous)
    path.write_text(json.dumps(script.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    voice_text = run_dir / ns.VOICE_TEXT_FILE
    text = ns.voice_text(script)
    if not voice_text.is_file() or voice_text.read_text(encoding="utf-8") != text:
        voice_text.write_text(text, encoding="utf-8")
    print(f"script.json: {len(script.scenes)} scenes, ≈{script.total_duration_seconds}s")
    return 0


def cmd_render(run_dir: Path, env_file: Path | None = None) -> int:
    from content_farm.production.news.render import render_news_short

    result = render_news_short(run_dir, load_channel(read_channel_code(run_dir)),
                               env_file=env_file or Path(__file__).resolve().parents[1] / ".env")
    print(f"{result.video} ({result.seconds}s, {result.cues} subtitle cues)")
    return 0


def cmd_weekly_check(run_dir: Path) -> int:
    from content_farm.explainer.deck import load_deck
    from content_farm.production.news.weekly import WEEKLY_FILE, check_deck

    plan = json.loads((run_dir / WEEKLY_FILE).read_text(encoding="utf-8"))
    problems = check_deck(load_deck(run_dir / "deck.json"), plan)
    for problem in problems:
        print(f"✗ {problem}")
    print(f"{'FAIL' if problems else 'OK'}: weekly deck, {len(plan['items'])} stories")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("lint", "audit", "factcheck", "prepare", "render", "weekly-check"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, help="machine-path settings for the picture/motion tools (render)")
    args = parser.parse_args(argv)
    handler = {"lint": cmd_lint, "audit": cmd_audit, "factcheck": cmd_factcheck, "prepare": cmd_prepare, "render": cmd_render,
               "weekly-check": cmd_weekly_check}[args.command]
    try:
        if args.command == "render":
            return cmd_render(args.run_dir.resolve(), args.env_file)
        return handler(args.run_dir.resolve())
    except (OSError, ValueError, ValidationError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
