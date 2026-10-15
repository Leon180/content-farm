"""Generate the model × segment grid one image at a time with mflux, measuring each run.

Each image is its own mflux process, so the model is unloaded when the process exits.
Per image: wall seconds, peak RSS of the mflux process, mflux's own "peak memory" line if it
prints one, swap used before / max during / after. Appends one JSON line per image to
<out>/results.jsonl and skips images that already exist (safe to re-run after an interruption).

Usage: python run_trial.py <prompts.json> <out_dir> <mflux_bin_dir> [model_id ...]
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

_SWAP = re.compile(r"used = ([\d.]+)M")
_PEAK = re.compile(r"[Pp]eak[^\n]*?([\d.]+)\s*GB")


def swap_used_mb() -> float:
    out = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, check=True).stdout
    match = _SWAP.search(out)
    if match is None:
        raise RuntimeError(f"unexpected vm.swapusage output: {out!r}")
    return float(match.group(1))


def rss_kb(pid: int) -> int:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return int(out) if out.isdigit() else 0


class Sampler(threading.Thread):
    def __init__(self, pid: int) -> None:
        super().__init__(daemon=True)
        self.pid, self.peak_rss_kb, self.max_swap_mb, self.stop = pid, 0, 0.0, threading.Event()

    def run(self) -> None:
        while not self.stop.is_set():
            self.peak_rss_kb = max(self.peak_rss_kb, rss_kb(self.pid))
            self.max_swap_mb = max(self.max_swap_mb, swap_used_mb())
            self.stop.wait(1.0)


def command(model: dict, prompt: str, out: Path, size: list[int], seed: int, bin_dir: Path) -> list[str]:
    return [str(bin_dir / model["command"]), "--model", model["repo"], "--base-model", model["base_model"],
            "--prompt", prompt, "--seed", str(seed), "--steps", str(model["steps"]),
            "--width", str(size[0]), "--height", str(size[1]), "--make-conf", "--output", str(out)]


def generate(model: dict, segment: dict, spec: dict, out_dir: Path, bin_dir: Path) -> dict | None:
    image = out_dir / model["id"] / f"{segment['id']}.png"
    if image.is_file():
        return None
    image.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "HF_HOME": model["hf_home"], "HF_HUB_OFFLINE": "1"}
    argv = command(model, segment["prompt"], image, spec["size"], spec["seed"], bin_dir)
    swap_before = swap_used_mb()
    started = time.monotonic()
    proc = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    sampler = Sampler(proc.pid)
    sampler.start()
    output, _ = proc.communicate()
    seconds = time.monotonic() - started
    sampler.stop.set()
    sampler.join()
    log = image.with_suffix(".log")
    log.write_text(output, encoding="utf-8")
    peak = _PEAK.findall(output)
    return {
        "model": model["id"], "segment": segment["id"], "ok": proc.returncode == 0 and image.is_file(),
        "returncode": proc.returncode, "seconds": round(seconds, 1),
        "peak_rss_gb": round(sampler.peak_rss_kb / 1024 / 1024, 2),
        "mflux_peak_gb": float(peak[-1]) if peak else None,
        "swap_before_mb": round(swap_before), "swap_max_mb": round(max(sampler.max_swap_mb, swap_before)),
        "swap_after_mb": round(swap_used_mb()),
        "steps": model["steps"], "seed": spec["seed"], "size": spec["size"], "repo": model["repo"],
        "prompt": segment["prompt"], "image": image.relative_to(out_dir).as_posix(),
        "log_tail": "" if proc.returncode == 0 else output[-600:],
    }


def main() -> int:
    spec_path, out_dir, bin_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    only = set(sys.argv[4:])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    results = out_dir / "results.jsonl"
    for model in spec["models"]:
        if only and model["id"] not in only:
            continue
        for segment in spec["segments"]:
            row = generate(model, segment, spec, out_dir, bin_dir)
            if row is None:
                continue
            with results.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{row['model']}/{row['segment']}: ok={row['ok']} {row['seconds']}s "
                  f"rss={row['peak_rss_gb']}GB swap {row['swap_before_mb']}->{row['swap_max_mb']}"
                  f"->{row['swap_after_mb']}MB", flush=True)
            if not row["ok"]:
                print(row["log_tail"], flush=True)
                break  # one failure per model is enough to diagnose; move on
            time.sleep(5)  # let the previous process release memory before the next load
    return 0


if __name__ == "__main__":
    sys.exit(main())
