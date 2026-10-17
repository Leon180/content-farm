"""Build the launch-video thumbnail variants (3 per video) and the promise map.

    PYTHONPATH=src python docs/design/thumbnails/tools/tn_build.py check  <launch_output_dir> <work_dir>
    PYTHONPATH=src python docs/design/thumbnails/tools/tn_build.py keyart <launch_output_dir> <work_dir>
    PYTHONPATH=src python docs/design/thumbnails/tools/tn_build.py render <launch_output_dir> <work_dir>

check   validate every spec and run the promise QC against the real script.json (no rendering)
keyart  generate the AI key art (klein, one image at a time, same gate as the host images)
render  scratch run dirs in <work_dir> (inputs linked read-only), render, QC, copy to
        docs/design/thumbnails/<video>/variant_<k>.jpg, write promises.json (where each promise is spoken)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(OUT.parent / "channel-hosts" / "tools"))
from tn_variants import VIDEOS  # noqa: E402

from content_farm.production import thumbnail as th  # noqa: E402
from content_farm.production.channels import load_channel  # noqa: E402

LINKS = ("script.json", "assets")


def scratch(src: Path, dst: Path, video: dict) -> Path:
    dst.mkdir(parents=True, exist_ok=True)
    for name in LINKS:
        if (src / name).exists() and not (dst / name).exists():
            (dst / name).symlink_to(src / name)
    (dst / "thumbnails").mkdir(exist_ok=True)
    (dst / th.VARIANTS_FILE).write_text(json.dumps({"vertical": video["vertical"], "variants": video["variants"]},
                                                   ensure_ascii=False, indent=1), encoding="utf-8")
    return dst


def spoken_at(run_dir: Path, phrase: str) -> float | None:
    """Start time of the first scene whose narration contains the phrase (punctuation and spaces ignored)."""
    target = th._compact(phrase)
    for start, text in th._narration_starts(run_dir):
        if target in text:
            return round(start, 1)
    return None


def check(src_root: Path, work: Path) -> int:
    bad = 0
    for name, video in VIDEOS.items():
        run = scratch(src_root / video["source"], work / name, video)
        spec_set = th.load_variants(run)
        for key, spec in spec_set.variants.items():
            problems = th.promise_findings(run, spec, f"{name} {key}")
            times = {p: spoken_at(run, p) for p in spec.promise}
            print(f"{name} {key} [{spec.layout}] 「{spec.text}」 promises {times}",
                  "OK" if not problems else [f.message for f in problems])
            bad += len(problems)
    return 1 if bad else 0


def keyart(src_root: Path, work: Path) -> int:
    from r2_gen import BIN, HF_HOME, wait_until_idle
    from r2_prompts import banned_terms

    for name, video in VIDEOS.items():
        prompt = video["keyart_prompt"]
        if not prompt:
            continue
        if banned_terms(prompt):
            raise ValueError(f"{name}: banned terms in key-art prompt: {banned_terms(prompt)}")
        out = work / "keyart" / f"{video.get('keyart_file', name)}.png"
        if out.is_file():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        size = ["--width", "768", "--height", "1344"] if video["vertical"] else ["--width", "1280", "--height", "720"]
        waited = wait_until_idle()
        started = time.monotonic()
        proc = subprocess.run([str(BIN / "mflux-generate-flux2"), "--model", "mflux-community/flux2-klein-4b-mflux-q4",
                               "--base-model", "flux2-klein-4b", "--steps", "4", *size, "--seed", "42",
                               "--prompt", prompt, "--output", str(out)], capture_output=True, text=True,
                              env={**os.environ, "HF_HOME": HF_HOME, "HF_HUB_OFFLINE": "1"})
        record = {"video": name, "rc": proc.returncode, "seconds": round(time.monotonic() - started, 1),
                  "waited": waited, "model": "FLUX.2 [klein] 4B (q4)", "license": "Apache-2.0", "seed": 42,
                  "prompt": prompt}
        (out.with_suffix(".json")).write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(record, ensure_ascii=False), flush=True)
        if proc.returncode != 0:
            raise RuntimeError(f"{name}: {(proc.stderr or proc.stdout)[-400:]}")
    return 0


def render(src_root: Path, work: Path) -> int:
    report = {}
    for name, video in VIDEOS.items():
        run = scratch(src_root / video["source"], work / name, video)
        if video["keyart_prompt"]:
            (run / "keyart").mkdir(exist_ok=True)
            shutil.copy2(work / "keyart" / f"{video.get('keyart_file', name)}.png", run / "keyart" / "keyart.png")
        channel = load_channel(video["channel"])
        outputs = th.render_variants(run, channel)
        findings = th.variant_findings(run, channel)
        dest = OUT / name
        dest.mkdir(parents=True, exist_ok=True)
        spec_set = th.load_variants(run)
        report[name] = {"channel": channel.name, "vertical": video["vertical"],
                        "qc": [f"[{f.level}] {f.message}" for f in findings], "variants": {}}
        for key, path in outputs.items():
            shutil.copy2(path, dest / path.name)
            spec = spec_set.variants[key]
            report[name]["variants"][key] = {
                "layout": spec.layout, "text": spec.text, "sub": spec.sub, "file": f"{name}/{path.name}",
                "kb": path.stat().st_size // 1024,
                "promises": [{"phrase": p, "spoken_at_s": spoken_at(run, p)} for p in spec.promise],
                "visual": spec.visual.kind, "credit": getattr(spec.visual, "credit", "")}
        if video["keyart_prompt"]:
            shutil.copy2(work / "keyart" / f"{video.get('keyart_file', name)}.json", dest / "keyart.json")
        print(name, report[name]["qc"], flush=True)
    (OUT / "promises.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    errors = [m for r in report.values() for m in r["qc"] if m.startswith("[error]")]
    return 1 if errors else 0


def main(argv: list[str]) -> int:
    mode, src_root, work = argv[0], Path(argv[1]), Path(argv[2])
    work.mkdir(parents=True, exist_ok=True)
    return {"check": check, "keyart": keyart, "render": render}[mode](src_root, work)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
