"""VoxCPM2 (OpenBMB, Apache-2.0) local voice-cloning TTS, run in its own venv."""

from __future__ import annotations

from content_farm.voice.local_clone import LocalCloneProvider


class VoxCPM2Provider(LocalCloneProvider):
    """Clones the channel's reference clip with VoxCPM2 (mlx-community 8-bit build).

    Trial 2026-10: peak ~21.7 GB system memory; known misreads go in
    channels/pronunciation.yaml."""

    kind = "voxcpm2"
    display = "VoxCPM2"
