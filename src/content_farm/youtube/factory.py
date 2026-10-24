"""Factory for creating YouTube upload providers from configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping

from content_farm.config import Settings
from content_farm.youtube.channel_tokens import resolve_refresh_token
from content_farm.youtube.protocol import YouTubeUploader


def create_youtube_uploader(
    settings: Settings,
    channel: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> YouTubeUploader:
    """Create the appropriate YouTube uploader based on settings.

    With ``channel``, the refresh token comes from
    ``CF_YOUTUBE_REFRESH_TOKEN_<CHANNEL>`` (falling back to the shared one).
    """
    provider = settings.youtube_provider

    if provider == "google":
        from content_farm.youtube.google_provider import GoogleProvider

        client_id = settings.youtube_client_id.get_secret_value()
        client_secret = settings.youtube_client_secret.get_secret_value()
        if channel:
            env = dict(os.environ if environ is None else environ)
            env.setdefault(
                "CF_YOUTUBE_REFRESH_TOKEN",
                settings.youtube_refresh_token.get_secret_value(),
            )
            refresh_token = resolve_refresh_token(channel, env)
        else:
            refresh_token = settings.youtube_refresh_token.get_secret_value()

        if not client_id:
            raise ValueError("CF_YOUTUBE_CLIENT_ID is required for Google provider")
        if not client_secret:
            raise ValueError("CF_YOUTUBE_CLIENT_SECRET is required for Google provider")
        if not refresh_token:
            raise ValueError("CF_YOUTUBE_REFRESH_TOKEN is required for Google provider")

        return GoogleProvider(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
        )

    raise ValueError(
        f"Unknown YouTube provider: {provider!r}. Supported: 'google'."
    )
