"""Data shapes of the topic radar. Frozen: every stage returns new objects."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceName = Literal["youtube", "wikipedia", "hackernews", "reddit", "bilibili"]
Kind = Literal["evergreen", "trending"]
VideoFormat = Literal["shorts", "long"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Evidence(_Frozen):
    """One number that supports a candidate, with the URL a person can open to check it."""

    source: SourceName
    metric: str
    value: float
    url: str
    note: str = ""


class Competitor(_Frozen):
    title: str
    channel: str
    views: int
    published: str
    url: str


class ViewerQuestion(_Frozen):
    text: str
    likes: int
    url: str


class Signal(_Frozen):
    """A raw observation from one source before it is turned into a candidate (HN story, Bilibili video …)."""

    source: SourceName
    subject: str
    url: str
    metrics: dict[str, float] = Field(default_factory=dict)
    lang: str = ""
    published: str = ""


class Candidate(_Frozen):
    id: str
    kind: Kind
    subject: str
    title_draft: str
    format: VideoFormat
    format_reason: str
    score: float
    evidence: tuple[Evidence, ...]
    competitors: tuple[Competitor, ...] = ()
    viewer_questions: tuple[ViewerQuestion, ...] = ()
    warnings: tuple[str, ...] = ()


class SourceStatus(_Frozen):
    """Whether a source answered, and what it cost — recorded in every output file."""

    source: SourceName
    ok: bool
    requests: int = 0
    cache_hits: int = 0
    units: int = 0
    note: str = ""


class ChannelRadar(_Frozen):
    channel: str
    date: str
    generated_at: str
    youtube_data_expires: str
    candidates: tuple[Candidate, ...]
    sources: tuple[SourceStatus, ...]
