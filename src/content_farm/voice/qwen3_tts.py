"""Qwen3-TTS Base (Alibaba Qwen, Apache-2.0) local voice-cloning TTS, run in its own venv."""

from __future__ import annotations

from content_farm.voice.local_clone import LocalCloneProvider


class Qwen3TTSProvider(LocalCloneProvider):
    """Clones the channel's reference clip with Qwen3-TTS 12Hz 1.7B Base (bf16).

    Trial 2026-10 (local README): peak ~24.5 GB system memory; known misreads go in
    channels/pronunciation.yaml."""

    kind = "qwen3_tts"
    display = "Qwen3-TTS"
