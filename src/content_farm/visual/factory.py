"""Factory for creating visual providers from configuration."""

from __future__ import annotations

import logging

from content_farm.config import Settings
from content_farm.visual.image_protocol import ImageProvider
from content_farm.visual.protocol import StockProvider

logger = logging.getLogger(__name__)


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


def create_image_provider(settings: Settings) -> ImageProvider | None:
    """Create the AI image generation provider, or None if not configured."""
    provider = settings.image_provider
    api_key = settings.gemini_api_key.get_secret_value()

    if provider == "gemini":
        if not api_key:
            logger.info("No CF_GEMINI_API_KEY — AI image generation disabled")
            return None
        from content_farm.visual.gemini import GeminiImageProvider

        return GeminiImageProvider(
            api_key=api_key,
            model=settings.gemini_imagen_model,
        )

    logger.warning("Unknown image provider: %r — AI image generation disabled", provider)
    return None
