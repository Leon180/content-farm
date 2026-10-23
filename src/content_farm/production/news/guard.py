"""Guardrails of the entertainment-news channel, as code (Leon 2026-10-23), not as prompt text.

* **Source whitelist** — a story, a feed entry or a script source counts only when its host is one of the
  channel's whitelisted outlets (``series.news.feeds[].domains``).
* **Topics we never touch** — minors, sexual-scandal detail, illness / cause-of-death speculation, private
  addresses and family. :func:`blocked_reason` is applied to the headline + feed summary before the selection
  panel sees a story, again by the panel's own ``sensitive`` flag, and a third time to the finished script
  (``news.py lint``). The patterns are deliberately broad: a missed sensitive story costs more than a skipped
  harmless one (there are always other stories).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol, TypeVar
from urllib.parse import urlsplit


class HasDomains(Protocol):
    domains: tuple[str, ...]


Outlet = TypeVar("Outlet", bound=HasDomains)

# category → regex (case-insensitive). Traditional Chinese first, then the English / Japanese words that the
# whitelisted foreign outlets (Soompi, Variety, Deadline, NHK) use for the same things.
TOPIC_PATTERNS: dict[str, str] = {
    "未成年人": (r"未成年|童星|兒童|幼童|孩童|學童|小學生|國小生|國中生|高中生|中學生|青少年|少年少女|少女"
              r"|\bminors?\b|under-?age|child (?:star|actor)|\bteen(?:ager)?s?\b|schoolgirl|schoolboy|高校生|中学生|小学生|児童"),
    "性醜聞細節": (r"性侵|性騷|性愛|性交|性行為|性影片|性醜聞|性剝削|不雅|偷拍|猥褻|裸照|裸露|援交|嫖|約炮|強姦|強制性交"
               r"|sexual (?:assault|abuse|misconduct)|sex tape|\brape\b|\bnude\b|レイプ|わいせつ|性的暴行"),
    "病情與死因": (r"病逝|病情|病危|重病|罹癌|癌症|病故|過世|辭世|逝世|猝死|驟逝|死因|身亡|喪命|輕生|自殺|尋短|離世|憂鬱症|住院|開刀|手術"
              r"|\bdied\b|\bdies\b|\bdeath of\b|passed away|\bcancer\b|suicide|hospitali[sz]ed|訃報|死去|逝去"),
    "私人住址與家人": (r"住址|住家|住處|私宅|家人|親人|親屬|家屬|父母|爸爸|媽媽|母親|父親|子女|兒女|孩子|小孩|女兒|兒子|寶寶|前妻|前夫"
                "|老婆|老公|岳父|岳母|婆婆|公婆|私生活|home address|\\bhis (?:children|kids|wife)\\b"
                "|\\bher (?:children|kids|husband)\\b|family members|自宅|住所|家族"),
}
_COMPILED = {name: re.compile(pattern, re.I) for name, pattern in TOPIC_PATTERNS.items()}


def blocked_reason(*texts: str) -> str | None:
    """``"<category>：<matched words>"`` when any text touches a forbidden topic, else None."""
    joined = " ".join(t for t in texts if t)
    for name, pattern in _COMPILED.items():
        hit = pattern.search(joined)
        if hit:
            return f"{name}：{hit.group(0)}"
    return None


def host_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def host_matches(url: str, domains: Iterable[str]) -> bool:
    host = host_of(url)
    return any(host == d or host.endswith("." + d) for d in domains)


def outlet_for(url: str, feeds: Iterable[Outlet]) -> Outlet | None:
    """The whitelisted outlet that publishes ``url`` (None = not on the whitelist)."""
    return next((feed for feed in feeds if host_matches(url, feed.domains)), None)
