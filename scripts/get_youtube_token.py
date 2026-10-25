"""Obtain a YouTube OAuth2 refresh token for ONE brand channel and store it in .env.

Usage (one run per channel; technews = 晚點你就知道 and may stay on the default CF_YOUTUBE_REFRESH_TOKEN):
    .venv/bin/python scripts/get_youtube_token.py --channel chipcat
    .venv/bin/python scripts/get_youtube_token.py --channel cel
    .venv/bin/python scripts/get_youtube_token.py --channel yokai
    .venv/bin/python scripts/get_youtube_token.py --channel deepsea
    .venv/bin/python scripts/get_youtube_token.py --channel fable

Flow: opens a browser (pick the brand channel on Google's account chooser) ->
calls channels.list mine=true and prints "已授權頻道：<name>" for you to verify ->
asks to confirm -> appends CF_YOUTUBE_REFRESH_TOKEN_<CHANNEL>=... to .env.
The token itself is never printed.

If that variable already exists the script refuses before opening the browser;
pass --replace to overwrite it. Use --yes to skip the confirmation prompt and
--env-file to target a different file (default: <repo>/.env).
Requires CF_YOUTUBE_CLIENT_ID / CF_YOUTUBE_CLIENT_SECRET already in .env.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from content_farm.youtube.channel_tokens import (  # noqa: E402
    CHANNELS,
    CHANNEL_ALIASES,
    normalize_channel,
    token_env_name,
)
from content_farm.youtube.env_file import env_var_exists, set_env_var  # noqa: E402

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--channel", required=True, choices=[*CHANNELS, *CHANNEL_ALIASES])
    parser.add_argument("--replace", action="store_true", help="overwrite an existing token")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    return parser.parse_args(argv)


def _authorize(client_id: str, client_secret: str) -> str:
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        },
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(
        port=8091, open_browser=True, access_type="offline", prompt="consent"
    )
    if not creds.refresh_token:
        raise SystemExit("Google returned no refresh token; revoke the app's access and retry.")
    return creds.refresh_token


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    load_dotenv(args.env_file)
    channel = normalize_channel(args.channel)
    var_name = token_env_name(channel)

    if env_var_exists(args.env_file, var_name) and not args.replace:
        print(f"{var_name} already exists in {args.env_file}. Re-run with --replace to overwrite.")
        return 1

    client_id = os.environ.get("CF_YOUTUBE_CLIENT_ID", "")
    client_secret = os.environ.get("CF_YOUTUBE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("Error: set CF_YOUTUBE_CLIENT_ID and CF_YOUTUBE_CLIENT_SECRET in .env")
        return 1

    refresh_token = _authorize(client_id, client_secret)

    from content_farm.youtube.google_provider import GoogleProvider

    info = GoogleProvider(client_id, client_secret, refresh_token).get_authorized_channel()
    print(f"已授權頻道：{info['title']}  (id {info['id']})")

    if not args.yes and input(f"這是「{channel}」要用的頻道嗎？寫入 {var_name}？[y/N] ").strip().lower() != "y":
        print("Aborted; nothing written.")
        return 1

    outcome = set_env_var(args.env_file, var_name, refresh_token, replace=args.replace)
    print(f"{outcome} {var_name} in {args.env_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
