"""Which TTS voice a run's voice step uses.

``channels/<code>.yaml`` names an env var (``voice.voice_id_env``). Its value,
from the process environment first and then the run's env file, is passed to
the voice subprocess as ``CF_TTS_VOICE_ID``. When it is unset the provider's
own default applies (``CF_FISH_AUDIO_REFERENCE_ID`` for Fish Audio), and the
choice says so, so the runner log and the reports can name which one was used.

The choice is also part of the voice step's fingerprint: changing the voice
re-runs the step instead of resuming on audio made with the old one.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from content_farm.production.channels import LOCAL_TTS_PROVIDERS, Channel, VoiceReference
from content_farm.voice.pronunciation import table_fingerprint

REPO_ROOT = Path(__file__).resolve().parents[3]
MOCK_PROVIDER = "macos_say"
MODEL_ENV = {"fish_audio": "CF_FISH_AUDIO_MODEL", "voxcpm2": "CF_VOXCPM2_MODEL", "qwen3_tts": "CF_QWEN3_TTS_MODEL"}
# keep in step with config.Settings (fish_audio_model, voxcpm2_model, qwen3_tts_model)
DEFAULT_MODEL = {"fish_audio": "s2.1-pro", "voxcpm2": "mlx-community/VoxCPM2-8bit",
                 "qwen3_tts": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"}
DEFAULT_VOICE_ENV = {
    "fish_audio": "CF_FISH_AUDIO_REFERENCE_ID",
    "elevenlabs": "CF_ELEVENLABS_VOICE_ID",
    "macos_say": "CF_MACOS_SAY_VOICE",
}


def reference_fingerprint(reference: VoiceReference) -> str:
    """Hash of the reference clip's bytes + transcript (same formula as voice.local_clone)."""
    path = reference.audio_path()
    if not path.is_file():
        raise FileNotFoundError(f"voice reference audio not found: {path}")
    digest = hashlib.sha256(path.read_bytes())
    digest.update(reference.text.encode("utf-8"))
    return digest.hexdigest()[:12]


@dataclass(frozen=True)
class VoiceChoice:
    provider: str
    voice_id: str        # "" = nothing set anywhere; the provider's built-in default
    source: str          # env var the id came from, or why there is none
    from_channel: bool   # True = the channel's own voice, passed as CF_TTS_VOICE_ID
    model: str = ""      # "" = the provider has no model setting we track
    reference: VoiceReference | None = None   # local cloning providers: the clip that is the voice
    pronunciation: str = ""                   # pronunciation table path ("" = none)
    pronunciation_sha: str = ""               # entries this provider/channel uses
    channel_code: str = ""
    speech_check: bool = False

    def describe(self) -> str:
        """One line for logs and fingerprints. Voice ids are not secrets; API keys never appear."""
        model = f" model={self.model}" if self.model else ""
        if self.reference is not None:
            voice = f" ref={self.voice_id}（{self.reference.audio}）"
        else:
            fallback = "" if self.from_channel else "，退回預設"
            voice = f" voice_id={self.voice_id or '(未設)'}（來源 {self.source}{fallback}）"
        extra = f" pron={self.pronunciation_sha}" if self.pronunciation_sha else ""
        return f"{self.provider}{model}{voice}{extra}"

    def env(self) -> dict[str, str]:
        """What the voice subprocess needs to use exactly this voice."""
        env = {"CF_TTS_PROVIDER": self.provider}
        if self.from_channel:
            env["CF_TTS_VOICE_ID"] = self.voice_id
        if self.model and self.provider in MODEL_ENV:
            env[MODEL_ENV[self.provider]] = self.model
        if self.reference is not None:
            env["CF_TTS_REF_AUDIO"] = str(self.reference.audio_path())
            env["CF_TTS_REF_TEXT"] = self.reference.text
        if self.pronunciation:
            env["CF_PRONUNCIATION_FILE"] = self.pronunciation
            env["CF_CHANNEL_CODE"] = self.channel_code
        if self.speech_check:
            env["CF_SPEECH_CHECK"] = "true"
        return env


def read_env_file(path: Path) -> dict[str, str]:
    """``KEY=VALUE`` lines of a dotenv file; comments, blanks and malformed lines are skipped."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def env_file_defaults(env_file: Path) -> dict[str, str]:
    """``CF_*`` values from the env file that the process environment does not already set.

    The voice subprocess runs from the repo root, whose ``.env`` may not exist
    (e.g. a worktree); this hands it the configured file's settings, with the
    real environment still taking precedence as pydantic-settings would."""
    return {key: value for key, value in read_env_file(env_file).items()
            if key.startswith("CF_") and key not in os.environ}


def _lookup(name: str, file_values: dict[str, str]) -> str:
    return os.environ.get(name) or file_values.get(name, "")


def choose_model(channel: Channel, file_values: dict[str, str]) -> str:
    """Channel yaml ``voice.model``, else the provider's model env var, else its default."""
    provider = channel.voice.provider
    if channel.voice.model:
        return channel.voice.model
    env_name = MODEL_ENV.get(provider, "")
    return (_lookup(env_name, file_values) if env_name else "") or DEFAULT_MODEL.get(provider, "")


def _pronunciation(channel: Channel) -> dict:
    """Table path, its fingerprint for this provider/channel, and the read-back check switch."""
    path = REPO_ROOT / channel.voice.pronunciation
    sha = table_fingerprint(path, provider=channel.voice.provider, channel=channel.code)
    return {"pronunciation": str(path), "pronunciation_sha": sha, "channel_code": channel.code,
            "speech_check": True}


def choose_voice(channel: Channel, env_file: Path, *, mock: bool) -> VoiceChoice:
    if mock:
        return VoiceChoice(MOCK_PROVIDER, "", "--mock-voice", from_channel=False)
    provider = channel.voice.provider
    file_values = read_env_file(env_file)
    model = choose_model(channel, file_values)
    extras = _pronunciation(channel)
    if provider in LOCAL_TTS_PROVIDERS:
        reference = channel.voice.reference
        assert reference is not None  # enforced by channels.Voice
        voice_id = f"ref:{reference_fingerprint(reference)}"
        return VoiceChoice(provider, voice_id, "voice.reference", from_channel=False, model=model,
                           reference=reference, **extras)
    channel_env = channel.voice.voice_id_env or ""
    channel_id = _lookup(channel_env, file_values)
    if channel_id:
        return VoiceChoice(provider, channel_id, channel_env, from_channel=True, model=model, **extras)
    default_env = DEFAULT_VOICE_ENV.get(provider, "")
    default_id = _lookup(default_env, file_values) if default_env else ""
    source = f"{default_env}（{channel_env} 未設）" if default_env else f"{channel_env} 未設"
    return VoiceChoice(provider, default_id, source, from_channel=False, model=model, **extras)
