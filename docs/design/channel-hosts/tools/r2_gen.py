"""Round 2: generate the 75 candidates with local FLUX.2 [klein] 4B, one image at a time.

    PYTHONPATH=src python docs/design/channel-hosts/tools/r2_gen.py <raw_dir> [--only Y01,O03]

Before every image: no ffmpeg / remotion / mflux / mlx_video process (wan.busy_processes, which
matches the executable, not text in other processes' arguments) and `memory_pressure -Q` free
>= 25 %. Existing images are skipped, so an interrupted run resumes. Each run appends to
<raw_dir>/runs.jsonl. Writes round2/prompts.json (the exact prompts) before generating.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from r2_prompts import all_prompts, check_prompts  # noqa: E402

from content_farm.explainer.wan import busy_processes  # noqa: E402

BIN = Path(os.environ.get("CF_MFLUX_BIN_DIR", "/Users/lileon/.claude/jobs/d3bbd556/tmp/flux-venv/bin"))
HF_HOME = os.environ.get("CF_MFLUX_HF_HOME", "/Users/lileon/.claude/jobs/f9ab0177/tmp/hf")
MODEL = ["--model", "mflux-community/flux2-klein-4b-mflux-q4", "--base-model", "flux2-klein-4b", "--steps", "4",
         "--width", "768", "--height", "768"]
MIN_FREE_PERCENT = 25
WAIT_SECONDS, MAX_WAIT_SECONDS = 20, 1800


def free_percent() -> int:
    out = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True).stdout
    match = re.search(r"free percentage:\s*(\d+)%", out)
    if not match:
        raise RuntimeError(f"cannot read memory_pressure -Q: {out!r}")
    return int(match.group(1))


def wait_until_idle() -> float:
    waited = 0.0
    while True:
        busy, free = busy_processes({os.getpid()}), free_percent()
        if not busy and free >= MIN_FREE_PERCENT:
            return waited
        if waited >= MAX_WAIT_SECONDS:
            raise TimeoutError(f"still busy after {waited:.0f}s: {busy} free={free}%")
        print(f"waiting: busy={busy[:2]} free={free}%", flush=True)
        time.sleep(WAIT_SECONDS)
        waited += WAIT_SECONDS


def generate(row: dict, raw: Path, log: Path) -> None:
    out = raw / f"{row['id']}.png"
    if out.is_file():
        return
    waited = wait_until_idle()
    started = time.monotonic()
    proc = subprocess.run([str(BIN / "mflux-generate-flux2"), *MODEL, "--prompt", row["prompt"],
                           "--seed", str(row["seed"]), "--output", str(out)],
                          capture_output=True, text=True, env={**os.environ, "HF_HOME": HF_HOME, "HF_HUB_OFFLINE": "1"})
    peak = re.findall(r"Peak MLX memory: ([\d.]+) GB", proc.stdout + proc.stderr)
    record = {"id": row["id"], "seed": row["seed"], "rc": proc.returncode, "seconds": round(time.monotonic() - started, 1),
              "waited": waited, "peak_gb": float(peak[-1]) if peak else None}
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    print(json.dumps(record), flush=True)
    if proc.returncode != 0 or not out.is_file():
        raise RuntimeError(f"{row['id']} failed: {(proc.stderr or proc.stdout)[-600:]}")
    time.sleep(2)


def main(argv: list[str]) -> int:
    raw = Path(argv[0])
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
    rows = all_prompts()
    check_prompts(rows)
    (HERE.parent / "round2").mkdir(exist_ok=True)
    (HERE.parent / "round2" / "prompts.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    raw.mkdir(parents=True, exist_ok=True)
    for row in rows:
        if only is None or row["id"] in only:
            generate(row, raw, raw / "runs.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
