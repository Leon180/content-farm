"""Voice several runs with one loaded local TTS model (Leon 2026-10-18: 同 provider 合批).

Holds the machine-wide heavy slot once, then runs the voice stage for each run-dir in one process
with a shared TTS worker (the model loads once; the voice is each channel's reference clip).
Afterwards ``produce.py run`` sees the voice outputs and skips the step when its inputs match.

    PYTHONPATH=src python scripts/voice_batch.py --env-file ../.env --run-dir output/a --run-dir output/b
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


async def _voice_all(run_dirs: list[Path], env_file: Path) -> list[dict]:
    from run_stage import run_stage  # type: ignore[import-not-found]

    from content_farm.production.channels import LOCAL_TTS_PROVIDERS, load_channel
    from content_farm.production.state import read_channel_code
    from content_farm.production.steps import EXPLAINER_SUBTITLE_MAX
    from content_farm.production.voice_choice import choose_voice, env_file_defaults
    from content_farm.voice.local_clone import SHARED_ENV, close_shared_workers

    base = dict(os.environ)
    results = []
    try:
        for run_dir in run_dirs:
            channel = load_channel(read_channel_code(run_dir))
            if channel.voice.provider not in LOCAL_TTS_PROVIDERS:
                raise SystemExit(f"{run_dir}: {channel.voice.provider} is not a local TTS provider")
            os.environ.clear()
            os.environ.update({**base, **env_file_defaults(env_file),
                               "CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE": EXPLAINER_SUBTITLE_MAX,   # as steps.voice
                               **choose_voice(channel, env_file, mock=False).env(), SHARED_ENV: "1"})
            os.environ.setdefault("CF_ANTHROPIC_API_KEY", "unused-by-tts")
            started = time.monotonic()
            await run_stage("voice", run_dir)
            results.append({"run_dir": str(run_dir), "channel": channel.code,
                            "seconds": round(time.monotonic() - started, 1)})
            print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    finally:
        await close_shared_workers()
    return results


def main() -> int:
    from content_farm.lanes.queue import Ticket, heavy_slot

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, action="append", required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    with heavy_slot(Ticket(f"voice-batch:{len(args.run_dir)} runs", kind="long"), print):
        asyncio.run(_voice_all([p.resolve() for p in args.run_dir], args.env_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
