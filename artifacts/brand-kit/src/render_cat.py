"""Render settled chipcat poses (transparent PNG) with the repo's own rig (headless, local)."""
from pathlib import Path

from content_farm.explainer.mascot.still import pose_png

OUT = Path("artifacts/brand-kit/raw")
for pose in ("idle", "smug", "wave", "shocked"):
    print(pose_png(pose, OUT / f"chipcat_{pose}.png"))
