"""Factory for creating thumbnail providers from configuration."""

from __future__ import annotations

from content_farm.config import Settings
from content_farm.thumbnail.protocol import ThumbnailProvider


def create_thumbnail_provider(settings: Settings) -> ThumbnailProvider:
    """Create the appropriate thumbnail provider based on settings."""
    provider = settings.thumbnail_provider

    if provider == "pillow":
        from content_farm.thumbnail.pillow_provider import PillowProvider

        return PillowProvider(ffmpeg_path=settings.ffmpeg_path)

    raise ValueError(
        f"Unknown thumbnail provider: {provider!r}. Supported: 'pillow'."
    )
