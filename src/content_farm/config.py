"""Application configuration via environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Content Farm configuration. All settings loaded from CF_* env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CF_",
    )

    # --- LLM ---
    anthropic_api_key: SecretStr
    llm_cheap_model: str = "claude-haiku-4-5"
    llm_expensive_model: str = "claude-sonnet-4-6"

    # --- Voice ---
    tts_provider: str = "elevenlabs"  # "elevenlabs" | "fish_audio"
    elevenlabs_api_key: SecretStr = SecretStr("")
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    elevenlabs_model_id: str = "eleven_v3"
    fish_audio_api_key: SecretStr = SecretStr("")
    fish_audio_reference_id: str = ""

    # --- Visual ---
    stock_provider: str = "pexels"  # "pexels"
    pexels_api_key: SecretStr = SecretStr("")

    # --- Assembly ---
    ffmpeg_path: str = "ffmpeg"

    # --- Subtitle ---
    subtitle_provider: str = "estimation"  # "estimation"

    # --- Thumbnail ---
    thumbnail_provider: str = "pillow"  # "pillow"
    thumbnail_font_path: str = ""  # Path to CJK font file

    # --- YouTube Upload ---
    youtube_provider: str = "google"  # "google"
    youtube_client_id: SecretStr = SecretStr("")
    youtube_client_secret: SecretStr = SecretStr("")
    youtube_refresh_token: SecretStr = SecretStr("")

    # --- Cache ---
    cache_backend: str = "file"  # "file" | "redis"
    cache_dir: Path = Path(".cache/llm")
    redis_url: str = "redis://localhost:6379/0"

    # --- Content ---
    default_language: str = "zh-TW"  # zh-TW | en | ja | ko | etc.

    # --- Pipeline ---
    max_concurrent_scenes: int = Field(default=5, ge=1, le=20)
    log_level: str = "INFO"
