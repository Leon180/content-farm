"""Stock B-roll client: parsing, ranking, cache, rate limits — all over a mock transport."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from content_farm.explainer.stock import (
    MIN_WIDTH,
    PEXELS_SEARCH,
    PIXABAY_SEARCH,
    RateLimiter,
    StockClient,
    StockUnavailable,
    cache_key,
    credit_entry,
    parse_pexels,
    parse_pixabay,
    rank,
)


def pexels_video(vid: int = 1, duration: int = 20, files: list[dict] | None = None) -> dict:
    return {
        "id": vid, "url": f"https://www.pexels.com/video/x-{vid}/", "duration": duration,
        "user": {"name": "Ann Shooter", "url": "https://www.pexels.com/@ann"},
        "video_files": files if files is not None else [
            {"quality": "hd", "width": 3840, "height": 2160, "link": f"https://videos.pexels.com/{vid}-4k.mp4"},
            {"quality": "hd", "width": 1920, "height": 1080, "link": f"https://videos.pexels.com/{vid}-1080.mp4"},
            {"quality": "sd", "width": 960, "height": 540, "link": f"https://videos.pexels.com/{vid}-540.mp4"},
        ],
    }


def pixabay_hit(hid: int = 7, duration: int = 15) -> dict:
    return {
        "id": hid, "pageURL": f"https://pixabay.com/videos/x-{hid}/", "duration": duration,
        "user": "bob", "user_id": 42,
        "videos": {
            "large": {"url": f"https://cdn.pixabay.com/{hid}-large.mp4", "width": 3840, "height": 2160},
            "medium": {"url": f"https://cdn.pixabay.com/{hid}-medium.mp4", "width": 1920, "height": 1080},
            "small": {"url": f"https://cdn.pixabay.com/{hid}-small.mp4", "width": 1280, "height": 720},
        },
    }


class Recorder:
    """httpx.MockTransport handler with canned responses and a call log."""

    def __init__(self, pexels: dict | None = None, pixabay: dict | None = None,
                 pexels_status: int = 200, headers: dict | None = None) -> None:
        self.calls: list[httpx.Request] = []
        self.pexels = pexels if pexels is not None else {"videos": [pexels_video()]}
        self.pixabay = pixabay if pixabay is not None else {"hits": [pixabay_hit()]}
        self.pexels_status = pexels_status
        self.headers = headers or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        url = str(request.url)
        if url.startswith(PEXELS_SEARCH):
            return httpx.Response(self.pexels_status, json=self.pexels, headers=self.headers)
        if url.startswith(PIXABAY_SEARCH):
            return httpx.Response(200, json=self.pixabay)
        return httpx.Response(200, content=b"\x00" * 2048)  # file download

    def searches(self) -> list[httpx.Request]:
        return [c for c in self.calls if "search" in str(c.url) or "api/videos" in str(c.url)]


def client(tmp_path: Path, rec: Recorder, *, pexels: str = "pk", pixabay: str = "xk",
           limiter: RateLimiter | None = None) -> StockClient:
    return StockClient(
        pexels_key=pexels, pixabay_key=pixabay, cache_dir=tmp_path / "cache",
        http=httpx.Client(transport=httpx.MockTransport(rec)),
        limiter=limiter or RateLimiter(min_interval=0, sleep=lambda s: None),
    )


class TestParsing:
    def test_pexels_picks_smallest_full_hd_file_and_credits(self) -> None:
        [c] = parse_pexels({"videos": [pexels_video()]})
        assert c.download_url.endswith("1-1080.mp4") and (c.width, c.height) == (1920, 1080)
        assert c.author == "Ann Shooter" and c.author_url.endswith("@ann")
        assert c.page_url == "https://www.pexels.com/video/x-1/"
        assert c.license_name == "Pexels License"

    def test_pexels_skips_portrait_and_tiny(self) -> None:
        portrait = pexels_video(files=[{"width": 1080, "height": 1920, "link": "p.mp4"}])
        tiny = pexels_video(vid=2, files=[{"width": 640, "height": 360, "link": "t.mp4"}])
        nulls = pexels_video(vid=3, files=[{"width": None, "height": None, "link": "n.mp4"}])
        assert parse_pexels({"videos": [portrait, tiny, nulls]}) == []

    def test_pixabay_prefers_1080_over_4k_and_builds_profile_url(self) -> None:
        [c] = parse_pixabay({"hits": [pixabay_hit()]})
        assert c.download_url.endswith("7-medium.mp4")
        assert c.author_url == "https://pixabay.com/users/bob-42/"
        assert c.license_name == "Pixabay Content License"

    def test_pixabay_falls_back_to_720(self) -> None:
        hit = pixabay_hit()
        hit["videos"]["large"] = {"url": "", "width": 0, "height": 0}
        hit["videos"]["medium"] = {"url": "", "width": 0, "height": 0}
        [c] = parse_pixabay({"hits": [hit]})
        assert c.width == MIN_WIDTH

    def test_rank_full_hd_then_long_enough(self) -> None:
        short_hd, long_hd = parse_pexels({"videos": [pexels_video(1, 4), pexels_video(2, 30)]})
        [hd720] = parse_pixabay({"hits": [{**pixabay_hit(9, 60), "videos": {
            "small": {"url": "s.mp4", "width": 1280, "height": 720}}}]})
        assert [c.provider_id for c in rank([short_hd, hd720, long_hd], 20)] == ["2", "1", "9"]

    def test_cache_key_normalises(self) -> None:
        assert cache_key("Wafer  Fab") == cache_key("wafer fab")
        assert cache_key("wafer fab") != cache_key("wafer fab line")
        assert cache_key("晶圓").startswith("q-")


class TestClient:
    def test_pexels_first_download_and_credit(self, tmp_path: Path) -> None:
        rec = Recorder()
        asset = client(tmp_path, rec).fetch("wafer fab", 10)
        assert asset.candidate.provider == "pexels" and not asset.from_cache
        assert asset.path.read_bytes() == b"\x00" * 2048
        search, download = rec.calls
        assert search.headers["Authorization"] == "pk"
        assert search.url.params["orientation"] == "landscape"
        assert "Authorization" not in download.headers  # key only goes to the API
        credit = credit_entry(asset, "s01", 1)
        assert credit["source_url"].startswith("https://www.pexels.com/video/")
        assert credit["author"] == "Ann Shooter" and credit["license_url"].endswith("/license/")

    def test_same_query_is_served_from_cache(self, tmp_path: Path) -> None:
        rec = Recorder()
        client(tmp_path, rec).fetch("wafer fab", 10)
        again = client(tmp_path, rec).fetch("Wafer Fab", 10)
        assert again.from_cache and len(rec.calls) == 2  # nothing new

    def test_cache_hit_needs_no_key(self, tmp_path: Path) -> None:
        rec = Recorder()
        client(tmp_path, rec).fetch("wafer fab", 10)
        assert client(tmp_path, rec, pexels="", pixabay="").fetch("wafer fab", 10).from_cache

    def test_pixabay_when_pexels_has_nothing(self, tmp_path: Path) -> None:
        rec = Recorder(pexels={"videos": []})
        asset = client(tmp_path, rec).fetch("chip", 10)
        assert asset.candidate.provider == "pixabay"
        pixabay_search = rec.searches()[1]
        assert pixabay_search.url.params["key"] == "xk"
        assert pixabay_search.url.params["safesearch"] == "true"

    def test_unavailable_lists_every_reason(self, tmp_path: Path) -> None:
        rec = Recorder(pexels={"videos": []}, pixabay={"hits": []})
        with pytest.raises(StockUnavailable, match="pexels: no landscape.*pixabay: no landscape"):
            client(tmp_path, rec).fetch("nothing", 10)

    def test_no_keys(self, tmp_path: Path) -> None:
        rec = Recorder()
        with pytest.raises(StockUnavailable, match="no Pexels/Pixabay API key"):
            client(tmp_path, rec, pexels="", pixabay="").fetch("x", 5)
        assert rec.calls == []

    def test_http_error_falls_through_to_pixabay(self, tmp_path: Path) -> None:
        rec = Recorder(pexels_status=500)
        assert client(tmp_path, rec).fetch("x", 5).candidate.provider == "pixabay"

    def test_429_stops_further_pexels_calls(self, tmp_path: Path) -> None:
        rec = Recorder(pexels_status=429, pixabay={"hits": []})
        stock = client(tmp_path, rec)
        with pytest.raises(StockUnavailable, match="429"):
            stock.fetch("a", 5)
        with pytest.raises(StockUnavailable, match="pexels rate limit reached"):
            stock.fetch("b", 5)
        pexels_calls = [c for c in rec.calls if str(c.url).startswith(PEXELS_SEARCH)]
        assert len(pexels_calls) == 1

    def test_remaining_zero_header_stops_next_call(self, tmp_path: Path) -> None:
        rec = Recorder(headers={"X-Ratelimit-Remaining": "0", "X-Ratelimit-Reset": "1760000000"})
        stock = client(tmp_path, rec)
        stock.fetch("a", 5)  # this response is still used
        asset = stock.fetch("b", 5)
        assert asset.candidate.provider == "pixabay"

    def test_corrupt_cache_is_refetched(self, tmp_path: Path) -> None:
        rec = Recorder()
        first = client(tmp_path, rec).fetch("x", 5)
        (first.path.parent / "meta.json").write_text("{not json")
        assert not client(tmp_path, rec).fetch("x", 5).from_cache
        meta = json.loads((first.path.parent / "meta.json").read_text())
        assert meta["candidate"]["provider"] == "pexels"


class TestRateLimiter:
    def test_spaces_calls(self) -> None:
        now = [100.0]
        slept: list[float] = []
        limiter = RateLimiter(min_interval=1.0, clock=lambda: now[0], sleep=slept.append)
        limiter.wait("pexels")
        now[0] += 0.25
        limiter.wait("pexels")
        limiter.wait("pixabay")  # separate provider, no wait
        assert slept == [pytest.approx(0.75)]

    def test_per_run_budget(self) -> None:
        limiter = RateLimiter(min_interval=0, max_calls=2, sleep=lambda s: None)
        limiter.wait("pexels")
        limiter.wait("pexels")
        with pytest.raises(StockUnavailable, match="budget"):
            limiter.wait("pexels")


@pytest.mark.skipif(not os.environ.get("CF_PEXELS_API_KEY"), reason="needs CF_PEXELS_API_KEY")
def test_live_pexels_search_returns_landscape_full_hd(tmp_path: Path) -> None:
    """Integration: one real search (no download) to catch API shape drift."""
    stock = StockClient(pexels_key=os.environ["CF_PEXELS_API_KEY"], pixabay_key="",
                        cache_dir=tmp_path)
    found = stock._search("pexels", "semiconductor")
    assert found, "Pexels returned no usable landscape video for 'semiconductor'"
    assert all(c.width >= MIN_WIDTH and c.width > c.height for c in found)
    assert all(c.page_url.startswith("https://www.pexels.com/") and c.author for c in found)
