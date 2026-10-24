"""Check that the Pexels / Pixabay keys work with one tiny search each. Prints status only — never the key.

    python scripts/check_stock_keys.py --env-file <repo>/.env
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

from content_farm.explainer.stock import PEXELS_SEARCH, PIXABAY_SEARCH, USER_AGENT


def _key(name: str, env_file: Path) -> str:
    if os.environ.get(name):
        return os.environ[name]
    if env_file.is_file():
        from dotenv import dotenv_values

        return str(dotenv_values(env_file).get(name) or "")
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args(argv)
    pexels, pixabay = _key("CF_PEXELS_API_KEY", args.env_file), _key("CF_PIXABAY_API_KEY", args.env_file)
    headers = {"User-Agent": USER_AGENT}
    failed = 0
    with httpx.Client(timeout=30, headers=headers) as http:
        checks = (
            ("pexels", pexels, lambda: http.get(PEXELS_SEARCH, params={"query": "ocean", "per_page": 1},
                                                headers={"Authorization": pexels})),
            ("pixabay", pixabay, lambda: http.get(PIXABAY_SEARCH, params={"key": pixabay, "q": "ocean", "per_page": 3})),
        )
        for name, key, call in checks:
            if not key:
                print(f"{name}: no key configured")
                failed += 1
                continue
            try:
                response = call()
            except httpx.HTTPError as exc:
                print(f"{name}: request failed ({type(exc).__name__})")
                failed += 1
                continue
            remaining = response.headers.get("x-ratelimit-remaining", "?")
            ok = response.status_code == 200
            print(f"{name}: HTTP {response.status_code} {'valid' if ok else 'INVALID'} (rate-limit remaining {remaining})")
            failed += not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
