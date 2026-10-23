"""Dedupe across sources, keep the last 48 hours, score for a Taiwan audience.

score = (0.55·popularity + 0.45·relevance) · freshness

- popularity ∈ [0, 1]: HN log(points)+0.6·log(comments) normalised to the day's
  best; Lobsters/arXiv from their list position (no score in RSS/Atom).
- relevance ∈ [0, 1]: weighted Taiwan keywords (chips, supply chain, AI hardware,
  security, platforms Taiwanese users use), capped; topics we never cover score 0.
- freshness: 1.0 at 0 h → 0.5 at 48 h; older is dropped.

The weights are a first guess, written down so Leon can tune them after a few
weeks of picks (``rank_weights`` in the series config).
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from content_farm.production.news.models import Candidate, Ranked

MAX_AGE_HOURS = 48.0
TITLE_DUP_JACCARD = 0.6

# keyword (lower-case regex) → weight. One hit of 1.0 is "clearly for Taiwan".
TAIWAN_KEYWORDS: Mapping[str, float] = {
    r"taiwan|taipei|台灣|臺灣": 1.0,
    r"\btsmc\b|台積電": 1.0,
    r"semiconductor|foundry|wafer|\bfab\b|lithograph|\beuv\b|asml": 0.9,
    r"\bchips?\b|chipmaker|\bsoc\b|\bnpu\b|\bgpu\b|\bhbm\b|cowos|packaging": 0.8,
    r"nvidia|\bamd\b|intel|qualcomm|mediatek|聯發科|\barm\b|risc-v|apple silicon|\bm[1-6]\b": 0.7,
    r"foxconn|hon hai|鴻海|quanta|wistron|pegatron|supply chain|tariff|export control": 0.9,
    r"data ?cent(er|re)|power grid|electricity|energy|nuclear|battery": 0.5,
    r"\bai\b|\bllm\b|model|inference|training|open[- ]?weights?|open[- ]?source": 0.4,
    r"security|vulnerab|exploit|\bcve\b|zero[- ]day|ransomware|breach|malware|bgp|rpki": 0.6,
    r"privacy|regulat|antitrust|copyright|lawsuit|\beu\b|\bfcc\b": 0.4,
    r"iphone|android|google|apple|microsoft|meta\b|youtube|line\b|openai|anthropic": 0.4,
    r"robot|\bev\b|electric vehicle|drone|satellite|5g|6g": 0.4,
}
# Topics the series does not cover (rules: 不給投資建議; no crypto pumping; no US partisan politics).
EXCLUDE_PATTERNS = (r"\bcrypto|bitcoin|ethereum|\bnft\b|memecoin", r"\btrump\b|\bbiden\b|election")

# Entertainment profile: what a Taiwanese audience follows (Taiwan / Japan / Korea / Chinese-language industry).
ENT_KEYWORDS: Mapping[str, float] = {
    r"台灣|臺灣|台北|taiwan": 0.9,
    r"金曲|金鐘|金馬|金像|葛萊美|奧斯卡|艾美|grammy|oscar|emmy|golden globe|blue dragon|青龍": 0.9,
    r"演唱會|巡演|巡迴|世界巡|concert|world tour|fan ?meeting|見面會": 0.8,
    r"專輯|新歌|單曲|回歸|出道|打歌|mv\b|album|comeback|debut|ライブ|アルバム": 0.7,
    r"票房|上映|首映|電影|影集|戲劇|劇集|連續劇|綜藝|box office|premiere|series|film|drama|season": 0.7,
    r"k-?pop|j-?pop|偶像|團體|男團|女團|idol|ジャニーズ|アイドル": 0.6,
    r"netflix|disney|hbo|apple tv|prime video|kkbox|friday|愛奇藝|iqiyi|youtube": 0.5,
}
_TRACKING = re.compile(r"^(utm_|ref$|ref_src$|fbclid$|gclid$|mc_)")
_WORD = re.compile(r"[a-z0-9]+|[一-鿿]")


@dataclass(frozen=True)
class Weights:
    popularity: float = 0.55
    relevance: float = 0.45
    comments: float = 0.6


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k)))
    path = parts.path.rstrip("/") or "/"
    if host == "arxiv.org":
        path = re.sub(r"^/(pdf|html)/", "/abs/", path).removesuffix(".pdf")
        path = re.sub(r"v\d+$", "", path)
    return urlunsplit(("https", host, path, query, ""))


def title_tokens(title: str) -> frozenset[str]:
    return frozenset(_WORD.findall(title.lower()))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _merge(a: Candidate, b: Candidate) -> Candidate:
    """Keep the earliest sighting and the HN-style id; union discussions/tags/summary."""
    first, second = (a, b) if a.posted_at <= b.posted_at else (b, a)
    keeper = next((c for c in (a, b) if c.id.startswith("hn-")), first)
    discussions = tuple({d.url: d for d in (*a.discussions, *b.discussions)}.values())
    return keeper.model_copy(update={
        "posted_at": first.posted_at, "discussions": discussions,
        "tags": tuple(dict.fromkeys((*a.tags, *b.tags))),
        "summary": a.summary or b.summary,
    })


def dedupe(candidates: Iterable[Candidate]) -> list[Candidate]:
    """Same canonical URL, or near-identical titles (Jaccard ≥ 0.6), are one story."""
    merged: list[Candidate] = []
    keys: list[tuple[str, frozenset[str]]] = []
    for cand in candidates:
        key = (canonical_url(cand.url), title_tokens(cand.title))
        hit = next((i for i, (url, toks) in enumerate(keys)
                    if url == key[0] or jaccard(toks, key[1]) >= TITLE_DUP_JACCARD), None)
        if hit is None:
            merged.append(cand)
            keys.append(key)
        else:
            merged[hit] = _merge(merged[hit], cand)
    return merged


def relevance_ent(candidate: Candidate) -> tuple[float, tuple[str, ...]]:
    """Entertainment: weighted keywords over title + feed summary; a bare headline still scores 0.2 (the panel decides)."""
    text = " ".join((candidate.title, candidate.summary, " ".join(candidate.tags))).lower()
    hits = [(pattern, w) for pattern, w in ENT_KEYWORDS.items() if re.search(pattern, text)]
    if not hits:
        return 0.2, ()
    weights = sorted((w for _, w in hits), reverse=True)
    reasons = tuple(re.search(p, text).group(0) for p, _ in hits)  # type: ignore[union-attr]
    return round(min(1.0, weights[0] + 0.2 * sum(weights[1:])), 3), reasons


def relevance(candidate: Candidate) -> tuple[float, tuple[str, ...]]:
    text = " ".join((candidate.title, candidate.domain, " ".join(candidate.tags))).lower()
    if any(re.search(p, text) for p in EXCLUDE_PATTERNS):
        return 0.0, ("excluded",)
    hits = [(pattern, w) for pattern, w in TAIWAN_KEYWORDS.items() if re.search(pattern, text)]
    if not hits:
        return 0.0, ()
    weights = sorted((w for _, w in hits), reverse=True)
    value = min(1.0, weights[0] + 0.25 * sum(weights[1:]))
    reasons = tuple(re.search(p, text).group(0) for p, _ in hits)  # type: ignore[union-attr]
    return round(value, 3), reasons


def _hn_raw(candidate: Candidate, comments_weight: float) -> float:
    hn = [d for d in candidate.discussions if d.site == "hn"]
    if not hn:
        return 0.0
    return max(math.log1p(d.points or 0) + comments_weight * math.log1p(d.comments or 0) for d in hn)


def _rank_score(candidate: Candidate, site: str, list_size: int) -> float:
    ranks = [d.rank for d in candidate.discussions if d.site == site and d.rank]
    if not ranks or list_size <= 0:
        return 0.0
    return max(0.0, 1.0 - (min(ranks) - 1) / list_size)


def _outlet_score(candidate: Candidate, list_size: int) -> float:
    """Whitelisted-outlet stories: list position (0.6 weight) + 0.25 per extra outlet that carries the same story."""
    feeds = [d for d in candidate.discussions if d.site == "rss"]
    if not feeds:
        return 0.0
    position = max(0.0, 1.0 - (min(d.rank or list_size for d in feeds) - 1) / max(list_size, 1))
    return min(1.0, 0.6 * position + 0.25 * (len(feeds) - 1))


def popularity(candidates: Sequence[Candidate], weights: Weights) -> dict[str, float]:
    raw = {c.id: _hn_raw(c, weights.comments) for c in candidates}
    best = max(raw.values(), default=0.0) or 1.0
    lob_n = sum(any(d.site == "lobsters" for d in c.discussions) for c in candidates)
    arx_n = sum(any(d.site == "arxiv" for d in c.discussions) for c in candidates)
    gh_n = sum(any(d.site == "github" for d in c.discussions) for c in candidates)
    rss_n = sum(any(d.site == "rss" for d in c.discussions) for c in candidates)
    out = {}
    for c in candidates:
        values = [raw[c.id] / best,
                  0.6 * _rank_score(c, "lobsters", lob_n),   # a Lobsters front page < an HN front page
                  0.3 * _rank_score(c, "arxiv", arx_n),      # a fresh paper alone is rarely news
                  0.55 * _rank_score(c, "github", gh_n),     # a trending repo alone: a tool, rarely a story
                  _outlet_score(c, rss_n)]                   # whitelisted outlets: how many carry it, and how high
        bonus = 0.1 if len({d.site for d in c.discussions}) > 1 else 0.0  # on two sites
        out[c.id] = round(min(1.0, max(values) + bonus), 3)
    return out


def age_hours(candidate: Candidate, now: datetime) -> float:
    return (now - datetime.fromisoformat(candidate.posted_at)).total_seconds() / 3600


def rank(candidates: Iterable[Candidate], now: datetime, weights: Weights = Weights(),
         max_age_hours: float = MAX_AGE_HOURS, profile: str = "tech") -> list[Ranked]:
    unique = [c for c in dedupe(candidates) if -1 <= age_hours(c, now) <= max_age_hours]  # -1: clock skew
    pop = popularity(unique, weights)
    ranked = []
    for c in unique:
        rel, reasons = relevance_ent(c) if profile == "ent" else relevance(c)
        if reasons == ("excluded",):
            continue
        age = max(0.0, age_hours(c, now))
        fresh = 1.0 - 0.5 * min(age, max_age_hours) / max_age_hours
        score = (weights.popularity * pop[c.id] + weights.relevance * rel) * fresh
        ranked.append(Ranked(candidate=c, score=round(score, 4), popularity=pop[c.id], freshness=round(fresh, 3),
                             relevance=rel, age_hours=round(age, 1), reasons=reasons))
    return sorted(ranked, key=lambda r: (-r.score, r.candidate.id))
