"""Data shapes shared by the news modules (all frozen; JSON on disk)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Discussion(_Frozen):
    """Where people talk about the story. Leads only — never quoted as fact."""

    site: str = Field(pattern="^(hn|lobsters|arxiv|github)$")
    url: str
    points: int | None = None        # Lobsters RSS and arXiv carry no score
    comments: int | None = None
    rank: int | None = None          # position in the source's own list (1 = top)


class Candidate(_Frozen):
    id: str = Field(min_length=1, max_length=40)       # "hn-45601234", "lob-abc123", "arxiv-2610.01234"
    title: str = Field(min_length=1, max_length=300)    # original-language title as published
    url: str                                            # the original article (not the discussion)
    domain: str
    posted_at: str                                      # ISO-8601 UTC, earliest sighting
    discussions: tuple[Discussion, ...] = ()
    tags: tuple[str, ...] = ()                          # source tags (Lobsters categories, arXiv cats)
    summary: str = ""                                   # arXiv abstract only; empty otherwise


class Read(_Frozen):
    """Result of opening the original URL once (``verify``)."""

    url: str                     # what we asked for
    final_url: str = ""          # after redirects
    read_at: str                 # ISO-8601 with offset
    ok: bool
    reason: str = ""             # why not ok: http 403, robots, too short, not html, …
    kind: str = Field(default="article", pattern="^(article|abstract)$")
    page_title: str = ""
    published: str = ""          # from article:published_time / <time>, if any
    description: str = ""        # meta description (shown on the private review page only)
    chars: int = 0               # visible text length we got
    text_path: str = ""          # local cache (output/, never committed)


class Ranked(_Frozen):
    candidate: Candidate
    score: float
    popularity: float
    freshness: float
    relevance: float
    age_hours: float
    reasons: tuple[str, ...] = ()       # matched Taiwan-relevance keywords
    read: Read | None = None
