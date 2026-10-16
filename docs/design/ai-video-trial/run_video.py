"""Generate the model × shot video grid one clip at a time, measuring each run, then burn in 「AI 示意圖」.

Each clip is its own process (the model unloads when it exits). Before every clip we wait until no
other session is rendering (ffmpeg etc.). Per clip: wall seconds, peak RSS of the process tree, the
pipeline's own "peak memory" line if it prints one, swap before / max during / after. A clip that
runs past timeout_seconds is killed and recorded as a timeout. Re-running skips finished clips.

Usage: python run_video.py <shots.json> <models.json> <src_dir> <out_dir> <python> [model_id ...] [--only shot_id ...]
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from trial_common import Sampler, label_layer, swap_used_mb, wait_until_render_idle

DOCS = Path(__file__).resolve().parent
_PEAK = re.compile(r"[Pp]eak[^\n]*?([\d.]+)\s*GB")


def expand(template: list[str], values: dict, image: Path | None) -> list[str]:
    argv: list[str] = []
    for part in template:
        if part == "{image_flag}":
            argv += ["--image", str(image)] if image else []
        else:
            argv.append(part.format(**values))
    return argv


def burn_label(raw: Path, labelled: Path) -> None:
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", str(raw)],
                           capture_output=True, text=True, check=True).stdout.strip()
    width, height = (int(v) for v in probe.split(","))
    layer = labelled.with_suffix(".label.png")
    label_layer(width, height).save(layer)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-i", str(layer), "-filter_complex",
                    "overlay=0:0", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-an", str(labelled)],
                   check=True)
    layer.unlink()


def run_clip(model: dict, job: dict, spec: dict, out_dir: Path, python: str) -> dict:
    raw = out_dir / "raw" / model["id"] / f"{job['id']}.mp4"
    raw.parent.mkdir(parents=True, exist_ok=True)
    values = {"python": python, "docs": str(DOCS), "model_dir": model["model_dir"], "prompt": job["prompt"],
              "width": spec["size"][0], "height": spec["size"][1], "num_frames": spec["num_frames"],
              "seed": job["seed"], "output": str(raw)}
    argv = expand(model["argv"], values, job.get("image_path"))
    waited = wait_until_render_idle({os.getpid()})
    swap_before, started = swap_used_mb(), time.monotonic()
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    sampler = Sampler(proc.pid)
    sampler.start()
    timed_out = False
    try:
        output, _ = proc.communicate(timeout=spec["timeout_seconds"])
    except subprocess.TimeoutExpired:
        proc.kill()
        output, _ = proc.communicate()
        timed_out = True
    seconds = time.monotonic() - started
    sampler.stop.set()
    sampler.join()
    raw.with_suffix(".log").write_text(output, encoding="utf-8")
    ok = proc.returncode == 0 and raw.is_file() and not timed_out
    labelled = out_dir / "labeled" / model["id"] / f"{job['id']}.mp4"
    if ok:
        labelled.parent.mkdir(parents=True, exist_ok=True)
        burn_label(raw, labelled)
    peak = _PEAK.findall(output)
    return {"model": model["id"], "segment": job["id"], "mode": job["mode"], "ok": ok, "timed_out": timed_out,
            "returncode": proc.returncode, "seconds": round(seconds, 1), "gate_wait_seconds": waited,
            "peak_rss_gb": round(sampler.peak_rss_kb / 1024 / 1024, 2),
            "reported_peak_gb": float(peak[-1]) if peak else None,
            "swap_before_mb": round(swap_before), "swap_max_mb": round(max(sampler.max_swap_mb, swap_before)),
            "swap_after_mb": round(swap_used_mb()), "size": spec["size"], "num_frames": spec["num_frames"],
            "fps": spec["fps"], "seed": job["seed"], "repo": model["repo"], "prompt": job["prompt"],
            "video": labelled.relative_to(out_dir).as_posix() if ok else None,
            "log_tail": "" if ok else output[-800:]}


def jobs(shots: dict, src_dir: Path) -> list[dict]:
    rows = [{"id": s["id"], "mode": "i2v", "prompt": s["prompt"], "seed": shots["seed"],
             "image_path": src_dir / s["image"]} for s in shots["shots"]]
    t2v = shots["t2v"]
    rows.append({"id": t2v["id"], "mode": "t2v", "prompt": t2v["prompt"], "seed": shots["seed"], "image_path": None})
    return rows


def main() -> int:
    shots_path, models_path, src_dir, out_dir, python = (Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]),
                                                         Path(sys.argv[4]), sys.argv[5])
    rest = sys.argv[6:]
    only_shots = set(rest[rest.index("--only") + 1:]) if "--only" in rest else set()
    only_models = set(rest[:rest.index("--only")] if "--only" in rest else rest)
    shots = json.loads(shots_path.read_text(encoding="utf-8"))
    spec = json.loads(models_path.read_text(encoding="utf-8"))
    results = out_dir / "results.jsonl"
    for model in spec["models"]:
        if only_models and model["id"] not in only_models:
            continue
        for job in jobs(shots, src_dir):
            if only_shots and job["id"] not in only_shots:
                continue
            if (out_dir / "labeled" / model["id"] / f"{job['id']}.mp4").is_file():
                continue
            row = run_clip(model, job, spec, out_dir, python)
            with results.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{row['model']}/{row['segment']}: ok={row['ok']} {row['seconds']}s rss={row['peak_rss_gb']}GB "
                  f"swap {row['swap_before_mb']}->{row['swap_max_mb']}->{row['swap_after_mb']}MB", flush=True)
            if not row["ok"]:
                print(row["log_tail"], flush=True)
                break
            time.sleep(10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
