"""Round 4 trials: flat pack vs 3D-look pack with 2.5D motion, side by side, 20 s each.

    PYTHONPATH=src python docs/design/channel-hosts/tools/r4_trial.py <r3_trials_dir> <out_dir>

Uses the round-3 trial run dirs (r3_trial.py): yokai/ and cel/ link the launch-fixes runs read-only;
short_pipeline/assembly/draft.mp4 is the 7,722 Short rendered with an empty cat slot. Each variant is
rendered over the same draft, checked frame by frame against the forbidden rects, then the two are
scaled to half size and stacked left/right with a label (1920x540, or 1080x960 for 9:16).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from r3_trial import forbidden_pixels, stills  # noqa: E402

from content_farm.assembly.drawtext import find_cjk_font  # noqa: E402
from content_farm.explainer.mascot.cues import SceneCue  # noqa: E402
from content_farm.explainer.pngtuber.run import run_host_overlay  # noqa: E402
from content_farm.production import shorts_cut as cut  # noqa: E402
from content_farm.script_gen.schemas import Script  # noqa: E402

OUT = HERE.parent / "round4"
SECONDS = 20.0
TRIALS = {  # name: (run dir under r3 trials, flat pack, 3d pack)
    "yokai": ("yokai", "pngtuber/frog-scribe", "pngtuber/frog-scribe-3d"),
    "cel": ("cel", "pngtuber/paint-bottle", "pngtuber/paint-bottle-3d"),
    "offwork": ("short_pipeline", "pngtuber/cooler-goldfish", "pngtuber/cooler-goldfish-3d"),
}
LABELS = ("平面版", "3D 質感＋2.5D")


def short_cues(run_dir: Path) -> tuple[SceneCue, ...]:
    spec = cut.load_spec(run_dir)
    script = Script.model_validate_json((run_dir / "script.json").read_text(encoding="utf-8"))
    seconds = [scene.duration_seconds for scene in script.scenes]
    starts = [sum(seconds[:i]) for i in range(len(seconds) + 1)]
    return tuple(SceneCue(index=i, start=starts[i - 1], end=starts[i], pose=beat.pose)
                 for i, beat in enumerate(spec.beats, start=1))


def side_by_side(left: Path, right: Path, out: Path, vertical: bool) -> None:
    w, h = (540, 960) if vertical else (960, 540)
    font = find_cjk_font()
    size = 34 if vertical else 30

    def label(i: int, text: str) -> str:
        return (f"[{i}:v]scale={w}:{h},drawtext=fontfile='{font}':text='{text}':x=20:y=20:fontsize={size}:"
                f"fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=10[v{i}]")

    graph = f"{label(0, LABELS[0])};{label(1, LABELS[1])};[v0][v1]hstack=inputs=2[v]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(left), "-i", str(right), "-filter_complex", graph,
                    "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-t", f"{SECONDS:.2f}", "-movflags", "+faststart", str(out)], check=True)


def trial(name: str, run_dir: Path, flat: str, deep: str, out_dir: Path) -> dict:
    cues = short_cues(run_dir) if name == "offwork" else None
    result: dict = {"run_dir": str(run_dir)}
    finals = []
    for tag, ref in (("flat", flat), ("3d", deep)):
        final = run_dir / "assembly" / f"r4_{tag}.mp4"
        res = run_host_overlay(run_dir, ref, seconds=SECONDS, out=final, cues=cues)
        result[tag] = {"pack": ref, "frames": res.render.frames, "faces": res.render.faces,
                       "render_seconds": res.render.seconds,
                       "forbidden": forbidden_pixels(res.alpha_video, (res.info.width, res.info.height))}
        finals.append(final)
    out = out_dir / f"compare_{name}_20s.mp4"
    side_by_side(finals[0], finals[1], out, vertical=name == "offwork")
    result["compare"] = str(out)
    result["stills"] = stills(out, f"compare_{name}", (3.0, 9.0, 15.0))
    return result


def main(argv: list[str]) -> int:
    trials_dir, out_dir = Path(argv[0]), Path(argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    import r3_trial
    r3_trial.OUT = OUT          # stills land in round4/
    report = {name: trial(name, trials_dir / run, flat, deep, out_dir) for name, (run, flat, deep) in TRIALS.items()}
    (OUT / "trials.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    bad = [n for n, r in report.items() for tag in ("flat", "3d")
           if any(v for k, v in r[tag]["forbidden"].items() if k != "frames_checked")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
