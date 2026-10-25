"""The ``series.news`` (or legacy ``series.hn``) block of a channel yaml, validated here (channels.py only stores it)."""

from __future__ import annotations

from typing import Literal

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


class Feed(_Strict):
    """One whitelisted outlet (ent): the only way a story can enter the channel."""

    id: str = Field(pattern="^[a-z][a-z0-9-]{1,15}$")
    name: str = Field(min_length=1, max_length=20)        # how the narration credits it: 「據{name}報導」
    aliases: tuple[str, ...] = ()                         # other spellings the narration may use for the same outlet
    domains: tuple[str, ...] = Field(min_length=1)        # hosts (and sub-domains) its articles live on
    url: str = Field(pattern=r"^https://")                # public RSS / Atom feed
    lang: Literal["zh", "ja", "ko", "en"] = "zh"
    spacing_seconds: float = Field(default=1.0, ge=0.5, le=10)   # minimum gap between requests to the feed host

    def names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


class NewsSeries(_Strict):
    name: str
    playlist: str
    sources: tuple[str, ...] = ("hn", "lobsters", "arxiv")
    dir_prefix: str = Field(default="hn", pattern="^[a-z][a-z0-9]{1,15}$")   # output/<prefix>-<day>… (channels must not share)
    min_per_source: int = Field(default=0, ge=0, le=5)   # review page: at least this many readable stories from each non-HN source
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
    # ── entertainment news (channel ``ent``): everything below is opt-in; the tech channels leave it unset ──
    feeds: tuple[Feed, ...] = ()                  # the source whitelist; "rss" in ``sources`` reads exactly these
    rank_profile: Literal["tech", "ent"] = "tech"
    topic_guard: bool = False                     # guard.blocked_reason on candidates, panel flag, finished script
    claims_audit: bool = False                    # every factual sentence needs a sourced claim (news/claims.py)
    fact_check: bool = False                      # correctness check of the script vs the original (news/fact_check.py)
    analogy_required: bool = True                # tech Shorts explain a glossary term; ent has no analogy beat
    beat_labels: dict[str, str] = {}              # on-screen name per beat kind (overrides news.script.BEAT_LABELS)
    bubbles: dict[str, str] = {}                  # the small callout per beat kind (overrides news.render.BUBBLES)
    end_headline: str = "這週最重要的幾則\n週六講深一點"       # end card
    end_points: tuple[str, ...] = ("原文連結都在說明欄", "摘要＋評論，非翻譯")
    panel_brief: str = ""                         # one sentence on the channel for the selection panel
    series_line: str = ""                         # description footer line (replaces the tech default)
    tags: tuple[str, ...] = ()                    # extra tags; replaces the tech default tags when set

    @model_validator(mode="after")
    def _sources(self) -> NewsSeries:
        bad = set(self.sources) - {"hn", "lobsters", "arxiv", "github", "rss"}
        if bad:
            raise ValueError(f"unknown/forbidden sources {sorted(bad)} (free sources only; no X)")
        if ("rss" in self.sources) != bool(self.feeds):
            raise ValueError("sources has 'rss' exactly when feeds (the whitelist) is non-empty")
        if len({f.id for f in self.feeds}) != len(self.feeds):
            raise ValueError("feeds: duplicate id")
        return self

    def outlet(self, url: str) -> Feed | None:
        """The whitelisted outlet publishing ``url``; None when it is not on the whitelist."""
        from content_farm.production.news.guard import outlet_for

        return outlet_for(url, self.feeds)

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
                    series_line=series.series_line or f"{series.name}：每天整理國外科技圈值得知道的消息，用台灣中文講給你聽。",
                    tags=("Shorts", series.name, *(series.tags or ("科技新聞", "科技新知"))),
                    beat_labels=dict(series.beat_labels))
