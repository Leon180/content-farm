"""Factory for creating visual providers from configuration."""

from __future__ import annotations

import logging

from content_farm.config import Settings
from content_farm.visual.image_protocol import ImageProvider
from content_farm.visual.protocol import StockProvider

logger = logging.getLogger(__name__)


def create_stock_provider(settings: Settings) -> StockProvider:
    """Create the appropriate stock provider based on settings.

    When both Pexels and Pixabay API keys are set, returns a
    MultiStockProvider that tries Pexels first, then Pixabay.
    """
    pexels_key = settings.pexels_api_key.get_secret_value()
    pixabay_key = settings.pixabay_api_key.get_secret_value()

    providers: list = []
    names: list[str] = []

    if pexels_key:
        from content_farm.visual.pexels import PexelsProvider

        providers.append(PexelsProvider(api_key=pexels_key))
        names.append("pexels")

    if pixabay_key:
        from content_farm.visual.pixabay import PixabayProvider

        providers.append(PixabayProvider(api_key=pixabay_key))
        names.append("pixabay")

    if not providers:
        raise ValueError(
            "At least one stock video API key is required "
            "(CF_PEXELS_API_KEY or CF_PIXABAY_API_KEY)"
        )

    if len(providers) == 1:
        return providers[0]

    from content_farm.visual.multi_provider import MultiStockProvider

    return MultiStockProvider(
        providers=tuple(providers), provider_names=tuple(names),
    )


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
