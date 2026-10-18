"""Open each candidate's original URL once and record what we read, and when.

Rule (Leon): no script without reading the original page (or the arXiv
abstract). A page we cannot read — paywall, 403, robots.txt disallow, a
JavaScript shell with no text, a non-HTML file — makes the story
unpickable on the review page. HN/Lobsters comments are never read here:
they are leads, not facts.

The text we extract is cached under the day's ``reads/`` (inside ``output/``,
which is never committed) for the script writer; it is not republished.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlsplit

from content_farm.production.news import fetch
from content_farm.production.news.models import Candidate, Read

MIN_CHARS = 600            # less than this is a teaser / JS shell, not an article
ABSTRACT_MIN_CHARS = 200
_SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside", "button"}
_BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "blockquote", "pre", "td", "figcaption"}


class _Extractor(HTMLParser):
    """Title, a few meta tags and block-level visible text — enough to fact-check, no layout."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self.blocks: list[str] = []
        self._skip = 0
        self._in_title = False
        self._buf: list[str] = []
        self._time = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag in _SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"].strip())
        elif tag == "time" and a.get("datetime") and not self._time:
            self._time = a["datetime"]
        elif tag in _BLOCK:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in _BLOCK:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self._buf.append(data)

    def _flush(self) -> None:
        text = " ".join("".join(self._buf).split())
        self._buf = []
        if len(text) >= 25:
            self.blocks.append(text)

    def result(self) -> tuple[str, dict[str, str], str, list[str]]:
        self._flush()
        return " ".join(self.title.split()), self.meta, self._time, self.blocks


def extract(html: str) -> dict[str, object]:
    parser = _Extractor()
    parser.feed(html)
    parser.close()
    title, meta, time_attr, blocks = parser.result()
    published = (meta.get("article:published_time") or meta.get("og:published_time")
                 or meta.get("date") or meta.get("dc.date") or time_attr)
    return {
        "title": meta.get("og:title") or title,
        "description": meta.get("og:description") or meta.get("description") or "",
        "published": published[:25],
        "text": "\n\n".join(dict.fromkeys(blocks)),
    }


def _decode(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    for encoding in ([match.group(1)] if match else []) + ["utf-8", "latin-1"]:
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


RobotsCheck = Callable[[str], bool]


def robots_allows(get: fetch.Getter) -> RobotsCheck:
    """``can_fetch`` per host, cached; an unreadable robots.txt counts as allowed (RFC 9309 §2.3.1.3)."""
    cache: dict[str, robotparser.RobotFileParser | None] = {}

    def check(url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in cache:
            try:
                resp = get(f"{origin}/robots.txt")
                parser = robotparser.RobotFileParser()
                parser.parse(_decode(resp.body, resp.content_type).splitlines() if resp.status == 200 else [])
                cache[origin] = parser
            except fetch.FetchError:
                cache[origin] = None
        parser = cache[origin]
        return True if parser is None else parser.can_fetch(fetch.USER_AGENT, url)

    return check


def _save(reads_dir: Path, candidate: Candidate, header: str, text: str) -> str:
    reads_dir.mkdir(parents=True, exist_ok=True)
    path = reads_dir / f"{candidate.id}.txt"
    path.write_text(header + "\n\n" + text + "\n", encoding="utf-8")
    return str(path)


def read_abstract(candidate: Candidate, get: fetch.Getter, reads_dir: Path, now: str) -> Read:
    """arXiv: the API abstract (never the PDF)."""
    ident = fetch.arxiv_abs_id(candidate.url)
    paper = None
    if candidate.summary:
        paper = candidate
    elif ident:
        paper = fetch.fetch_arxiv_abstract(get, ident)
    if paper is None or len(paper.summary) < ABSTRACT_MIN_CHARS:
        return Read(url=candidate.url, read_at=now, ok=False, reason="arXiv abstract not found", kind="abstract")
    header = f"# {paper.title}\nURL: {paper.url}\nread_at: {now}\nkind: arXiv abstract (API)"
    return Read(url=candidate.url, final_url=paper.url, read_at=now, ok=True, kind="abstract",
                page_title=paper.title, published=paper.posted_at, description=paper.summary[:300],
                chars=len(paper.summary), text_path=_save(reads_dir, candidate, header, paper.summary))


def _local_now() -> datetime:
    return datetime.now().astimezone()


def read_original(candidate: Candidate, get: fetch.Getter, robots: RobotsCheck, reads_dir: Path,
                  clock: Callable[[], datetime] = _local_now) -> Read:
    stamp = clock().isoformat(timespec="seconds")   # this page's own read time
    if fetch.arxiv_abs_id(candidate.url):
        try:
            return read_abstract(candidate, get, reads_dir, stamp)
        except fetch.FetchError as exc:
            return Read(url=candidate.url, read_at=stamp, ok=False, reason=str(exc)[:200], kind="abstract")
    fail = lambda reason, **kw: Read(url=candidate.url, read_at=stamp, ok=False, reason=reason, **kw)  # noqa: E731
    if fetch.is_blocked(candidate.url):
        return fail("X/Twitter link: not a source")
    try:
        if not robots(candidate.url):
            return fail("robots.txt disallows this page: read it by hand or skip")
        resp = get(candidate.url)
    except fetch.FetchError as exc:
        return fail(str(exc)[:200])
    if resp.status != 200:
        return fail(f"http {resp.status} (paywall / blocked?)", final_url=resp.url)
    if "html" not in resp.content_type.lower():
        return fail(f"not a web page ({resp.content_type or 'unknown type'})", final_url=resp.url)
    page = extract(_decode(resp.body, resp.content_type))
    text = str(page["text"])
    if len(text) < MIN_CHARS:
        return fail(f"only {len(text)} chars of text (JS page / teaser)", final_url=resp.url,
                    page_title=str(page["title"])[:200])
    header = f"# {page['title']}\nURL: {resp.url}\nread_at: {stamp}\npublished: {page['published']}"
    return Read(url=candidate.url, final_url=resp.url, read_at=stamp, ok=True,
                page_title=str(page["title"])[:200], published=str(page["published"]),
                description=str(page["description"])[:300], chars=len(text),
                text_path=_save(reads_dir, candidate, header, text))
