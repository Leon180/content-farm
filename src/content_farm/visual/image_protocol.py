"""Image generation provider protocol — abstraction for AI image generators."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ImageProvider(Protocol):
    """Interface for AI image generation providers (Gemini Imagen, DALL-E, etc.)."""

    async def generate_image(
        self,
        prompt: str,
        *,
        output_path: Path,
        aspect_ratio: str = "16:9",
    ) -> Path:
        """Generate an image from a text prompt and save it.

        Returns the path to the saved image file.
        Raises RuntimeError if generation fails.
        """
        ...
