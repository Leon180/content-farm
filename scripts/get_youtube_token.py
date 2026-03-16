"""One-time script to obtain YouTube OAuth2 refresh token.

Usage:
    .venv/bin/python scripts/get_youtube_token.py

Opens a browser for Google login. After authorization, prints the
refresh_token to add to .env as CF_YOUTUBE_REFRESH_TOKEN.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def main() -> None:
    client_id = os.environ.get("CF_YOUTUBE_CLIENT_ID", "")
    client_secret = os.environ.get("CF_YOUTUBE_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("Error: Set CF_YOUTUBE_CLIENT_ID and CF_YOUTUBE_CLIENT_SECRET in .env")
        raise SystemExit(1)

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
    creds = flow.run_local_server(port=8091, open_browser=True)

    print("\n=== Success! ===")
    print(f"Refresh token: {creds.refresh_token}")
    print(f"\nAdd to .env:\nCF_YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
