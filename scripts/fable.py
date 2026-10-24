"""寓言學堂 (fable channel) tools, run by the pipeline steps.

    python scripts/fable.py lint     --run-dir output/<run>     # fable.json: structure, reveal rule, thread ledger
    python scripts/fable.py prepare  --run-dir output/<run>     # fable.json -> script.json + voice_text.json
    python scripts/fable.py images   --run-dir output/<run> [--env-file .env]   # draw pictures + parallax clips
    python scripts/fable.py render   --run-dir output/<run>     # compose final.mp4 (needs images + the voice step)
    python scripts/fable.py guesses  --run-dir output/<run>     # the script panel's 「在哪一句猜到」 table

Exit codes: 0 ok, 1 problems found (all listed), 2 missing or unreadable input.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from content_farm.production.fable import check, guesses, model, prepare


def _load(run_dir: Path) -> model.Fable | None:
    try:
        return model.load(run_dir)
    except FileNotFoundError:
        print(f"missing {run_dir / model.FABLE_FILE}", file=sys.stderr)
    except ValidationError as exc:
        print(f"{model.FABLE_FILE} does not match the schema:\n{exc}", file=sys.stderr)
    return None


def cmd_lint(args: argparse.Namespace) -> int:
    fable = _load(args.run_dir)
    if fable is None:
        return 2
    problems = check.fable_problems(fable)
    for problem in problems:
        print(f"- {problem}")
    print(f"{len(problems)} problem(s); estimated {check.estimated_seconds(fable):g} s, {len(fable.beats)} beats")
    return 1 if problems else 0


def cmd_prepare(args: argparse.Namespace) -> int:
    if _load(args.run_dir) is None:
        return 2
    script = prepare.prepare(args.run_dir)
    print(f"script.json: {len(script.scenes)} scenes, ~{script.total_duration_seconds:g} s")
    return 0


def cmd_images(args: argparse.Namespace) -> int:
    from content_farm.production.channels import load_channel
    from content_farm.production.fable import images
    from content_farm.production.state import read_channel_code

    fable = _load(args.run_dir)
    if fable is None:
        return 2
    channel = load_channel(read_channel_code(args.run_dir))
    manifest, drawn = images.build(args.run_dir, fable, channel, env_file=args.env_file)
    print(f"{manifest}: {len(images.drawn_shots(fable))} pictures ({drawn} drawn now), each with a parallax clip")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    from content_farm.production.channels import load_channel
    from content_farm.production.fable import render
    from content_farm.production.state import read_channel_code

    if _load(args.run_dir) is None:
        return 2
    channel = load_channel(read_channel_code(args.run_dir))
    result = render.render_fable(args.run_dir, channel, env_file=args.env_file)
    print(f"{result.video}: {result.seconds:g} s, {result.pictures} pictures ({result.drawn} drawn now), {result.cues} subtitle cues")
    return 0


def cmd_guesses(args: argparse.Namespace) -> int:
    rows = guesses.collect(args.run_dir)
    print(guesses.table(rows))
    return 0 if rows else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in (("lint", cmd_lint), ("prepare", cmd_prepare), ("images", cmd_images), ("render", cmd_render),
                       ("guesses", cmd_guesses)):
        p = sub.add_parser(name)
        p.add_argument("--run-dir", type=Path, required=True)
        if name in ("images", "render"):
            p.add_argument("--env-file", type=Path, default=None)
        p.set_defaults(func=func)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
