"""Round 4: 3D-look versions of the three hosts with klein reference edits.

    PYTHONPATH=src python docs/design/channel-hosts/tools/r4_gen.py <r3_raw_dir> <out_dir>

1. base: the flat base re-rendered as a soft vinyl / clay 3D figure. The style change moves the
   outline a little (shading, rim light), so it is accepted at IoU >= 0.97 against the flat base.
2. states: the same six edits as round 3, made from the 3D base, accepted at IoU >= 0.99.
No IP, character or studio names in any prompt (r2_prompts.check_prompts runs on them).
Gate: r2_gen.wait_until_idle (no ffmpeg / mflux / mlx_video / local TTS, free memory >= 25 %).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from r2_prompts import banned_terms  # noqa: E402
from r3_gen import STATES, accepted_edit  # noqa: E402

PICKS = ("Y14", "O25", "C09")
STYLE_IOU_MIN = 0.97
STYLE_3D = ("Re-render this exact character as a small 3D figure, like a soft vinyl toy or smooth clay sculpture: "
            "soft studio lighting from the upper left, gentle rounded shading, soft ambient occlusion in the creases, "
            "a subtle cool rim light along the edges, slightly glossy surface. Keep the same pose, same proportions, "
            "same colours, same face and features, same props, same position and size in the frame. "
            "Plain pure white background, no ground shadow, no text.")


def main(argv: list[str]) -> int:
    r3_raw, out_dir = Path(argv[0]), Path(argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    prompts = [STYLE_3D, *STATES.values()]
    bad = [p for p in prompts if banned_terms(p)]
    if bad:
        raise ValueError(f"banned terms in prompts: {bad}")
    log, summary = out_dir / "r4_runs.jsonl", []
    for pick in PICKS:
        work = out_dir / pick
        work.mkdir(parents=True, exist_ok=True)
        summary.append(accepted_edit(r3_raw / pick / "base.png", STYLE_3D, work / "base.png", log,
                                     {"pick": pick, "state": "base3d"}, iou_min=STYLE_IOU_MIN))
        for state, prompt in STATES.items():
            summary.append(accepted_edit(work / "base.png", prompt, work / f"{state}.png", log,
                                         {"pick": pick, "state": state}))
        (out_dir / "r4_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    failed = [s for s in summary if s.get("passed") is False]
    print("failed:", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
