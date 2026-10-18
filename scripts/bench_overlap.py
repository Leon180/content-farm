"""Measure whether an ffmpeg render slows local TTS (and vice versa) when they overlap.

Holds the machine-wide heavy slot for the whole measurement (nothing else heavy runs), then:
  1. TTS alone      — N sentences with the channel's local voice (model loaded once)
  2. ffmpeg alone   — libx264 encode of a clip (assembly settings)
  3. overlap        — the same TTS sentences while the same ffmpeg encode loops
Writes JSON with per-sentence seconds and the encode times.

    PYTHONPATH=src python scripts/bench_overlap.py --channel chipcat --env-file ../.env \
        --clip /path/release.mp4 --out output/bench/overlap.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import tempfile
import threading
import time
from pathlib import Path

SENTENCES = (
    "一片十二吋晶圓，只排得下六十二個這種大小的晶片。",
    "可是規劃中的九倍大封裝，同一片晶圓只剩五個。",
    "問題不在晶片本身，而是把晶片和記憶體接在一起的那一步。",
    "台積電說，明年的先進封裝產能要再翻一倍。",
    "翻倍聽起來很多，但一顆大封裝就吃掉以前好幾顆的面積。",
    "所以產能翻倍，能出貨的晶片數不一定跟著翻倍。",
)


def encode(clip: Path, seconds: int, out: Path) -> float:
    started = time.monotonic()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0", "-t", str(seconds), "-i", str(clip),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-an", str(out)], check=True)
    return round(time.monotonic() - started, 2)


async def tts(channel_code: str, env_file: Path, out_dir: Path) -> dict:
    from content_farm.config import Settings
    from content_farm.production.channels import load_channel
    from content_farm.production.voice_choice import choose_voice, env_file_defaults
    from content_farm.voice.factory import create_tts_provider

    channel = load_channel(channel_code)
    os.environ.update({**env_file_defaults(env_file), **choose_voice(channel, env_file, mock=False).env()})
    os.environ.setdefault("CF_ANTHROPIC_API_KEY", "unused-by-tts")
    # The TTS worker normally pauses while ffmpeg runs; for this measurement it must not.
    os.environ["CF_LOCAL_TTS_BUSY_PATTERN"] = "mlx_video|mflux"
    provider = create_tts_provider(Settings())  # type: ignore[call-arg]
    started = time.monotonic()
    per = []
    try:
        for n, text in enumerate(SENTENCES):
            t0 = time.monotonic()
            await provider.generate_speech(text, output_path=out_dir / f"s{n}.mp3")
            per.append(round(time.monotonic() - t0, 2))
    finally:
        await provider.aclose()
    return {"total_s": round(time.monotonic() - started, 2), "first_s": per[0], "per_sentence_s": per,
            "warm_median_s": statistics.median(per[1:])}


def main() -> int:
    from content_farm.lanes.queue import Ticket, heavy_slot

    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default="chipcat")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--clip", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result: dict = {"clip": str(args.clip), "encode_seconds_of_video": args.seconds}
    with heavy_slot(Ticket("bench:ffmpeg-vs-tts", kind="other"), print), tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        result["ffmpeg_alone_s"] = [encode(args.clip, args.seconds, work / f"a{n}.mp4") for n in range(2)]
        result["tts_alone"] = asyncio.run(tts(args.channel, args.env_file, work / "alone"))
        stop, overlap_encodes = threading.Event(), []

        def loop() -> None:
            n = 0
            while not stop.is_set():
                overlap_encodes.append(encode(args.clip, args.seconds, work / f"o{n}.mp4"))
                n += 1

        thread = threading.Thread(target=loop)
        thread.start()
        time.sleep(2)
        result["tts_overlap"] = asyncio.run(tts(args.channel, args.env_file, work / "overlap"))
        stop.set()
        thread.join()
        result["ffmpeg_during_tts_s"] = overlap_encodes
    alone, both = result["tts_alone"]["warm_median_s"], result["tts_overlap"]["warm_median_s"]
    result["tts_slowdown_x"] = round(both / alone, 2) if alone else None
    result["ffmpeg_slowdown_x"] = round(statistics.median(result["ffmpeg_during_tts_s"])
                                        / statistics.median(result["ffmpeg_alone_s"]), 2)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
