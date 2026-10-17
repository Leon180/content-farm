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
    # "fish_audio" | "elevenlabs" | "macos_say"
    # macos_say: free local macOS `say` voice, for development/testing only — do not publish with it.
    tts_provider: str = "fish_audio"
    # Per-run voice override (the production runner sets it from channels/<code>.yaml
    # voice.voice_id_env). Empty = the provider's own default below.
    tts_voice_id: str = ""
    elevenlabs_api_key: SecretStr = SecretStr("")
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    elevenlabs_model_id: str = "eleven_v3"
    fish_audio_api_key: SecretStr = SecretStr("")
    fish_audio_reference_id: str = ""
    # Fish TTS model (sent as the `model` header). Original-voice auditions were made with
    # s2.1-pro; audio from before this setting used the SDK default (see voice.generator).
    fish_audio_model: str = "s2.1-pro"
    macos_say_voice: str = "Flo (Chinese (Taiwan))"  # list installed voices: say -v '?'
    macos_say_rate: int | None = Field(default=None, gt=0)  # words per minute (say -r); None = voice default

    # Local voice-cloning TTS ("voxcpm2" | "qwen3_tts", both Apache-2.0). They run in their own
    # venv through scripts/local_tts_worker.py; the repo .venv never imports mlx. Models are
    # read from the Hugging Face hub caches below, offline (nothing is downloaded).
    local_tts_python: str = "~/.local/share/qwen3-tts/.venv/bin/python"
    voxcpm2_hub_dir: str = "~/.local/share/voxcpm2/hf/hub"
    voxcpm2_model: str = "mlx-community/VoxCPM2-8bit"
    qwen3_tts_hub_dir: str = "~/.local/share/qwen3-tts/hf/hub"
    qwen3_tts_model: str = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
    # Reference clip + its transcript for cloning; the runner sets them from the channel yaml.
    tts_ref_audio: str = ""
    tts_ref_text: str = ""
    tts_seed: int = 1
    # Resource gate before a local model loads: wait while these run or free memory is low.
    local_tts_busy_pattern: str = "mlx_video|mflux|ffmpeg"
    local_tts_min_free_pct: int = Field(default=25, ge=0, le=100)
    local_tts_max_wait_s: int = Field(default=1800, ge=0)
    local_tts_lock_path: str = "~/.cache/content-farm/local_tts.lock"

    # Read-back check: whisper transcribes each synthesized scene; above the threshold (or a
    # key term missing) the scene is re-generated with another seed, up to the retry limit.
    speech_check: bool = False
    speech_check_max_cer: float = Field(default=0.12, ge=0, le=1)
    speech_check_retries: int = Field(default=3, ge=0, le=10)
    asr_hub_dir: str = "~/.local/share/qwen3-tts/hf/hub"
    asr_model: str = "mlx-community/whisper-large-v3-turbo-asr-fp16"
    # Shared pronunciation table (TTS text only; subtitles keep the script's wording).
    pronunciation_file: str = ""
    channel_code: str = ""

    # --- Visual ---
    stock_provider: str = "pexels"  # "pexels" | "pixabay" | "multi"
    pexels_api_key: SecretStr = SecretStr("")
    pixabay_api_key: SecretStr = SecretStr("")
    image_provider: str = "gemini"  # "gemini" (for AI-generated images)
    gemini_api_key: SecretStr = SecretStr("")
    gemini_imagen_model: str = "imagen-4.0-generate-001"

    # --- Assembly ---
    ffmpeg_path: str = "ffmpeg"

    # --- Visual Generation (browser-automated Nano Banana) ---
    gemini_browser_user_data_dir: str = ".cache/playwright_gemini"
    gemini_browser_delay_s: float = 5.0
    gemini_browser_generation_timeout_s: float = 180.0
    gemini_browser_headless: bool = False
    gemini_browser_use_system_chrome: bool = False

    # --- Subtitle ---
    subtitle_provider: str = "whisper"  # "whisper" (default, accurate) | "estimation" (fallback)
    subtitle_max_chars_per_line: int = 13  # zh-TW portrait 1080x1920 @ 78pt
    # Landscape 1920x1080 @ 52pt (explainer / long-form). Portrait keeps the value above.
    subtitle_max_chars_per_line_landscape: int = Field(default=24, ge=8, le=40)
    whisper_model_size: str = "base"  # tiny | base | small | medium | large-v3
    whisper_language: str = "zh"
    whisper_device: str = "cpu"  # "cpu" | "cuda" | "auto"
    whisper_compute_type: str = "int8"  # int8 | float16 | float32

    # --- Thumbnail ---
    thumbnail_provider: str = "pillow"  # "pillow"
    thumbnail_font_path: str = ""  # Path to CJK font file

    # --- YouTube Upload ---
    youtube_provider: str = "google"  # "google"
    youtube_client_id: SecretStr = SecretStr("")
    youtube_client_secret: SecretStr = SecretStr("")
    youtube_refresh_token: SecretStr = SecretStr("")

    # --- Telegram ---
    telegram_bot_token: SecretStr = SecretStr("")  # from @BotFather
    telegram_chat_id: str = ""  # your chat ID (from @userinfobot)

    # --- Cache ---
    cache_backend: str = "file"  # "file" | "redis"
    cache_dir: Path = Path(".cache/llm")
    redis_url: str = "redis://localhost:6379/0"

    # --- Content ---
    default_language: str = "zh-TW"  # zh-TW | en | ja | ko | etc.

    # --- Google Drive ---
    drive_credentials_path: str = ""  # Path to service account JSON
    drive_folder_id: str = ""  # Shared Drive folder ID

    # --- Pipeline ---
    pipeline_mode: str = "materials"  # "materials" | "full"
    output_dir: str = "output"
    max_concurrent_scenes: int = Field(default=5, ge=1, le=20)
    log_level: str = "INFO"

    # --- Daemon ---
    project_root: Path = Path(".")  # Base path for security/ and other relative dirs
