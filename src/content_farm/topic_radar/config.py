"""Per-channel radar settings: ``channels/radar/<code>.yaml``.

Kept apart from ``channels/<code>.yaml`` on purpose: that file's schema is strict (``extra="forbid"``) and
two of the six channels (deepsea, fable) live on other branches, so a separate file lets all six be
edited without touching a shared schema.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

RADAR_DIR = Path(__file__).resolve().parents[3] / "channels" / "radar"
CHANNEL_CODES = ("chipcat", "cel", "yokai", "technews", "deepsea", "fable")


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class WikiEntry(_Strict):
    lang: Literal["zh", "en", "ja"]
    title: str = Field(min_length=1)


class Topic(_Strict):
    subject: str = Field(min_length=1, description="what the video is about, in the channel's language")
    wiki: tuple[WikiEntry, ...] = ()
    youtube_query: str = ""
    title: str = Field(default="", description="hand-written title draft; empty = the channel's template")


class Subreddit(_Strict):
    name: str
    sort: Literal["top", "hot"] = "top"


class Watch(_Strict):
    """Where to look for fresh, fast-moving items (not tied to a seed topic)."""

    hackernews_queries: tuple[str, ...] = ()
    subreddits: tuple[Subreddit, ...] = ()
    bilibili_rids: tuple[int, ...] = ()
    keywords: tuple[str, ...] = Field(default=(), description="lower-case substrings; an item must contain one")


class RadarConfig(_Strict):
    channel: str
    title_template: str = "{subject}"
    shorts_supported: bool = True
    trending_bonus: float = Field(default=0.0, ge=0, le=40, description="added to trending items' score (news channels)")
    topics: tuple[Topic, ...]
    watch: Watch = Watch()

    @field_validator("title_template")
    @classmethod
    def _has_subject(cls, value: str) -> str:
        if "{subject}" not in value:
            raise ValueError("title_template must contain {subject}")
        return value


def load_radar_config(code: str, radar_dir: Path | None = None) -> RadarConfig:
    path = (radar_dir or RADAR_DIR) / f"{code}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no radar config for channel {code!r}: {path}")
    config = RadarConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if config.channel != code:
        raise ValueError(f"{path}: channel is {config.channel!r}, expected {code!r}")
    return config
