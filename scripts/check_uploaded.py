"""Read back uploaded videos (videos.list, read-only, 1 quota unit per channel) and compare
tags, categoryId, defaultLanguage, madeForKids / selfDeclaredMadeForKids, containsSyntheticMedia
(plus title, description, privacyStatus) with the pack's metadata.md.

Usage:
    .venv/bin/python scripts/check_uploaded.py --pack-dir output/upload-20261024 \
        [--env-file /path/to/.env] [--only <folder> ...]

Only folders that have upload_result.json are checked. Exit code 1 if any field differs.
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
from content_farm.youtube.pack import load_pack  # noqa: E402
from content_farm.youtube.pack_upload import RESULT_FILENAME  # noqa: E402
from content_farm.youtube.verify import compare_video  # noqa: E402


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--pack-dir", type=Path, default=REPO_ROOT / "output" / "upload-20261024")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    parser.add_argument("--only", action="append")
    parser.add_argument("--include-unlisted", action="store_true")
    return parser.parse_args(argv)


def _make_provider(refresh_token: str):
    from content_farm.youtube.google_provider import GoogleProvider

    client_id = os.environ.get("CF_YOUTUBE_CLIENT_ID", "")
    client_secret = os.environ.get("CF_YOUTUBE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise SystemExit("Set CF_YOUTUBE_CLIENT_ID and CF_YOUTUBE_CLIENT_SECRET in .env")
    return GoogleProvider(client_id, client_secret, refresh_token)


def main(argv: list[str] | None = None, provider_factory=_make_provider) -> int:
    args = _parse_args(argv)
    load_dotenv(args.env_file)
    items = [
        i for i in load_pack(args.pack_dir, only=args.only, include_unlisted=args.include_unlisted)
        if (i.folder / RESULT_FILENAME).is_file()
    ]
    if not items:
        print("no folders with upload_result.json")
        return 0

    mismatches = 0
    for item in items:
        result = json.loads((item.folder / RESULT_FILENAME).read_text(encoding="utf-8"))
        video_id = result["videoId"]
        provider = provider_factory(resolve_refresh_token(item.channel, os.environ))
        video = provider.get_videos([video_id]).get(video_id)
        print(f"[{item.folder.name}] {video_id}  channel={item.channel}")
        if video is None:
            print("  NOT FOUND via videos.list")
            mismatches += 1
            continue
        for check in compare_video(item, video):
            mark = "OK  " if check.ok else "DIFF"
            line = f"  {mark} {check.field}"
            if not check.ok:
                line += f": expected {check.expected!r}, got {check.actual!r}"
                mismatches += 1
            print(line)
    print(f"\n{len(items)} video(s) checked, {mismatches} field difference(s)")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
