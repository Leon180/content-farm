"""Check a 冷笑話小劇場 run's script.json (shorts_skit pipeline).

Usage:
    python scripts/check_skit.py --run-dir output/<run>

Checks (``content_farm.production.skit``): valid script.json; scenes titled 鋪陳 / 笑點 / 收尾 in that order;
the last 鋪陳 carries transition ``pause:0.6``; one short 笑點; goldfish expression per scene; 20–50 s;
no trendy words; AI disclosure on. No network.

Exit codes: 0 ok, 1 problems found (all listed), 2 missing or unreadable script.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from content_farm.production.skit import estimated_seconds, skit_problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    path = args.run_dir / "script.json"
    if not path.is_file():
        print(f"missing {path}", file=sys.stderr)
        return 2
    try:
        script = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"{path} is not JSON: {exc}", file=sys.stderr)
        return 2
    problems = skit_problems(script)
    for problem in problems:
        print(f"- {problem}")
    print(f"{len(problems)} problem(s); estimated {estimated_seconds(script):g} s")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
