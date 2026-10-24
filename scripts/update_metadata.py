"""Push metadata.md's title/description/tags/categoryId to already-uploaded videos (videos.update).

DRY-RUN by default (reads the live snippet with videos.list, 1 unit, and prints the diff and the
full description that would be written). Nothing is written without --apply (videos.update, 50 units).
Only snippet.title / description / tags / categoryId are changed; every other snippet field is kept
(the live snippet is read first and overlaid), and status is never touched.

Usage:
    .venv/bin/python scripts/update_metadata.py --only fable-asymmetry-short \
        --pack-dir output/upload-20261024 [--env-file /path/.env]          # dry-run
    ... --apply                                                             # really write

Only folders with upload_result.json are considered; --only is repeatable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from content_farm.youtube.channel_tokens import resolve_refresh_token  # noqa: E402
from content_farm.youtube.pack import PackItem, load_pack  # noqa: E402
from content_farm.youtube.pack_upload import RESULT_FILENAME  # noqa: E402

FIELDS = ("title", "description", "tags", "categoryId")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--pack-dir", type=Path, default=REPO_ROOT / "output" / "upload-20261024")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    parser.add_argument("--only", action="append")
    parser.add_argument("--apply", action="store_true", help="actually call videos.update")
    return parser.parse_args(argv)


def _make_provider(refresh_token: str):
    from content_farm.youtube.google_provider import GoogleProvider

    client_id = os.environ.get("CF_YOUTUBE_CLIENT_ID", "")
    client_secret = os.environ.get("CF_YOUTUBE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise SystemExit("Set CF_YOUTUBE_CLIENT_ID and CF_YOUTUBE_CLIENT_SECRET in .env")
    return GoogleProvider(client_id, client_secret, refresh_token)


def desired_snippet(item: PackItem) -> dict:
    return {
        "title": item.title,
        "description": item.description,
        "tags": list(item.tags),
        "categoryId": item.category_id,
    }


def changed_fields(item: PackItem, live_snippet: dict) -> list[str]:
    """Fields whose value differs (tags compared order-insensitively)."""
    want = desired_snippet(item)
    out = []
    for field in FIELDS:
        a, b = want[field], live_snippet.get(field, [] if field == "tags" else None)
        if (sorted(a) != sorted(b)) if field == "tags" else (a != b):
            out.append(field)
    return out


def main(argv: list[str] | None = None, provider_factory=_make_provider) -> int:
    args = _parse_args(argv)
    load_dotenv(args.env_file)
    items = [i for i in load_pack(args.pack_dir, only=args.only) if (i.folder / RESULT_FILENAME).is_file()]
    if not items:
        print("no folders with upload_result.json")
        return 0
    print(f"mode: {'APPLY (videos.update, 50 units each)' if args.apply else 'DRY-RUN (no writes)'}\n")
    for item in items:
        video_id = json.loads((item.folder / RESULT_FILENAME).read_text(encoding="utf-8"))["videoId"]
        provider = provider_factory(resolve_refresh_token(item.channel, os.environ))
        live = provider.get_videos([video_id]).get(video_id)
        print(f"[{item.folder.name}] {video_id}")
        if live is None:
            print("  NOT FOUND via videos.list")
            return 1
        diff = changed_fields(item, live["snippet"])
        print(f"  differs: {', '.join(diff) or '(none)'}")
        if "description" in diff:
            print(f"  live description : {len(live['snippet'].get('description', ''))} chars")
            print(f"  new description  : {len(item.description)} chars / {item.description_bytes} bytes")
            print("  ----- new description (full) -----")
            print(item.description)
            print("  ----- end -----")
        if item.problems():
            print(f"  PROBLEMS, not writing: {'; '.join(item.problems())}")
            continue
        if args.apply and diff:
            provider.update_snippet(video_id, desired_snippet(item))
            print("  updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
