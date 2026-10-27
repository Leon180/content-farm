"""Cross-channel fit: rules (``channels/radar/pool.yaml``) that say which channel a candidate suits.

A rule is a set of keywords (lower-case; write simplified and traditional forms, Bilibili and V2EX are
simplified) plus a one-line reason. Matching is by distinct keyword: ASCII keywords match whole words,
CJK keywords match as substrings. The rules are a hint for a human, not a verdict.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from content_farm.topic_radar.config import RADAR_DIR, Watch
from content_farm.topic_radar.models import Fit

MAX_EXISTING_FITS = 2
MAX_NEW_FITS = 1


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FitRule(_Strict):
    target: str = Field(min_length=1, description="channel code, or a new-direction slug starting with 'new-'")
    kind: Literal["existing", "new"]
    label: str = Field(min_length=1)
    reason: str = Field(min_length=1, description="one sentence shown next to the candidate")
    keywords: tuple[str, ...] = Field(min_length=1)
    min_hits: int = Field(default=1, ge=1)


class PoolConfig(_Strict):
    pool_size: int = Field(default=40, ge=1, description="how many fresh Chinese-web signals enter the pool")
    per_target: int = Field(default=5, ge=1, description="candidates listed per channel in POOL.md")
    watch: Watch
    rules: tuple[FitRule, ...]


def load_pool_config(radar_dir: Path | None = None) -> PoolConfig:
    path = (radar_dir or RADAR_DIR) / "pool.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no pool config: {path}")
    config = PoolConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    for rule in config.rules:
        if (rule.kind == "new") != rule.target.startswith("new-"):
            raise ValueError(f"{path}: rule {rule.target!r}: kind 'new' targets must start with 'new-' (and only they)")
    return config


def _found(text: str, keyword: str) -> bool:
    word = keyword.lower()
    if word.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text) is not None
    return word in text


def _rule_fit(rule: FitRule, text: str) -> Fit | None:
    hits = sum(1 for keyword in dict.fromkeys(rule.keywords) if _found(text, keyword))
    if hits < rule.min_hits:
        return None
    return Fit(target=rule.target, kind=rule.kind, label=rule.label, reason=rule.reason, hits=hits)


def assign_fits(text: str, rules: tuple[FitRule, ...], origin: str | None = None) -> tuple[Fit, ...]:
    """Fits for ``text``: the origin channel first (its own seed topic), then the best keyword matches
    (at most MAX_EXISTING_FITS existing channels and MAX_NEW_FITS new directions), most hits first."""
    lowered = text.lower()
    scored = [fit for fit in (_rule_fit(rule, lowered) for rule in rules) if fit]
    scored.sort(key=lambda fit: -fit.hits)         # stable: ties keep the order of the rules file
    chosen: list[Fit] = []
    if origin and origin != "cn-signal":
        label = next((rule.label for rule in rules if rule.target == origin), origin)
        chosen.append(Fit(target=origin, kind="existing", label=label, reason="此頻道自己的種子題目", hits=0))
    for kind, limit in (("existing", MAX_EXISTING_FITS), ("new", MAX_NEW_FITS)):
        pool = [fit for fit in scored if fit.kind == kind and fit.target != origin]
        room = max(0, limit - sum(1 for fit in chosen if fit.kind == kind))
        chosen.extend(pool[:room])
    return tuple(chosen)
