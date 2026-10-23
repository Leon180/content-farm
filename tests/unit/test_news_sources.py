"""production/news: fetching, ranking, reading originals (no network: fake getters)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from content_farm.production.news import fetch, rank, verify
from content_farm.production.news.models import Candidate, Discussion

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def _cand(cid: str, title: str, url: str, hours_ago: float = 2, points: int | None = 100,
          comments: int | None = 20, site: str = "hn", rank_: int = 1) -> Candidate:
    return Candidate(id=cid, title=title, url=url, domain=fetch.domain_of(url),
                     posted_at=(NOW - timedelta(hours=hours_ago)).isoformat(),
                     discussions=(Discussion(site=site, url=f"https://d/{cid}", points=points,
                                             comments=comments, rank=rank_),))


def _resp(body: bytes | str, status: int = 200, ctype: str = "text/html; charset=utf-8", url: str = "") -> fetch.Response:
    return fetch.Response(url or "https://example.com/a", status, ctype, body.encode() if isinstance(body, str) else body)


# ── polite HTTP ──────────────────────────────────────────────────────────────

def test_polite_http_spaces_requests_per_host() -> None:
    clock = {"t": 0.0}
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    http = fetch.PoliteHttp(sleep=sleep, clock=lambda: clock["t"])
    http._wait("export.arxiv.org")
    http._wait("export.arxiv.org")
    http._wait("hacker-news.firebaseio.com")
    assert sleeps == [pytest.approx(3.0)]     # arXiv: one request every three seconds


def test_x_links_are_never_fetched() -> None:
    http = fetch.PoliteHttp(sleep=lambda s: None)
    with pytest.raises(fetch.FetchError, match="never fetched"):
        http.get("https://x.com/someone/status/1")
    assert fetch.is_blocked("https://mobile.twitter.com/a") and not fetch.is_blocked("https://ax.com.tw/")


# ── sources ─────────────────────────────────────────────────────────────────

def test_hn_item_needs_an_external_url() -> None:
    story = {"id": 7, "type": "story", "title": "T", "url": "https://ex.com/p", "time": 1760000000,
             "score": 50, "descendants": 4}
    cand = fetch.hn_item_candidate(story, 3)
    assert cand is not None and cand.id == "hn-7" and cand.discussions[0].points == 50
    assert fetch.hn_item_candidate({**story, "url": None}, 1) is None          # Ask HN: nothing to read
    assert fetch.hn_item_candidate({**story, "url": "https://x.com/a/status/1"}, 1) is None
    assert fetch.hn_item_candidate({**story, "dead": True}, 1) is None


def test_fetch_hn_merges_top_and_best() -> None:
    items = {1: {"id": 1, "type": "story", "title": "A", "url": "https://a.com/1", "time": 1760000000},
             2: {"id": 2, "type": "story", "title": "B", "url": "https://b.com/2", "time": 1760000000}}

    def get(url: str) -> fetch.Response:
        if url.endswith("topstories.json"):
            return _resp(json.dumps([1, 2]), ctype="application/json")
        if url.endswith("beststories.json"):
            return _resp(json.dumps([2]), ctype="application/json")
        return _resp(json.dumps(items[int(url.rsplit("/", 1)[1].split(".")[0])]), ctype="application/json")

    assert [c.id for c in fetch.fetch_hn(get)] == ["hn-1", "hn-2"]


LOBSTERS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Linus on AI</title><link>https://lore.kernel.org/x</link><guid>https://lobste.rs/s/xiq59t</guid>
<comments>https://lobste.rs/s/xiq59t/linus</comments><pubDate>Fri, 16 Oct 2026 02:50:33 -0000</pubDate>
<category>linux</category></item>
<item><title>No date</title><link>https://a.com</link></item>
</channel></rss>"""

ARXIV = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>http://arxiv.org/abs/2610.01234v2</id><published>2026-10-15T17:00:00Z</published>
<title>A  Chiplet
Interconnect</title><summary>We study ...</summary><category term="cs.AR"/></entry></feed>"""


def test_parse_lobsters_rss() -> None:
    [item] = fetch.parse_lobsters_rss(LOBSTERS)
    assert item.id == "lob-xiq59t" and item.tags == ("linux",) and item.posted_at.startswith("2026-10-16T02:50")


def test_parse_arxiv_atom_keeps_abstract_not_pdf() -> None:
    [paper] = fetch.parse_arxiv_atom(ARXIV)
    assert paper.url == "https://arxiv.org/abs/2610.01234" and paper.title == "A Chiplet Interconnect"
    assert paper.summary == "We study ..." and paper.tags == ("cs.AR",)
    assert fetch.arxiv_abs_id("https://arxiv.org/pdf/2610.01234v3.pdf") == "2610.01234"
    assert fetch.arxiv_abs_id("https://example.com/abs/1") is None


def test_fetch_all_reports_a_failing_source_and_keeps_the_rest() -> None:
    def get(url: str) -> fetch.Response:
        if "lobste.rs" in url:
            return _resp("", status=404)
        if "arxiv" in url:
            return _resp(ARXIV, ctype="application/atom+xml")
        return _resp("[]", ctype="application/json")

    report = fetch.fetch_all(get)
    assert report.counts == {"hn": 0, "lobsters": 0, "arxiv": 1}
    assert len(report.errors) == 1 and report.errors[0].startswith("lobsters")


# ── rank ────────────────────────────────────────────────────────────────────

def test_canonical_url_drops_tracking_and_arxiv_versions() -> None:
    assert rank.canonical_url("http://www.ex.com/a/?utm_source=hn&id=3") == "https://ex.com/a?id=3"
    assert rank.canonical_url("https://arxiv.org/pdf/2610.01234v2.pdf") == "https://arxiv.org/abs/2610.01234"


def test_dedupe_merges_same_story_across_sites() -> None:
    hn = _cand("hn-1", "TSMC opens Arizona fab", "https://ex.com/tsmc?utm_source=x")
    lob = _cand("lob-a", "TSMC opens Arizona fab", "https://www.ex.com/tsmc", site="lobsters", points=None,
                comments=None, hours_ago=5)
    [merged] = rank.dedupe([lob, hn])
    assert merged.id == "hn-1" and {d.site for d in merged.discussions} == {"hn", "lobsters"}
    assert merged.posted_at == lob.posted_at    # earliest sighting


def test_rank_drops_old_and_excluded_and_prefers_taiwan_relevance() -> None:
    items = [_cand("hn-1", "TSMC 2nm yields", "https://a.com/1", points=50),
             _cand("hn-2", "A new static site generator", "https://b.com/2", points=50),
             _cand("hn-3", "Bitcoin hits a record", "https://c.com/3", points=900),
             _cand("hn-4", "TSMC old news", "https://d.com/4", hours_ago=60)]
    ranked = rank.rank(items, NOW)
    assert [r.candidate.id for r in ranked] == ["hn-1", "hn-2"]
    assert ranked[0].relevance == 1.0 and "tsmc" in ranked[0].reasons
    assert ranked[1].relevance == 0.0


def test_freshness_halves_at_the_window_edge() -> None:
    [fresh] = rank.rank([_cand("hn-1", "x", "https://a.com", hours_ago=0)], NOW)
    [old] = rank.rank([_cand("hn-1", "x", "https://a.com", hours_ago=48)], NOW)
    assert fresh.freshness == 1.0 and old.freshness == 0.5


# ── verify ──────────────────────────────────────────────────────────────────

ARTICLE = ("<html><head><title>Raw</title><meta property='og:title' content='Real title'>"
           "<meta property='article:published_time' content='2026-10-16T00:34:03+00:00'>"
           "<meta name='description' content='Short desc'><script>var x='not text'</script></head><body>"
           "<nav>Home About</nav>" + "".join(f"<p>Paragraph {i} with enough words to count as text.</p>" for i in range(30))
           + "</body></html>")


def _robots_ok(url: str) -> bool:
    return True


def test_read_original_records_text_and_read_time(tmp_path: Path) -> None:
    cand = _cand("hn-9", "t", "https://ex.com/a")
    read = verify.read_original(cand, lambda url: _resp(ARTICLE, url=url), _robots_ok, tmp_path,
                                clock=lambda: NOW)
    assert read.ok and read.page_title == "Real title" and read.published.startswith("2026-10-16")
    assert read.read_at == "2026-10-16T12:00:00+00:00"
    text = Path(read.text_path).read_text(encoding="utf-8")
    assert "Paragraph 0" in text and "not text" not in text and "Home About" not in text


@pytest.mark.parametrize(("resp", "reason"), [
    (_resp("", status=403), "http 403"),
    (_resp("%PDF", ctype="application/pdf"), "not a web page"),
    (_resp("<html><body><p>Only a teaser paragraph, nothing else here.</p></body></html>"), "chars of text"),
])
def test_unreadable_originals_are_not_ok(tmp_path: Path, resp: fetch.Response, reason: str) -> None:
    read = verify.read_original(_cand("hn-9", "t", "https://ex.com/a"), lambda url: resp, _robots_ok, tmp_path)
    assert not read.ok and reason in read.reason and read.text_path == ""


def test_robots_disallow_blocks_the_read(tmp_path: Path) -> None:
    calls: list[str] = []

    def get(url: str) -> fetch.Response:
        calls.append(url)
        return _resp("User-agent: *\nDisallow: /private", ctype="text/plain")

    robots = verify.robots_allows(get)
    read = verify.read_original(_cand("hn-9", "t", "https://ex.com/private/a"), get, robots, tmp_path)
    assert not read.ok and "robots" in read.reason
    assert calls == ["https://ex.com/robots.txt"]     # the page itself was never requested


def test_arxiv_link_is_read_through_the_api_abstract(tmp_path: Path) -> None:
    cand = _cand("hn-5", "paper", "https://arxiv.org/pdf/2610.01234v2.pdf")
    long_abstract = ARXIV.replace(b"We study ...", b"We study " + b"chiplets " * 40)
    urls: list[str] = []

    def get(url: str) -> fetch.Response:
        urls.append(url)
        return _resp(long_abstract, ctype="application/atom+xml")

    read = verify.read_original(cand, get, _robots_ok, tmp_path)
    assert read.ok and read.kind == "abstract"
    assert urls == ["https://export.arxiv.org/api/query?id_list=2610.01234"]   # no PDF request


# ── GitHub Trending + response cache (technews, 2026-10-23) ─────────────────

_TRENDING = """<div><article class="Box-row">
<h2 class="h3 lh-condensed"><a href="/acme/rocket"><span class="text-normal">acme /</span> rocket</a></h2>
<p class="col-9 color-fg-muted my-1">A tiny <b>fast</b> inference engine</p>
<div class="f6"><span itemprop="programmingLanguage">Rust</span>
<a href="/acme/rocket/stargazers"><svg></svg> 12,345</a>
<span>1,234 stars today</span></div></article>
<article class="Box-row"><h2><a href="/x/y">x / y</a></h2><div><a href="/x/y/stargazers"><svg></svg> 9</a> 5 stars today</div></article></div>"""


def test_github_trending_rows_become_candidates() -> None:
    from datetime import datetime, timezone

    from content_farm.production.news.fetch import parse_github_trending

    got = parse_github_trending(_TRENDING, datetime(2026, 10, 23, 4, 0, tzinfo=timezone.utc))
    assert [c.id for c in got] == ["gh-acme-rocket", "gh-x-y"]
    first = got[0]
    assert first.url == "https://github.com/acme/rocket" and first.domain == "github.com"
    assert first.title == "acme/rocket: A tiny fast inference engine" and first.tags == ("Rust",)
    assert first.discussions[0].site == "github" and first.discussions[0].points == 1234
    assert first.discussions[0].rank == 1 and got[1].discussions[0].rank == 2


def test_response_cache_answers_a_rerun_without_a_request(tmp_path) -> None:
    from content_farm.production.news.fetch import PoliteHttp, Response

    calls = []

    class Stub(PoliteHttp):
        pass

    http = PoliteHttp(cache_dir=tmp_path, cache_ttl=60, wall=lambda: 1000.0, sleep=lambda _: None)
    http._cache_put("https://lobste.rs/rss", Response("https://lobste.rs/rss", 200, "text/xml", b"<rss/>"))
    got = http.get("https://lobste.rs/rss")
    assert got.body == b"<rss/>" and http.hits == 1 and not calls
    stale = PoliteHttp(cache_dir=tmp_path, cache_ttl=60, wall=lambda: 1100.0)
    assert stale._cache_get("https://lobste.rs/rss") is None           # older than the TTL
    forced = PoliteHttp(cache_dir=tmp_path, cache_ttl=0, wall=lambda: 1000.0)
    assert forced._cache_get("https://lobste.rs/rss") is None          # --refetch ignores the cache
    http._cache_put("https://lobste.rs/x", Response("https://lobste.rs/x", 404, "", b"no"))
    assert http._cache_get("https://lobste.rs/x") is None              # only 200s are cached
