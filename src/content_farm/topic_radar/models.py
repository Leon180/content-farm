"""Data shapes of the topic radar. Frozen: every stage returns new objects."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceName = Literal["youtube", "wikipedia", "hackernews", "reddit", "bilibili", "v2ex"]
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
    fetched_at: str = ""        # when the radar read it (trending sources); lets a person judge staleness


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
    excerpt: str = ""           # <= EXCERPT_CHARS of the public body; never author names or comments
    fetched_at: str = ""


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
    excerpt: str = ""


class SourceStatus(_Frozen):
    """Whether a source answered, and what it cost — recorded in every output file."""

    source: SourceName
    ok: bool
    requests: int = 0
    cache_hits: int = 0
    units: int = 0
    note: str = ""


class Fit(_Frozen):
    """Which channel a candidate suits, and why. ``kind="new"`` is only a label for a possible channel direction."""

    target: str                       # channel code (fable, yokai, technews …) or a new-direction slug (new-history …)
    kind: Literal["existing", "new"]
    label: str
    reason: str
    hits: int = 0                     # distinct rule keywords found in the candidate's text (0 = seed topic of that channel)


class PoolEntry(_Frozen):
    id: str
    origin: str                       # channel code whose radar produced it, or "cn-signal"
    kind: Kind
    subject: str
    title_draft: str
    format: VideoFormat
    score: float
    fits: tuple[Fit, ...]
    evidence: tuple[Evidence, ...]
    excerpt: str = ""
    warnings: tuple[str, ...] = ()


class Pool(_Frozen):
    date: str
    generated_at: str
    entries: tuple[PoolEntry, ...]
    sources: tuple[SourceStatus, ...]


class ChannelRadar(_Frozen):
    channel: str
    date: str
    generated_at: str
    youtube_data_expires: str
    candidates: tuple[Candidate, ...]
    sources: tuple[SourceStatus, ...]
