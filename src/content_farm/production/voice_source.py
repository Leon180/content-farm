"""Which TTS provider voiced a run, read from ``logs/voice.log``.

Used by the AI disclosure (publish) and the manual-upload kit's machine-voice
banner. The answer is the last provider that actually synthesized: a re-run
that only logs "Reusing existing audio" keeps whatever voice was there before.
A Short cut from a long run (``short_source.json``) has no voice step of its
own, so it is answered from the long run.
"""

from __future__ import annotations

import re
from pathlib import Path

from content_farm.production import shorts_cut

MACHINE_PROVIDER = "macos_say"
PROVIDER_NAMES = {"macos_say": "macOS say", "fish_audio": "Fish Audio", "elevenlabs": "ElevenLabs"}

_TTS_LINE = re.compile(r"content_farm\.voice\.(?!generator\b)(\w+) INFO .*TTS", re.IGNORECASE)


def voice_run_dir(run_dir: Path) -> Path:
    """The run whose voice step produced this run's narration."""
    return Path(shorts_cut.load_spec(run_dir).long_run_dir) if shorts_cut.is_short_cut(run_dir) else run_dir


def last_tts_provider(run_dir: Path) -> str | None:
    """Module name of the last provider that synthesized audio, or None when the log shows none."""
    log = voice_run_dir(run_dir) / "logs" / "voice.log"
    if not log.is_file():
        return None
    providers = _TTS_LINE.findall(log.read_text(encoding="utf-8", errors="replace"))
    return providers[-1] if providers else None


def uses_machine_voice(run_dir: Path) -> bool:
    return last_tts_provider(run_dir) == MACHINE_PROVIDER


def provider_name(provider: str | None) -> str:
    if provider is None:
        return "未知（找不到 TTS 紀錄）"
    return PROVIDER_NAMES.get(provider, provider)
