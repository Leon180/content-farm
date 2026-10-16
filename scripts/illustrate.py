"""Generate the deck's ``ai_image`` illustrations with the channel's local model.

Usage:
    python scripts/illustrate.py --run-dir output/<run> --channel yokai
    python scripts/illustrate.py --run-dir <dir> --channel chipcat --replace   # regenerate

Reads ``channels/<code>.yaml`` → ``ai_illustration`` (model, style prefix, seed, size).
Needs CF_MFLUX_BIN_DIR and CF_MFLUX_HF_HOME (environment, else ``--env-file``).
Writes ``assets/ai_images/<slide_id>.png`` and a ``<slide_id>.json`` sidecar (model,
prompt, seed, steps, licence, timing) that the media step copies into credits.json.
One image per mflux process; waits while macOS memory pressure is warn or worse.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from content_farm.explainer.deck import load_deck
from content_farm.explainer.illustrate import LocalMflux, Settings, illustrate, missing_images
from content_farm.production.channels import load_channel
from content_farm.production.voice_choice import env_file_defaults

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    parser.add_argument("--replace", action="store_true", help="regenerate images that already exist")
    args = parser.parse_args()

    channel = load_channel(args.channel)
    if not channel.media.ai_image:
        print(f"channel {channel.code} does not allow ai_image; nothing to do")
        return 0
    deck = load_deck(args.run_dir / "deck.json")
    config = channel.ai_illustration
    settings = Settings(config.model, config.style_prefix, config.seed, config.width, config.height)
    pending = missing_images(deck, args.run_dir, settings, replace=args.replace)
    if not pending:
        print("no ai_image slide is missing an image; nothing to generate")
        return 0
    print(f"{len(pending)} image(s) to generate with {config.model}: {', '.join(pending)}")
    env = {**env_file_defaults(args.env_file), **os.environ}
    try:
        provider = LocalMflux.from_env(config.model, env)
        records = illustrate(deck, args.run_dir, settings, provider, replace=args.replace)
    except (RuntimeError, ValueError, FileNotFoundError, TimeoutError) as exc:
        print(f"illustrate failed: {exc}", file=sys.stderr)
        return 1
    for record in records:
        print(f"{record['slide_id']}: {record['model']} {record['seconds']}s "
              f"swap {record['swap_before_mb']}→{record['swap_after_mb']} MB")
    print(f"{len(records)} image(s) generated with {config.model}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
