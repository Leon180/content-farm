"""Factory for creating subtitle providers from configuration."""

from __future__ import annotations

from content_farm.config import Settings
from content_farm.subtitle.protocol import SubtitleProvider


def create_subtitle_provider(settings: Settings) -> SubtitleProvider:
    """Create the appropriate subtitle provider based on settings."""
    provider = settings.subtitle_provider

    if provider == "estimation":
        from content_farm.subtitle.estimation import EstimationProvider

        return EstimationProvider()

    raise ValueError(
        f"Unknown subtitle provider: {provider!r}. Supported: 'estimation'."
    )
