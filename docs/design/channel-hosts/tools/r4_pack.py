"""Round 4: build the 3D-look packs (<id>-3d) with 2.5D motion from r4_gen.py output.

    PYTHONPATH=src python docs/design/channel-hosts/tools/r4_pack.py <r4_raw_dir> [--mouths path.json]

For each pick: build_pack → mouth mode (C09 / O25 small 'o', centre measured on the 3D base; pass
--mouths to override) → manifest motion "2.5d" → depth.png from scripts/host_depth_worker.py run
in the mlx-video venv (CF_MLX_VIDEO_HOME, default ~/.local/share/mlx-video). Waits on the same gate
as image generation (the depth model is small, but the machine is shared). Review sheets go to
docs/design/channel-hosts/round4/.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from r2_gen import wait_until_idle  # noqa: E402
from r3_pack import SOURCE, sheet  # noqa: E402

from content_farm.explainer.pngtuber.build import (  # noqa: E402
    apply_mouth_mode, build_pack, erase_mouth, set_manifest)
from content_farm.explainer.pngtuber.pack import PACK_ROOT  # noqa: E402

ROOT = HERE.parents[3]
OUT = HERE.parent / "round4"
PACKS = {"Y14": ("frog-scribe-3d", "青蛙書記（3D）", "#14110d"),
         "O25": ("cooler-goldfish-3d", "飲水機金魚（3D）", "#ffd84d"),
         "C09": ("paint-bottle-3d", "顏料瓶老師傅（3D）", "#f5f1e8")}
MLX_HOME = Path(os.environ.get("CF_MLX_VIDEO_HOME", Path.home() / ".local/share/mlx-video"))
# measured on each 3D base.png (canvas px); same decisions as the flat packs (r3_pack.py)
ERASE_MOUTH = {"cooler-goldfish-3d": [((397, 433), (60, 38)), ((393, 458), (50, 52)), ((381, 447), (128, 42)),
                                      ((390, 460), (58, 32))]}
SPEECH_FX = {"cooler-goldfish-3d": {"kind": "bubbles", "emit": [395, 445], "surface_y": 288, "x_range": [255, 515]}}
SMALL_O = {"paint-bottle-3d": {"center": (388, 378), "cover": (52, 24), "o_sizes": ((13, 14), (17, 20))}}


def depth(folder: Path) -> dict:
    wait_until_idle()
    proc = subprocess.run([str(MLX_HOME / "venv/bin/python"), str(ROOT / "scripts/host_depth_worker.py"),
                           "--pack-dir", str(folder), "--depth-model", str(MLX_HOME / "models/depth-anything-v2-small-hf")],
                          capture_output=True, text=True, env={**os.environ, "HF_HUB_OFFLINE": "1"})
    if proc.returncode != 0:
        raise RuntimeError(f"depth worker failed for {folder.name}: {proc.stderr[-600:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def main(argv: list[str]) -> int:
    raw = Path(argv[0])
    mouths = json.loads(Path(argv[argv.index("--mouths") + 1]).read_text()) if "--mouths" in argv else {}
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    for pick, (pack_id, name, bg) in PACKS.items():
        folder = PACK_ROOT / pack_id
        built = build_pack(raw / pick, folder, pack_id, name, cut_thresh=100,   # drops the painted ground shadow
                           source={**SOURCE, "round2_id": pick, "style": "3D re-render (klein edit)"})
        small_o = {**SMALL_O, **mouths}
        if pack_id in small_o:
            m = small_o[pack_id]
            apply_mouth_mode(folder, "small_o", center=tuple(m["center"]), cover=tuple(m["cover"]),
                             o_sizes=tuple(tuple(s) for s in m["o_sizes"]))
        if pack_id in ERASE_MOUTH:
            print(pack_id, "mouth erased:", erase_mouth(folder, ERASE_MOUTH[pack_id]), flush=True)
        if pack_id in SPEECH_FX:
            set_manifest(folder, speech_fx=SPEECH_FX[pack_id])
        set_manifest(folder, motion="2.5d")
        report[pack_id] = {"pick": pick, "regions": built.regions, "silhouette_iou": built.iou, "depth": depth(folder),
                           "sheet": sheet(pick, raw, pack_id, bg, OUT).name}
        print(pack_id, report[pack_id], flush=True)
    (OUT / "packs.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
