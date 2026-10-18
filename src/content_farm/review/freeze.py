"""Steps a run must not redo (``production.frozen.json`` in the run-dir).

Example: a published-article fix pass where the article stage is settled and only the script may
change — ``{"steps": ["article"], "why": "..."}``. Panel issues caused by a frozen step are routed
to the next step that is not frozen (for the article: the script, which may add sources to
sources.json or cut the claim), and the runner never re-runs a frozen step for rework.
"""

from __future__ import annotations

import json
from pathlib import Path

FROZEN_FILE = "production.frozen.json"


def frozen_steps(run_dir: Path) -> frozenset[str]:
    path = run_dir / FROZEN_FILE
    if not path.is_file():
        return frozenset()
    data = json.loads(path.read_text(encoding="utf-8"))
    steps = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
        raise ValueError(f"{path}: expected {{\"steps\": [\"<step>\", ...]}}")
    return frozenset(steps)
