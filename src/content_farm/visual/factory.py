"""Factory for creating visual providers from configuration."""

from __future__ import annotations

from content_farm.config import Settings
from content_farm.visual.protocol import StockProvider


def create_stock_provider(settings: Settings) -> StockProvider:
    """Create the appropriate stock provider based on settings."""
    provider = settings.stock_provider

    if provider == "pexels":
        from content_farm.visual.pexels import PexelsProvider

        api_key = settings.pexels_api_key.get_secret_value()
        if not api_key:
            raise ValueError("CF_PEXELS_API_KEY is required for Pexels provider")
        return PexelsProvider(api_key=api_key)

    raise ValueError(f"Unknown stock provider: {provider!r}. Use 'pexels'.")
