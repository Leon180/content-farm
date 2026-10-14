"""Factory for creating subtitle providers from configuration."""

from __future__ import annotations

from content_farm.config import Settings
from content_farm.subtitle.protocol import SubtitleProvider
from content_farm.types import Orientation


def max_chars_per_line_for(settings: Settings, orientation: Orientation | None) -> int:
    """Per-line subtitle width for ``orientation``.

    Anything other than an explicit LANDSCAPE (including ``None``, i.e. scripts
    written before the orientation field existed) keeps the portrait/Shorts value,
    so the default workflow is unaffected.
    """
    if orientation == Orientation.LANDSCAPE:
        return settings.subtitle_max_chars_per_line_landscape
    return settings.subtitle_max_chars_per_line


def create_subtitle_provider(
    settings: Settings,
    orientation: Orientation | None = None,
) -> SubtitleProvider:
    """Create the appropriate subtitle provider based on settings."""
    provider = settings.subtitle_provider

    wrap = max_chars_per_line_for(settings, orientation)

    if provider == "estimation":
        from content_farm.subtitle.estimation import EstimationProvider

        return EstimationProvider(wrap_chars_per_line=wrap)

    if provider == "whisper":
        from content_farm.subtitle.whisper_alignment import WhisperAlignmentProvider

        return WhisperAlignmentProvider(
            model_size=settings.whisper_model_size,
            language=settings.whisper_language,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            wrap_chars_per_line=wrap,
        )

    raise ValueError(
        f"Unknown subtitle provider: {provider!r}. Supported: 'estimation', 'whisper'."
    )
