"""Channel config: one ``channels/<code>.yaml`` per YouTube channel.

A channel ties together everything that stays the same across its videos —
brand (slide theme), mascot, voice, topic categories, length, cadence, Shorts
strategy, media policy and which human gates its pipeline stops at. Secrets
never live here: the YouTube section only names the env vars that hold them.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from content_farm.explainer.brands import brand_codes
from content_farm.production.identity import Identity

CHANNELS_DIR = Path(__file__).resolve().parents[3] / "channels"

_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class Pipeline(str, Enum):
    EXPLAINER = "explainer"      # article → deck → voice → media → assembly → mascot
    SHORTS_SKIT = "shorts_skit"  # script → voice → mascot skit (no article, no deck)


class Gate(str, Enum):
    ARTICLE = "article"  # 文章審稿：論點、來源、八卦出處
    DECK = "deck"        # deck 審稿：contact sheet＋講稿
    SCRIPT = "script"    # 短劇本審稿（沒有文章階段的頻道用）
    MEDIA = "media"      # B-roll／AI 圖／artwork 授權
    FINAL = "final"      # 成片審看


# Gates every pipeline must keep — the final watch-through is never optional.
REQUIRED_GATES = {Gate.FINAL}
PIPELINE_GATES: dict[Pipeline, tuple[Gate, ...]] = {
    Pipeline.EXPLAINER: (Gate.ARTICLE, Gate.DECK, Gate.MEDIA, Gate.FINAL),
    Pipeline.SHORTS_SKIT: (Gate.SCRIPT, Gate.FINAL),
}


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Mascot(_Strict):
    name: str
    ref: str = Field(description="character id or asset path; resolved by the mascot module")
    rig_ready: bool = Field(default=False, description="False = skip the mascot overlay step")
    # rig: the vector 晶片貓 (explainer.mascot). pngtuber: a still-image pack, ref = "pngtuber/<pack id>"
    host: Literal["rig", "pngtuber"] = "rig"

    @model_validator(mode="after")
    def _pngtuber_ref(self) -> Mascot:
        if self.host == "pngtuber" and not self.ref.startswith("pngtuber/"):
            raise ValueError(f"mascot.host pngtuber needs ref 'pngtuber/<pack id>', got {self.ref!r}")
        return self


LOCAL_TTS_PROVIDERS = ("voxcpm2", "qwen3_tts")
TTS_PROVIDERS = ("fish_audio", "elevenlabs", "macos_say", *LOCAL_TTS_PROVIDERS)


class VoiceReference(_Strict):
    """The clip a local cloning model imitates, and its exact transcript."""
    audio: str = Field(min_length=1, description="path to the reference WAV; ~ is expanded")
    text: str = Field(min_length=1, description="what is said in the clip, word for word")
    note: str = ""   # where the take came from (trial, take id), for people

    def audio_path(self) -> Path:
        return Path(self.audio).expanduser()


class Voice(_Strict):
    provider: str = "fish_audio"
    # env var holding the voice id (Fish / ElevenLabs); local cloning providers use `reference`
    voice_id_env: str | None = Field(default=None, description="env var holding the TTS voice id")
    # TTS model for this channel (Fish: sent as the `model` header). None = CF_FISH_AUDIO_MODEL,
    # else the provider default. Changing voice id or model re-voices the whole video.
    model: str | None = Field(default=None, min_length=1, max_length=80)
    reference: VoiceReference | None = None
    # Narration speed, pitch kept (ffmpeg atempo). Changing it re-times the takes; it never
    # re-synthesizes (voice.tempo). Leon 2026-10-17 944769e1fc01.
    tempo: float = Field(default=1.0, ge=0.5, le=2.0)
    # Shared pronunciation table, relative to the repo root (TTS text only, not subtitles).
    pronunciation: str = "channels/shared/pronunciation.yaml"

    @field_validator("voice_id_env")
    @classmethod
    def _env_name(cls, value: str | None) -> str | None:
        return None if value is None else _check_env_name(value)

    @model_validator(mode="after")
    def _provider_needs(self) -> Voice:
        if self.provider not in TTS_PROVIDERS:
            raise ValueError(f"unknown voice provider {self.provider!r}; choose from {', '.join(TTS_PROVIDERS)}")
        if self.provider in LOCAL_TTS_PROVIDERS and self.reference is None:
            raise ValueError(f"voice provider {self.provider} clones a reference clip: set voice.reference")
        if self.provider not in LOCAL_TTS_PROVIDERS and self.voice_id_env is None:
            raise ValueError(f"voice provider {self.provider} needs voice.voice_id_env")
        return self


class Format(_Strict):
    length: str = Field(pattern="^(long|short)$")
    aspect: str = Field(pattern="^(16:9|9:16)$")
    target_seconds: tuple[int, int]
    # The length we aim for inside the range (Leon 2026-10-16: long videos 7–10 min, aim
    # >= 8:00 when the content holds up — mid-roll ads need 8 min). QC warns below it.
    goal_seconds: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _range(self) -> Format:
        low, high = self.target_seconds
        if not 0 < low <= high:
            raise ValueError(f"target_seconds must be 0 < min <= max, got {self.target_seconds}")
        if self.goal_seconds is not None and not low <= self.goal_seconds <= high:
            raise ValueError(f"goal_seconds {self.goal_seconds} must lie in target_seconds {self.target_seconds}")
        return self


class Cadence(_Strict):
    long_per_week: float = Field(ge=0, le=7)
    shorts_per_week: float = Field(ge=0, le=21)
    publish_days: tuple[str, ...] = ()   # long videos
    shorts_days: tuple[str, ...] = ()    # Shorts; empty = spread evenly over the week
    publish_time: str = Field(default="19:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = "Asia/Taipei"
    lead_days: int = Field(default=7, ge=0, le=60)  # start production this long before publishing

    @field_validator("publish_days", "shorts_days")
    @classmethod
    def _days(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        bad = [day for day in value if day not in _WEEKDAYS]
        if bad:
            raise ValueError(f"publish_days must be among {_WEEKDAYS}, got {bad}")
        return value


class MediaPolicy(_Strict):
    stock: bool = True
    ai_image: bool = True
    artwork: bool = False               # museum / public-domain artwork
    artwork_license_required: bool = True
    source_footage: bool = False        # other people's video — forbidden on every channel today

    @field_validator("source_footage")
    @classmethod
    def _no_source_footage(cls, value: bool) -> bool:
        if value:
            raise ValueError("source_footage must stay false (rule: 不用別人影片的原片)")
        return value


DEFAULT_STYLE_PREFIX = ("Hand-drawn editorial illustration, flat colours and clean ink lines, "
                        "illustration, not a photograph, no text, no logos.")


class AiIllustration(_Strict):
    """How ``ai_image`` slides are generated (Leon 2026-10-16 cc801e14fbc2: klein by default,
    Z-Image ink wash for yokai). Machine paths come from CF_MFLUX_BIN_DIR / CF_MFLUX_HF_HOME."""

    provider: str = Field(default="local_mflux", pattern="^local_mflux$")  # api / browser later
    model: str = "flux2-klein-4b"
    style_prefix: str = Field(default=DEFAULT_STYLE_PREFIX, min_length=1, max_length=400)
    seed: int = Field(default=42, ge=0)
    width: int = Field(default=1280, ge=256, le=2048, multiple_of=16)
    height: int = Field(default=720, ge=256, le=2048, multiple_of=16)

    @field_validator("model")
    @classmethod
    def _known_model(cls, value: str) -> str:
        from content_farm.explainer.illustrate import MODELS

        if value not in MODELS:
            raise ValueError(f"unknown ai_illustration model {value!r}; known: {', '.join(MODELS)}")
        return value

    @field_validator("style_prefix")
    @classmethod
    def _non_photoreal(cls, value: str) -> str:
        from content_farm.explainer.illustrate import forbidden_prompt_terms

        bad = forbidden_prompt_terms(value)
        if bad:
            raise ValueError(f"style_prefix asks for {bad} (rule: 非擬真、不模仿畫家)")
        return value


class YouTube(_Strict):
    # One OAuth client (shared, CF_YOUTUBE_CLIENT_ID/SECRET as today); one refresh token per
    # channel, minted by scripts/get_youtube_token.py while signed in as that channel.
    client_id_env: str = "CF_YOUTUBE_CLIENT_ID"
    client_secret_env: str = "CF_YOUTUBE_CLIENT_SECRET"
    refresh_token_env: str
    channel_id_env: str
    ai_disclosure: bool = True          # description-text disclosure line (TTS voice / AI images)
    # Studio's 「變造或合成內容」 checkbox = API status.containsSyntheticMedia. Off by Leon's
    # 2026-10-16 decision (916c2864e31f): disclose in the description only. YouTube asks for the
    # label on realistic altered content; our AI images are illustration/ink-wash by rule.
    altered_content_label: bool = False
    default_privacy: str = Field(default="private", pattern="^(private|unlisted|public)$")

    @field_validator("client_id_env", "client_secret_env", "refresh_token_env", "channel_id_env")
    @classmethod
    def _env_names(cls, value: str) -> str:
        return _check_env_name(value)


class Channel(_Strict):
    code: str = Field(pattern="^[a-z][a-z0-9_]{1,31}$")
    name: str
    line: str
    pipeline: Pipeline
    brand: str
    deck_category: str | None = None
    mascot: Mascot
    voice: Voice
    topic_categories: tuple[str, ...]
    format: Format
    cadence: Cadence
    shorts_strategy: str
    media: MediaPolicy = MediaPolicy()
    ai_illustration: AiIllustration = AiIllustration()
    gates: tuple[Gate, ...]
    youtube: YouTube
    identity: Identity | None = None   # opening / sign-off / description per channel
    notes: tuple[str, ...] = ()

    @field_validator("brand")
    @classmethod
    def _known_brand(cls, value: str) -> str:
        if value not in brand_codes():
            raise ValueError(f"unknown brand {value!r}; choose from {', '.join(brand_codes())}")
        return value

    @model_validator(mode="after")
    def _gates_fit_pipeline(self) -> Channel:
        allowed = set(PIPELINE_GATES[self.pipeline])
        extra = [gate.value for gate in self.gates if gate not in allowed]
        if extra:
            raise ValueError(f"gates {extra} do not exist in pipeline {self.pipeline.value}")
        missing = [gate.value for gate in REQUIRED_GATES if gate not in self.gates]
        if missing:
            raise ValueError(f"gate(s) {missing} cannot be removed")
        if self.pipeline is Pipeline.EXPLAINER and self.deck_category is None:
            raise ValueError("explainer channels need deck_category")
        if self.pipeline is Pipeline.EXPLAINER and self.identity is None:
            raise ValueError("explainer channels need identity (opening, outro, description template)")
        return self

    def gate_enabled(self, gate: Gate) -> bool:
        return gate in self.gates


def _check_env_name(value: str) -> str:
    if not _ENV_NAME.match(value):
        raise ValueError(f"{value!r} is not an env var name (UPPER_SNAKE); never put secret values here")
    return value


def load_channel(code_or_path: str | Path, channels_dir: Path = CHANNELS_DIR) -> Channel:
    path = Path(code_or_path)
    if path.suffix not in (".yaml", ".yml"):
        path = channels_dir / f"{code_or_path}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"channel config not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    channel = Channel.model_validate(data)
    if path.stem != channel.code:
        raise ValueError(f"{path}: file name must match code {channel.code!r}")
    return channel


def load_all(channels_dir: Path = CHANNELS_DIR) -> tuple[Channel, ...]:
    return tuple(load_channel(path, channels_dir) for path in sorted(channels_dir.glob("*.yaml")))


def other_identities(channel: Channel, channels_dir: Path = CHANNELS_DIR) -> tuple[Identity, ...]:
    """Identities of every other channel in ``channels_dir`` (for cross-channel checks)."""
    return tuple(other.identity for other in load_all(channels_dir)
                 if other.code != channel.code and other.identity is not None)
