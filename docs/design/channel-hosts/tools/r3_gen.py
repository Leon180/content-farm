"""Round 3: PNGtuber source frames for Leon's picks (Y14, O25, C09) with klein multi-reference edits.

    PYTHONPATH=src python docs/design/channel-hosts/tools/r3_gen.py <r2_raw_dir> <out_dir>

For each pick: an optional clean-up edit of the chosen image becomes the base, then one edit per
state (mouth_half, mouth_open, blink, surprised, smug, speechless) from that base. Each edit is
accepted only if its cut-out silhouette IoU against the base is >= 0.99; otherwise the next seed
is tried (3 seeds). Same gate as round 2 (no other model / render process, free memory >= 25 %).
Writes <out_dir>/<pick>/<state>.png and <out_dir>/r3_runs.jsonl (every attempt, kept or not).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cutout import cut_white  # noqa: E402
from r2_gen import BIN, HF_HOME, wait_until_idle  # noqa: E402

MODEL = ["--model", "mflux-community/flux2-klein-4b-mflux-q4", "--base-model", "flux2-klein-4b", "--steps", "4",
         "--width", "768", "--height", "768"]
IOU_MIN = 0.99
SEEDS = (301, 302, 303)

KEEP = ("Keep exactly the same character from the reference image: same design, same proportions, same colours, "
        "same outline, same position, same size and framing, plain white background. ")
PICKS = {
    "Y14": {"clean": "Remove the grey stick behind the frog's right leg; the frog keeps holding only the black brush. "
                     "Change nothing else."},
    "O25": {},
    "C09": {},
}
STATES = {
    "mouth_half": "Change only the mouth: slightly open, mid-word. Eyes unchanged.",
    "mouth_open": "Change only the mouth: wide open as if talking loudly. Eyes unchanged.",
    "blink": "Change only the eyes: both eyes closed, a blink. Mouth unchanged.",
    "surprised": "Change only the face: surprised, eyes wide, small round open mouth.",
    "smug": "Change only the face: smug, eyes half closed, a confident sideways smile.",
    # v2: the first wording made the frog lose its eyes entirely; ask for visible flat-line eyes
    "speechless": ("Change only the face: speechless and unimpressed. Keep both eyes visible but drawn as two short "
                   "flat horizontal black lines, a tiny flat mouth, one small sweat drop beside the head."),
}


def mask(path: Path) -> np.ndarray:
    return np.asarray(cut_white(Image.open(path).convert("RGB")).getchannel("A")) > 128


def iou(a: np.ndarray, b: np.ndarray) -> float:
    return float((a & b).sum() / max(1, (a | b).sum()))


def edit(ref: Path, prompt: str, seed: int, out: Path, log: Path, meta: dict) -> dict:
    waited = wait_until_idle()
    started = time.monotonic()
    proc = subprocess.run([str(BIN / "mflux-generate-flux2-edit"), *MODEL, "--image-paths", str(ref),
                           "--prompt", KEEP + prompt, "--seed", str(seed), "--output", str(out)],
                          capture_output=True, text=True, env={**os.environ, "HF_HOME": HF_HOME, "HF_HUB_OFFLINE": "1"})
    peak = re.findall(r"Peak MLX memory: ([\d.]+) GB", proc.stdout + proc.stderr)
    record = {**meta, "seed": seed, "rc": proc.returncode, "seconds": round(time.monotonic() - started, 1),
              "waited": waited, "peak_gb": float(peak[-1]) if peak else None}
    if proc.returncode != 0 or not out.is_file():
        record["error"] = (proc.stderr or proc.stdout)[-300:]
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    time.sleep(2)
    return record


def accepted_edit(base: Path, prompt: str, out: Path, log: Path, meta: dict, *, tag: str = "",
                  iou_min: float = IOU_MIN) -> dict:
    """Try SEEDS until the silhouette IoU against base reaches iou_min; keep the best attempt either way."""
    if out.is_file() and not tag:
        return {**meta, "skipped": True}
    base_mask, best = mask(base), None
    for seed in SEEDS:
        trial = out.with_name(f"{out.stem}{tag}_s{seed}.png")
        record = edit(base, prompt, seed, trial, log, meta)
        if record["rc"] != 0:
            continue
        score = iou(base_mask, mask(trial))
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({**meta, "seed": seed, "iou": round(score, 4)}) + "\n")
        print(f"{meta} seed {seed} iou {score:.4f}", flush=True)
        if best is None or score > best[0]:
            best = (score, trial, seed)
        if score >= iou_min:
            break
    if best is None:
        raise RuntimeError(f"every attempt failed for {meta}")
    out.write_bytes(best[1].read_bytes())
    return {**meta, "seed": best[2], "iou": round(best[0], 4), "passed": best[0] >= iou_min}


def redo(out_dir: Path, items: str) -> int:
    """--redo Y14:speechless[,…]: regenerate those states (attempts tagged _v2), overwriting <state>.png."""
    log, summary = out_dir / "r3_runs.jsonl", []
    for item in items.split(","):
        pick, state = item.split(":")
        work = out_dir / pick
        summary.append(accepted_edit(work / "base.png", STATES[state], work / f"{state}.png", log,
                                     {"pick": pick, "state": state, "redo": True}, tag="_v2"))
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if all(s.get("passed") for s in summary) else 1


def main(argv: list[str]) -> int:
    if len(argv) > 2 and argv[1] == "--redo":
        return redo(Path(argv[0]), argv[2])
    r2_raw, out_dir = Path(argv[0]), Path(argv[1])
    log, summary = out_dir / "r3_runs.jsonl", []
    for pick, opts in PICKS.items():
        work = out_dir / pick
        work.mkdir(parents=True, exist_ok=True)
        source = r2_raw / f"{pick}.png"
        base = work / "base.png"
        if not base.is_file():
            if "clean" in opts:
                summary.append(accepted_edit(source, opts["clean"], base, log, {"pick": pick, "state": "base"}))
            else:
                base.write_bytes(source.read_bytes())
        for state, prompt in STATES.items():
            summary.append(accepted_edit(base, prompt, work / f"{state}.png", log, {"pick": pick, "state": state}))
    (out_dir / "r3_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    failed = [s for s in summary if s.get("passed") is False]
    print("failed:", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
