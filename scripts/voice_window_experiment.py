"""Which voice window to re-synthesize when one sentence changes (±0 / ±1 / ±2 / whole scene)?

Usage:
    python scripts/voice_window_experiment.py --run-dir output/<run> --channel chipcat \
        --slide k1 --sentence 5 --new "每月大約 200 萬個封裝；" --env-file <main>/.env [--seeds 3]

For the chosen sentence of one slide it re-voices, with the channel's local TTS:
  w0   the new sentence alone;
  w0p  the new sentence continuing from the old take's previous sentence (prompt audio, VoxCPM2);
  w1   previous + new + next sentence (same slide) as one call;
  w2   two neighbours on each side;
  full the whole slide narration (what the pipeline did before);
splices each into the old raw take (voice.splice) and measures the seams: pitch jump
(semitones), loudness jump (dB) and the speech-rate ratio of the new part vs the old take.
Baseline = the same jumps at every natural sentence boundary of every old take in the run.
Writes <run-dir>/experiments/voice_window/{results.json, *.mp3}. Local model only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

from content_farm.retention.timing import normalise, split_sentences
from content_farm.voice import splice as sp


def _settings(run_dir: Path, channel_code: str, env_file: Path):
    from content_farm.production.channels import load_channel
    from content_farm.production.steps import Context, RunOptions, _voice_env

    ctx = Context(load_channel(channel_code), run_dir, RunOptions(env_file=env_file))
    os.environ.update(_voice_env(ctx))
    from content_farm.config import Settings

    return Settings()


def _tts_text(settings, deck: dict, text: str) -> str:
    from content_farm.voice.pronunciation import load_table, merged_map
    from content_farm.voice.text_normalize import normalize_for_tts

    table = (load_table(Path(settings.pronunciation_file), provider=settings.tts_provider,
                        channel=settings.channel_code) if settings.pronunciation_file else None)
    return normalize_for_tts(text, merged_map(table, deck.get("pronunciation_map") or {}))


def _slides(deck: dict) -> list[dict]:
    return [s for section in deck["sections"] for s in section["slides"]]


def baseline(run_dir: Path, deck: dict) -> list[dict]:
    """Seam jumps at the natural sentence boundaries of every old raw take."""
    out = []
    for index, slide in enumerate(_slides(deck), start=1):
        raw = run_dir / "audio" / "raw" / f"scene_{index:03d}.mp3"
        if not raw.is_file():
            continue
        samples = sp.decode(raw)
        sentences = split_sentences(slide["narration"])
        try:
            cuts = sp.sentence_cuts(samples, [len(normalise(s)) for s in sentences])
        except sp.SpliceError:
            continue
        out.extend({"slide": slide["id"], **sp.seam_jump(samples, at).to_json()} for at in cuts[1:-1])
    return out


def _stats(values: list[float]) -> dict:
    vals = np.array([v for v in values if v == v])
    if not vals.size:
        return {}
    return {"n": int(vals.size), "median": round(float(np.median(vals)), 2),
            "p90": round(float(np.percentile(vals, 90)), 2), "max": round(float(vals.max()), 2)}


async def run(args: argparse.Namespace) -> dict:
    run_dir: Path = args.run_dir
    deck = json.loads((run_dir / "deck.json").read_text(encoding="utf-8"))
    slides = _slides(deck)
    index = next(i for i, s in enumerate(slides, start=1) if s["id"] == args.slide)
    slide = slides[index - 1]
    old_sentences = split_sentences(slide["narration"])
    t = args.sentence
    new_sentences = [*old_sentences[:t], args.new, *old_sentences[t + 1:]]
    raw = sp.decode(run_dir / "audio" / "raw" / f"scene_{index:03d}.mp3")
    cuts = sp.sentence_cuts(raw, [len(normalise(s)) for s in old_sentences])
    old_rate = sp.speech_rate(raw, sum(len(normalise(s)) for s in old_sentences))

    settings = _settings(run_dir, args.channel, args.env_file)
    from content_farm.voice.factory import create_tts_provider

    tts = create_tts_provider(settings)
    out_dir = run_dir / "experiments" / "voice_window"
    out_dir.mkdir(parents=True, exist_ok=True)
    prev_clip = out_dir / "prompt_prev.mp3"
    sp.encode(raw[int(cuts[t - 1] * sp.SR): int(cuts[t] * sp.SR)], prev_clip)
    variants = {"w0": (t, t, None), "w0p": (t, t, (prev_clip, old_sentences[t - 1])),
                "w1": (t - 1, t + 1, None), "w2": (t - 2, t + 2, None),
                "full": (0, len(old_sentences) - 1, None)}
    results: dict[str, list[dict]] = {}
    try:
        for name, (first, last, prompt) in variants.items():
            first, last = max(first, 0), min(last, len(old_sentences) - 1)
            text = "".join(new_sentences[first:last + 1])
            for k in range(args.seeds):
                seed = settings.tts_seed + 7919 * k
                path = out_dir / f"{name}_seed{seed}.mp3"
                started = time.monotonic()
                kwargs = {"prompt": prompt} if prompt else {}
                await tts.generate_speech(_tts_text(settings, deck, text), output_path=path, seed=seed, **kwargs)
                gen_s = time.monotonic() - started
                new = sp.decode(path)
                spliced = sp.splice(raw, cuts, first, last, new) if name != "full" else new
                sp.encode(spliced, out_dir / f"{name}_seed{seed}_scene.mp3")
                left = cuts[first]
                right = len(spliced) / sp.SR - (len(raw) / sp.SR - cuts[last + 1])
                seams = [] if name == "full" else [
                    sp.seam_jump(spliced, at).to_json() for at in (left, right) if 0 < at < len(spliced) / sp.SR - 0.05]
                chars = sum(len(normalise(s)) for s in new_sentences[first:last + 1])
                rate = sp.speech_rate(new, chars)
                results.setdefault(name, []).append({
                    "seed": seed, "gen_s": round(gen_s, 1), "sentences": [first, last],
                    "audio_s": round(len(new) / sp.SR, 2), "seams": seams,
                    "rate_ratio": round(rate / old_rate, 3) if old_rate else None})
                print(f"{name} seed {seed}: {gen_s:.1f}s, seams {seams}, rate x{rate / old_rate:.2f}", flush=True)
    finally:
        await tts.aclose()
    summary = {name: {"pitch_st": _stats([s["pitch_st"] for r in rows for s in r["seams"]]),
                      "loudness_db": _stats([s["loudness_db"] for r in rows for s in r["seams"]]),
                      "rate_ratio": _stats([abs(1 - r["rate_ratio"]) for r in rows if r["rate_ratio"]]),
                      "gen_s": _stats([r["gen_s"] for r in rows])} for name, rows in results.items()}
    base = baseline(run_dir, deck)
    summary["baseline_natural_boundaries"] = {"pitch_st": _stats([b["pitch_st"] for b in base]),
                                              "loudness_db": _stats([b["loudness_db"] for b in base])}
    payload = {"slide": args.slide, "scene": index, "sentence": t, "old": old_sentences[t], "new": args.new,
               "cuts": [round(c, 3) for c in cuts], "old_rate_cps": round(old_rate, 2),
               "results": results, "summary": summary, "baseline": base}
    (out_dir / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--slide", required=True)
    parser.add_argument("--sentence", type=int, required=True, help="0-based sentence index in the slide")
    parser.add_argument("--new", required=True, help="the rewritten sentence")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--seeds", type=int, default=3)
    args = parser.parse_args(argv)
    payload = asyncio.run(run(args))
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
