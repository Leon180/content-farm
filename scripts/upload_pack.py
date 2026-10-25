"""Upload an upload pack (INDEX.md + per-video metadata.md) to YouTube — always PRIVATE.

Usage:
    .venv/bin/python scripts/upload_pack.py --dry-run                 # print plan, no API calls
    .venv/bin/python scripts/upload_pack.py --only chipcat-cowos-v4   # one folder
    .venv/bin/python scripts/upload_pack.py --limit 2                 # first N rows of INDEX
    .venv/bin/python scripts/upload_pack.py                           # real upload (videos.insert)

Options:
    --only NAME           repeatable: --only a --only b
    --env-file PATH       default <repo>/.env (point at the main checkout's .env from a worktree)
    --pack-dir DIR        default output/upload-20261024
    --include-unlisted    also plan folders that have metadata.md but are not in INDEX.md
    --force               re-upload folders that already have upload_result.json
    --quota-file PATH     local ledger (default .cache/youtube_quota.json)

Quota: videos.insert 1600 units, thumbnails.set 50, channels.list 1 (token/channel check).
The API reports no usage, so a local ledger (Pacific-day) tracks it; the daily limit comes
from CF_YOUTUBE_DAILY_QUOTA (default 10000). Stops before the first video that doesn't fit.

Token per channel: CF_YOUTUBE_REFRESH_TOKEN_<CHANNEL>, else CF_YOUTUBE_REFRESH_TOKEN.
Pinned comments (pinned-comment.txt) are only reminded, never posted.
Success writes <folder>/upload_result.json (videoId, Studio link).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from content_farm.youtube.pack import load_pack  # noqa: E402
from content_farm.youtube.pack_upload import (  # noqa: E402
    describe_item,
    run_upload,
    summarize_quota,
)
from content_farm.youtube.quota import DEFAULT_DAILY_LIMIT, QuotaLedger, pacific_day  # noqa: E402

DEFAULT_PACK = REPO_ROOT / "output" / "upload-20261024"
DEFAULT_LEDGER = REPO_ROOT / ".cache" / "youtube_quota.json"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--pack-dir", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", action="append", help="folder name inside the pack (repeatable)")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--include-unlisted", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--quota-file", type=Path, default=DEFAULT_LEDGER)
    return parser.parse_args(argv)


def _make_provider(channel: str, refresh_token: str):
    from content_farm.youtube.google_provider import GoogleProvider

    client_id = os.environ.get("CF_YOUTUBE_CLIENT_ID", "")
    client_secret = os.environ.get("CF_YOUTUBE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise SystemExit("Set CF_YOUTUBE_CLIENT_ID and CF_YOUTUBE_CLIENT_SECRET in .env")
    return GoogleProvider(client_id, client_secret, refresh_token)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    load_dotenv(args.env_file)
    items = load_pack(
        args.pack_dir, only=args.only, limit=args.limit, include_unlisted=args.include_unlisted
    )
    limit = int(os.environ.get("CF_YOUTUBE_DAILY_QUOTA", DEFAULT_DAILY_LIMIT))
    ledger = QuotaLedger.load(args.quota_file, limit=limit)

    print(f"pack: {args.pack_dir}  ({len(items)} videos)  mode: "
          f"{'DRY-RUN' if args.dry_run else 'UPLOAD (private)'}\n")
    for item in items:
        print(describe_item(item, os.environ), end="\n\n")
    print(summarize_quota(items, ledger, pacific_day()))

    if args.dry_run:
        return 0
    outcomes = asyncio.run(
        run_upload(
            items,
            environ=os.environ,
            ledger=ledger,
            provider_factory=_make_provider,
            force=args.force,
        )
    )
    failed = [o for o in outcomes if o.status == "failed"]
    stopped = [o for o in outcomes if o.status == "stopped-quota"]
    if stopped:
        print(f"\n{len(stopped)} video(s) not uploaded (quota) — rerun after the Pacific-midnight reset.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
