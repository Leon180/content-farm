"""Build the 3 thumbnail options for a fable run: add ``thumb`` to a copy of fable.json, draw, render, QC.

    PYTHONPATH=src python artifacts/thumbnail-v2/src/make_options.py \
        --source-fable <cf-fable>/output/fable-ess-mid/fable.json --run-dir <scratch dir> --env-file <.env> [--no-draw]

Drawing uses the local mflux model (free, one picture at a time, ~1 min each). The source run is only read.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from content_farm.production.channels import load_channel
from content_farm.production.fable import check, model, thumb

OPTIONS = [
    {"hook": "誰會贏？", "layout": "bottom",
     "image_prompt": "extreme close-up of two small round songbirds facing off on a branch, the left one lunging forward "
                     "with wings spread wide and beak open, the right one leaning back and stepping away, "
                     "a single red berry between them, simple warm cream background"},
    {"hook": "打還是讓？", "layout": "left",
     "image_prompt": "close-up of two small round songbirds nose to nose on a mossy branch on the right side of the frame, "
                     "one puffed up with fierce eyebrows and half-open wings, the other shrinking back with wide worried eyes, "
                     "plain soft sage green background with empty space on the left"},
    {"hook": "為什麼沒人贏", "layout": "bottom",
     "image_prompt": "dramatic close-up of two small round songbirds clashing in a burst of flying feathers over one red berry, "
                     "both with wings flared and equal strength, neither giving way, simple warm golden background"},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-fable", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--no-draw", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.source_fable.read_text(encoding="utf-8"))
    data["thumb"] = OPTIONS
    args.run_dir.mkdir(parents=True, exist_ok=True)
    (args.run_dir / "fable.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    fable = model.load(args.run_dir)
    problems = check.thumb_problems(fable)
    print("thumb problems:", problems or "none")
    if problems:
        return 1
    channel = load_channel("fable")
    if not args.no_draw:
        print("drawn now:", thumb.draw_thumb_images(args.run_dir, fable, channel, env_file=args.env_file))
    print({key: str(path) for key, path in thumb.render_options(args.run_dir, fable, channel).items()})
    for finding in thumb.thumb_findings(args.run_dir, fable, channel):
        print(f"[{finding.level}] {finding.check}: {finding.message}")
    shutil.copy(args.run_dir / "fable.json", args.run_dir / "fable.thumb.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
