import sys, json
import numpy as np
from pathlib import Path
from content_farm.explainer.mascot.cues import cues_from_run
from content_farm.explainer.mascot.run import mouth_for_run, probe_video
from content_farm.explainer.pngtuber.motion import host_frames, mouth_levels
from content_farm.explainer.pngtuber.pack import load_pack

run = Path("/Users/lileon/project/content-farm/.claude/worktrees/cf-cost-accept/output/yokai-kyubi-v2")
info = probe_video(run / "assembly" / "draft.mp4")
cues = cues_from_run(run)
env = np.asarray(mouth_for_run(run, cues, info.fps, info.frames))
np.save(sys.argv[1] + "/env.npy", env)
pack = load_pack("pngtuber/frog-scribe")
fr = host_frames(cues, env, info.fps, info.frames, pack, seed=7)
print("fps", info.fps, "frames", info.frames, "depth", pack.depth is not None, "mode", pack.mouth_mode)
m = np.array([f.mouth for f in fr])
lift = np.array([f.lift for f in fr])
speaking = env > 0.06
print("speaking share", speaking.mean())
trans = np.abs(np.diff(m)) > 0
print("mouth transitions per speaking sec", trans.sum() / (speaking.sum() / info.fps))
print("mouth level share", [float((m == k).mean()) for k in range(3)])
# run lengths of mouth states while speaking
runs = []
cur, n = m[0], 1
for v in m[1:]:
    if v == cur: n += 1
    else: runs.append(n); cur, n = v, 1
runs = np.array(runs)
print("run length frames median/mean/p10", np.median(runs), runs.mean(), np.percentile(runs, 10), "1-2 frame share", (runs <= 2).mean())
dl = np.abs(np.diff(lift))
print("lift px mean/max", lift.mean(), lift.max(), "frame jump mean/p95/max", dl[speaking[1:]].mean(), np.percentile(dl, 95), dl.max())
# envelope jitter
de = np.abs(np.diff(env))
print("envelope frame delta mean/p95", de[speaking[1:]].mean(), np.percentile(de, 95))
# expression usage
from collections import Counter
print(Counter(f.expression for f in fr))
print("blinks share", np.mean([f.blink for f in fr]))
# 4s windows with most talk density
w = int(4 * info.fps)
best = sorted(range(0, info.frames - w, w), key=lambda s: -env[s:s + w].mean())[:5]
print("busiest windows start sec", [s / info.fps for s in best])
