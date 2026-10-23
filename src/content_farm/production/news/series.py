"""The ``series.news`` (or legacy ``series.hn``) block of a channel yaml, validated here (channels.py only stores it)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from content_farm.production.channels import Channel
from content_farm.production.news.rank import Weights

SERIES_KEYS = ("news", "hn")     # "hn" = chipcat 快報 (original block name); "news" = technews


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Weekly(_Strict):
    items: tuple[int, int] = (3, 5)
    target_seconds: tuple[int, int] = (420, 660)
    publish_day: str = Field(default="sat", pattern="^(mon|tue|wed|thu|fri|sat|sun)$")
    publish_time: str = Field(default="10:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def _ranges(self) -> Weekly:
        if not 1 <= self.items[0] <= self.items[1] <= 8:
            raise ValueError(f"weekly.items must be 1 <= min <= max <= 8, got {self.items}")
        return self


class RankWeights(_Strict):
    popularity: float = Field(default=0.55, ge=0, le=1)
    relevance: float = Field(default=0.45, ge=0, le=1)
    comments: float = Field(default=0.6, ge=0, le=2)


class NewsSeries(_Strict):
    name: str
    playlist: str
    sources: tuple[str, ...] = ("hn", "lobsters", "arxiv")
    take_label: str = "晶片貓觀點"          # label of the 5th beat (commentary) on screen
    end_label: str = "每週六・長片整理"       # end-card ribbon
    # Narration speed of this channel's voice (visible chars / s, after tempo); lint and scene-length
    # estimates use it. 6.3 = chipcat's Fish voice. Local VoxCPM2 voices are slower: re-measure.
    chars_per_second: float = Field(default=6.3, gt=2, le=10)
    max_age_hours: float = Field(default=48, gt=0, le=168)
    review_candidates: int = Field(default=15, ge=3, le=40)
    daily_shorts: tuple[int, int] = (1, 2)
    shorts_time: str = Field(default="12:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekly: Weekly = Weekly()
    rank_weights: RankWeights = RankWeights()

    @model_validator(mode="after")
    def _sources(self) -> NewsSeries:
        bad = set(self.sources) - {"hn", "lobsters", "arxiv", "github"}
        if bad:
            raise ValueError(f"unknown/forbidden sources {sorted(bad)} (free sources only; no X)")
        return self

    def weights(self) -> Weights:
        w = self.rank_weights
        return Weights(popularity=w.popularity, relevance=w.relevance, comments=w.comments)


def news_series(channel: Channel) -> NewsSeries:
    block = next((channel.series[key] for key in SERIES_KEYS if key in channel.series), None)
    if block is None:
        raise ValueError(f"channel {channel.code} has no series.{'/'.join(SERIES_KEYS)} block")
    return NewsSeries.model_validate(block)


def branding_for(channel: Channel):
    """Words that differ per channel: chipcat's 快報 keeps the defaults, a ``series.news`` channel brings its own."""
    from content_farm.production.news.script import Branding

    if "news" not in channel.series:
        return Branding()
    series = news_series(channel)
    footer = channel.identity.description.footer if channel.identity else ""
    return Branding(take_label=series.take_label,
                    byline=footer or f"本片是{series.name}對原文的摘要與評論，不是翻譯；細節與數字以原文為準。",
                    series_line=f"{series.name}：每天整理國外科技圈值得知道的消息，用台灣中文講給你聽。",
                    tags=("Shorts", series.name, "科技新聞", "科技新知"))
