"""Trending query schemas."""

from __future__ import annotations

from pydantic import BaseModel


class TrendingQuery(BaseModel):
    """A single trending search query."""

    model_config = {"frozen": True}

    query: str
    category: str
    rising_percent: int | None = None
