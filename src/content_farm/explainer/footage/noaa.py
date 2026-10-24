"""NOAA Ocean Exploration media, checked page by page (there is no licence API).

NOAA web content is a US-government work and public domain *unless the page says otherwise*
(https://www.noaa.gov/disclaimer). Pages often credit a visiting scientist or institution ("Video courtesy of …"), and
that is third-party material. :func:`scan_page` therefore accepts a page only if it names NOAA (Ocean Exploration /
OER / Okeanos Explorer / NOAA Fisheries…) as the credit and contains no other "courtesy of", ©, "copyright" or
"permission" wording. Everything else is refused with the offending phrase, so the 2019 Gulf of Mexico giant-squid clip
("Video courtesy of Edie Widder and Nathan Robinson") ends up as a description link, not on screen.
"""

from __future__ import annotations

import html
import re
from urllib.parse import urljoin, urlparse

from content_farm.explainer.footage.models import FootageCandidate

LICENSE = ("Public domain (US government work, NOAA)", "https://www.noaa.gov/disclaimer")
VIDEO_LINK = re.compile(r"""(?:src|href|content)=["']([^"']+\.(?:mp4|webm|mov)(?:\?[^"']*)?)["']""", re.I)
_NOAA_CREDIT = re.compile(
    r"(?:courtesy of|credit:?|source:?|video by)\s+(?:the\s+)?(?:NOAA|Ocean Exploration|OER|NOAA Ocean Exploration|"
    r"NOAA Office of Ocean Exploration|Okeanos Explorer)", re.I)
_COURTESY = re.compile(r"(?:courtesy of|credit:?|©|\(c\)|copyright|permission|used with)\s*([^.<]{0,60})", re.I)
_NOAA_NAME = re.compile(r"NOAA|Ocean Exploration|\bOER\b|Okeanos|Deep Discoverer|Seirios|Ocean Exploration Trust", re.I)


class PageRefused(ValueError):
    """The page cannot supply on-screen footage; ``str(exc)`` says why."""


def is_noaa_host(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host == "noaa.gov" or host.endswith(".noaa.gov")


def _text(markup: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def scan_page(markup: str, page_url: str) -> FootageCandidate:
    """Page HTML → one candidate, or :class:`PageRefused`."""
    if not is_noaa_host(page_url):
        raise PageRefused(f"not a noaa.gov page: {page_url}")
    body = re.sub(r"<(script|style|nav|footer|header)\b.*?</\1>", " ", markup, flags=re.S | re.I)
    text = _text(body)
    third = [m.group(0).strip() for m in _COURTESY.finditer(text) if not _NOAA_NAME.search(m.group(1))]
    if third:
        raise PageRefused(f"第三方版權／出處註記：{third[0][:80]!r}")
    if not _NOAA_CREDIT.search(text) and not re.search(r"public domain", text, re.I):
        raise PageRefused("頁面沒有明確的 NOAA 出處或公有領域標示")
    links = [urljoin(page_url, m) for m in VIDEO_LINK.findall(markup)]
    links = [u for u in dict.fromkeys(links) if "thumb" not in u.lower()]
    if not links:
        raise PageRefused("頁面找不到可下載的影片檔")
    title_match = re.search(r"<title>(.*?)</title>", markup, re.S | re.I)
    title = _text(title_match.group(1)).removesuffix(" - NOAA Ocean Exploration") if title_match else page_url
    return FootageCandidate(
        provider="noaa", provider_id=urlparse(page_url).path.strip("/").replace("/", "-")[:80],
        title=title, page_url=page_url, download_url=links[0], width=0, height=0, duration=0,
        author="NOAA Ocean Exploration", author_url="https://oceanexplorer.noaa.gov",
        license_name=LICENSE[0], license_url=LICENSE[1], description=text[:300],
    )
