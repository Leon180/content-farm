"""PNGtuber-route concept art with local FLUX.2 [klein] 4B (Apache-2.0), one mflux process per image.

    PYTHONPATH=src python docs/design/channel-hosts/tools/ai_gen.py base   <raw_dir>
    PYTHONPATH=src python docs/design/channel-hosts/tools/ai_gen.py edits  <raw_dir> yokai=<seed> ...
    PYTHONPATH=src python docs/design/channel-hosts/tools/ai_gen.py drift  <raw_dir>

base   text-to-image, two seeds per character (pick one by eye)
edits  multi-reference edit from the chosen base: blink / talk / 2 expressions / a pose (consistency test)
drift  same prompt, a third seed, no reference (what you get without reference images)

Each image waits for memory pressure < warn and for no other mflux / mlx_video process
(content_farm.explainer.illustrate.wait_for_memory). Every run appends a line to
<raw_dir>/runs.jsonl (argv, seconds, peak memory) so an interrupted batch can be resumed:
images that already exist are skipped.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from content_farm.explainer.illustrate import wait_for_memory

BIN = Path(os.environ.get("CF_MFLUX_BIN_DIR", "/Users/lileon/.claude/jobs/d3bbd556/tmp/flux-venv/bin"))
HF_HOME = os.environ.get("CF_MFLUX_HF_HOME", "/Users/lileon/.claude/jobs/f9ab0177/tmp/hf")
MODEL = ["--model", "mflux-community/flux2-klein-4b-mflux-q4", "--base-model", "flux2-klein-4b", "--steps", "4"]
SIZE = ["--width", "768", "--height", "768"]
BASE_SEEDS = (11, 23)
DRIFT_SEED = 37

TAIL = ("Full body, front view, centered, standing on nothing, generous margin around the figure. "
        "Plain pure white background, no text, no letters, no logo, no watermark, no frame. "
        "An original character, not resembling any existing mascot, anime or cartoon character.")

CHARACTERS = {
    "yokai": (
        "Original mascot character design: a small chubby silverfish bookworm spirit who lives inside "
        "ancient Chinese books, a scholar. Pale silver-grey segmented body, three short tail filaments, two "
        "long curved antennae, big friendly dark eyes, tiny round brass spectacles, a small black scholar's cap, "
        "holding a rolled bamboo scroll in its little front legs, sitting upright facing the viewer. "
        "Style: cute East Asian ink wash illustration with confident brush outlines and flat muted washes: "
        "ink black, rice-paper cream, a touch of cinnabar red and verdigris green. "),
    "offwork": (
        "Original mascot character design: a round pufferfish office worker. Pale cream-white round body with "
        "short soft spikes, pink cheeks, big tired half-lidded eyes, a loose cobalt-blue employee lanyard with an "
        "ID badge, a tiny hot-pink necktie, two small fins holding a coffee mug. "
        "Style: bold flat comic sticker illustration, thick black ink outlines, flat colours only "
        "(hot pink, cobalt blue, black, white), no gradients, no shading. "),
    "cel": (
        "Original mascot character design: a small friendly ghost-like creature made of a transparent celluloid "
        "animation cel. Its body is a rounded rectangular see-through sheet, slightly curled at the bottom, with "
        "three peg-bar registration holes along its top edge, a simple hand-drawn face, two little arms, holding "
        "a red correction pencil. "
        "Style: clean hand-drawn 2D animation key-frame look, crisp dark pencil line, soft flat colours: warm paper "
        "cream, light non-photo blue, red pencil accents. "),
}

KEEP = ("Keep exactly the same character from the reference image: same design, same proportions, same colours, "
        "same outline style, same framing and size, plain white background. ")
EDITS = {
    "blink": KEEP + "Change only the eyes: both eyes gently closed (a blink). Mouth closed.",
    "talk": KEEP + "Change only the mouth: mouth open mid-sentence as if talking. Eyes open.",
    "surprised": KEEP + "Change only the face: surprised, eyes wide open, small round open mouth.",
    "smug": KEEP + "Change only the face: smug, eyes half closed, a confident sideways smile.",
    "wave": KEEP + "Now the character raises one arm and waves at the viewer, body turned slightly to the side.",
}


def run(argv: list[str], out: Path, log: Path, meta: dict) -> None:
    if out.is_file():
        print(f"skip {out.name} (exists)", flush=True)
        return
    waited = wait_for_memory()
    started = time.monotonic()
    proc = subprocess.run(argv, capture_output=True, text=True,
                          env={**os.environ, "HF_HOME": HF_HOME, "HF_HUB_OFFLINE": "1"})
    seconds = round(time.monotonic() - started, 1)
    peak = re.findall(r"Peak MLX memory: ([\d.]+) GB", proc.stdout + proc.stderr)
    record = {**meta, "out": out.name, "rc": proc.returncode, "seconds": seconds, "waited": waited,
              "peak_gb": float(peak[-1]) if peak else None}
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps(record, ensure_ascii=False), flush=True)
    if proc.returncode != 0 or not out.is_file():
        raise RuntimeError(f"{out.name} failed rc={proc.returncode}: {(proc.stderr or proc.stdout)[-600:]}")
    time.sleep(3)


def t2i(code: str, seed: int, out: Path, log: Path, kind: str) -> None:
    prompt = CHARACTERS[code] + TAIL
    argv = [str(BIN / "mflux-generate-flux2"), *MODEL, *SIZE, "--prompt", prompt, "--seed", str(seed),
            "--output", str(out)]
    run(argv, out, log, {"kind": kind, "code": code, "seed": seed, "prompt": prompt})


def edit(code: str, ref: Path, name: str, seed: int, out: Path, log: Path) -> None:
    prompt = EDITS[name]
    argv = [str(BIN / "mflux-generate-flux2-edit"), *MODEL, *SIZE, "--image-paths", str(ref),
            "--prompt", prompt, "--seed", str(seed), "--output", str(out)]
    run(argv, out, log, {"kind": "edit", "code": code, "edit": name, "ref": ref.name, "seed": seed, "prompt": prompt})


def main(argv: list[str]) -> int:
    mode, raw = argv[0], Path(argv[1])
    raw.mkdir(parents=True, exist_ok=True)
    log = raw / "runs.jsonl"
    if mode == "base":
        for code in CHARACTERS:
            for seed in BASE_SEEDS:
                t2i(code, seed, raw / f"{code}_base_s{seed}.png", log, "base")
    elif mode == "drift":
        for code in CHARACTERS:
            t2i(code, DRIFT_SEED, raw / f"{code}_drift_s{DRIFT_SEED}.png", log, "drift")
    elif mode == "edits":
        for pick in argv[2:]:
            code, seed = pick.split("=")
            ref = raw / f"{code}_base_s{seed}.png"
            for name in EDITS:
                edit(code, ref, name, int(seed), raw / f"{code}_{name}.png", log)
    else:
        raise SystemExit(f"unknown mode {mode!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
