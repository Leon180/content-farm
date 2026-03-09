"""Gemini Imagen provider — AI image generation via Google GenAI SDK."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class GeminiImageProvider:
    """Generate images using Google's Imagen model via the genai SDK.

    Requires: pip install google-genai pillow
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "imagen-4.0-generate-001",
    ) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def generate_image(
        self,
        prompt: str,
        *,
        output_path: Path,
        aspect_ratio: str = "16:9",
    ) -> Path:
        """Generate an image from prompt and save to output_path.

        The genai SDK is synchronous, so we run it in an executor.
        """
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._generate_sync,
            prompt,
            output_path,
            aspect_ratio,
        )

    def _generate_sync(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str,
    ) -> Path:
        """Synchronous image generation call."""
        from google.genai import types

        output_path.parent.mkdir(parents=True, exist_ok=True)

        response = self._client.models.generate_images(
            model=self._model,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=aspect_ratio,
            ),
        )

        if not response.generated_images:
            raise RuntimeError(f"Imagen returned no images for prompt: {prompt[:80]}")

        image = response.generated_images[0].image

        # Save the PIL image
        image_path = output_path.with_suffix(".png")
        image.save(str(image_path))

        logger.info("Gemini Imagen generated: %s (%s)", image_path.name, aspect_ratio)
        return image_path
