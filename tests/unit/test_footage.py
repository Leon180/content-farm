"""Outside footage (media kind stock_video): licence rules, providers, segment plan, clip build, description text."""

from __future__ import annotations

import json
import shutil
import subprocess

import httpx
import pytest
from pydantic import ValidationError

from content_farm.explainer import ffmpeg_ops
from content_farm.explainer.deck import Media, MediaKind, ReferenceLink
from content_farm.explainer.footage import nasa, noaa, segments, wikimedia
from content_farm.explainer.footage.client import FootageClient
from content_farm.explainer.footage.credits import footage_credits_text, reference_links_text
from content_farm.explainer.footage.models import FootageCandidate, mentions_people, screen
from content_farm.explainer.stock import RateLimiter, StockUnavailable
from content_farm.review.license_rules import classify_license, footage_problems, problems


@pytest.mark.parametrize("name,code,attribution", [
    ("Public domain", "pd", False), ("CC0 1.0", "cc0", False), ("CC BY 4.0", "cc-by", True),
    ("CC BY-SA 3.0", "cc-by-sa", True), ("Pexels License", "pexels", False),
    ("Pixabay Content License", "pixabay", False), ("PD-USGov-NOAA", "pd", False),
    ("Public domain (NASA media usage guidelines)", "pd", False),
])
def test_accepted_licences(name, code, attribution):
    verdict = classify_license(name)
    assert verdict.ok and verdict.code == code and verdict.attribution_required is attribution


@pytest.mark.parametrize("name", [
    "CC BY-NC 4.0", "CC BY-ND 2.0", "CC BY-NC-SA 3.0", "All rights reserved", "Fair use", "", "Standard YouTube License",
    "GFDL", "Third-party rights suspected (copyright)",
])
def test_refused_licences(name):
    assert not classify_license(name).ok


def test_licence_url_can_reveal_nc():
    assert not classify_license("Creative Commons", "https://creativecommons.org/licenses/by-nc/4.0/").ok


def _cand(**kw) -> FootageCandidate:
    base = dict(provider="wikimedia", provider_id="1", title="Deep sea squid", page_url="https://commons.wikimedia.org/wiki/File:S.webm",
                download_url="https://upload.wikimedia.org/x.webm", width=1280, height=720, duration=30, author="NOAA",
                author_url="", license_name="Public domain", license_url="")
    return FootageCandidate(**{**base, **kw})


def test_screen_refuses_nc_missing_author_and_people():
    assert screen(_cand()).ok
    assert not screen(_cand(license_name="CC BY-NC 4.0")).ok
    assert not screen(_cand(author="")).ok
    refused = screen(_cand(title="Scientist talking about squid"))
    assert not refused.ok and "避臉" in refused.reason
    assert screen(_cand(title="Portuguese man o' war drifting")).ok


def test_mentions_people():
    assert mentions_people("diver and crew") == ("crew", "diver")
    assert mentions_people("giant squid") == ()


def test_wikimedia_parse_strips_html_and_keeps_licence():
    data = {"query": {"pages": [{"pageid": 7, "title": "File:Ex1402 squid.webm", "imageinfo": [{
        "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Ex1402_squid.webm", "mime": "video/webm",
        "width": 1280, "height": 720, "duration": 41.5, "size": 1000,
        "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}, "LicenseUrl": {"value": "https://cc/by-sa"},
                        "Artist": {"value": "<a href=\"x\">Jane &amp; Co</a>"}}}]}]}}
    (c,) = wikimedia.parse(data)
    assert (c.author, c.license_name, c.duration) == ("Jane & Co", "CC BY-SA 4.0", 41.5)
    assert c.page_url == "https://commons.wikimedia.org/wiki/File:Ex1402_squid.webm"
    assert wikimedia.file_title_from_url(c.page_url) == "File:Ex1402 squid.webm"
    assert wikimedia.transcode_url(c.download_url).endswith("/transcoded/a/ab/Ex1402_squid.webm/Ex1402_squid.webm.720p.vp9.webm")


def test_nasa_parse_rejects_third_party_and_picks_file():
    ok = {"data": [{"nasa_id": "A1", "title": "Ocean worlds", "description": "NASA footage", "center": "JPL", "media_type": "video"}],
          "href": "https://images-assets.nasa.gov/video/A1/collection.json"}
    bad = {"data": [{"nasa_id": "B2", "title": "Storm", "description": "© Getty Images", "media_type": "video"}], "href": "h"}
    good, refused = nasa.parse({"collection": {"items": [ok, bad]}})
    assert screen(good).ok and "JPL" in good.author
    assert not screen(refused).ok
    files = ["http://x/A1~preview.mp4", "http://x/A1~medium.mp4", "http://x/A1~orig.mp4", "http://x/A1.srt"]
    assert nasa.pick_file(files) == "https://x/A1~orig.mp4"
    assert nasa.pick_file(["http://x/A1.srt"]) is None


NOAA_OK = "<html><title>Squid Dive - NOAA Ocean Exploration</title><body><p>Video courtesy of NOAA Ocean Exploration.</p><video><source src='/v/dive.mp4'></video></body></html>"
NOAA_THIRD = NOAA_OK.replace("NOAA Ocean Exploration.</p>", "Edie Widder and Nathan Robinson.</p>").replace("Video courtesy of Edie", "Video courtesy of Edie")


def test_noaa_page_scan():
    c = noaa.scan_page(NOAA_OK, "https://oceanexplorer.noaa.gov/x/")
    assert c.download_url == "https://oceanexplorer.noaa.gov/v/dive.mp4" and screen(c).ok and c.title == "Squid Dive"
    with pytest.raises(noaa.PageRefused, match="第三方"):
        noaa.scan_page(NOAA_THIRD, "https://oceanexplorer.noaa.gov/x/")
    with pytest.raises(noaa.PageRefused, match="noaa.gov"):
        noaa.scan_page(NOAA_OK, "https://example.com/x/")
    with pytest.raises(noaa.PageRefused, match="明確"):
        noaa.scan_page("<p>some page</p><video src='a.mp4'></video>", "https://oceanexplorer.noaa.gov/y/")


def test_segment_plan():
    assert segments.segment_count(8) == 1 and segments.segment_count(8.1) == 2 and segments.segment_count(20) == 3
    (seg,) = segments.plan(60, 6)
    assert seg.length == 6 and 0.5 <= seg.start <= 53.5
    many = segments.plan(120, 20)
    assert len(many) == 3 and all(3 <= s.length <= 8 for s in many) and many == sorted(many, key=lambda s: s.start)
    assert segments.plan(2, 10) == [segments.Segment(0.0, 2)]      # shorter source: whole clip, caller slows or loops
    assert segments.plan(60, 5, start=10) == [segments.Segment(10, 5)]


def test_segment_plan_prefers_motion():
    motion = [0.0] * 60
    for i in range(40, 46):
        motion[i] = 9.0
    (seg,) = segments.plan(60, 6, motion)
    assert 38 <= seg.start <= 41
    chosen = segments.plan(60, 12, motion)
    assert len(chosen) == 2 and chosen[1].start - chosen[0].start >= chosen[0].length


def test_footage_problems_sidecar_label_and_attribution(tmp_path):
    entry = {"slide_id": "s1", "kind": "stock_video", "provider": "wikimedia", "author": "Jane", "license": "CC BY 4.0",
             "source_url": "https://commons/x", "retrieved_at": "2026-10-24", "label": "影像：Jane", "label_burned": True,
             "sidecar": "assets/footage/s1.sidecar.json"}
    assert footage_problems(entry, "see https://commons/x") == []
    assert any("說明欄" in p for p in footage_problems(entry, "nothing here"))
    assert any("sidecar 檔不存在" in p for p in footage_problems(entry, "https://commons/x", tmp_path))
    assert any("來源標示" in p for p in footage_problems({**entry, "label_burned": False}, "https://commons/x"))
    assert any("sidecar 缺" in p for p in footage_problems({**entry, "author": ""}, "https://commons/x"))
    assert any("NC" in p for p in footage_problems({**entry, "license": "CC BY-NC 4.0"}, "https://commons/x"))
    path = tmp_path / entry["sidecar"]
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    assert footage_problems(entry, "https://commons/x", tmp_path) == []


def test_problems_whitelists_stock_video_kind():
    credits = {"entries": [{"slide_id": "s1", "kind": "stock_video", "provider": "nasa", "author": "NASA", "license": "Public domain",
                            "source_url": "https://images.nasa.gov/details/A1", "retrieved_at": "2026-10-24", "label": "影像：NASA",
                            "label_burned": True}], "pending": [], "description_text": ""}
    assert problems(credits) == []
    assert problems({**credits, "entries": [{**credits["entries"][0], "kind": "mystery"}]})


def test_deck_media_validation():
    Media(kind=MediaKind.STOCK_VIDEO, query="giant squid", url="https://commons.wikimedia.org/wiki/File:X.webm", start=3.0)
    with pytest.raises(ValidationError):
        Media(kind=MediaKind.STOCK_VIDEO)            # query required
    with pytest.raises(ValidationError):
        Media(kind=MediaKind.AI_IMAGE, prompt="x", url="https://a.b/c")
    with pytest.raises(ValidationError):
        ReferenceLink(title="t", url="not a url", note="n")


def test_description_blocks():
    entries = [{"kind": "stock_video", "source_url": "https://commons/x", "author": "Jane", "title": "Squid", "provider": "wikimedia",
                "license": "CC BY-SA 4.0", "license_url": "https://cc/by-sa", "attribution_required": True, "share_alike": True}]
    text = footage_credits_text(entries)
    assert "Jane〈Squid〉" in text and "https://cc/by-sa" in text and "https://commons/x" in text
    links = [ReferenceLink(title="2019 Gulf of Mexico", url="https://oceanexplorer.noaa.gov/a", note="Medusa 拍到的大王烏賊")]
    ref = reference_links_text(links)
    assert ref.startswith("延伸觀看") and "https://oceanexplorer.noaa.gov/a" in ref and "Medusa" in ref
    assert footage_credits_text([]) == "" and reference_links_text([]) == ""


def test_credits_text_puts_references_after_credits():
    from content_farm.explainer.media_run import credits_text

    entries = [{"kind": "stock_video", "source_url": "https://commons/x", "author": "NOAA", "provider": "wikimedia",
                "license": "Public domain"}]
    links = [ReferenceLink(title="T", url="https://e.com/v", note="n")]
    out = credits_text(entries, links)
    assert out.index("外部影像素材") < out.index("延伸觀看")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_footage_to_clip_is_silent_and_exact_length(tmp_path):
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=24:duration=10", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=10", "-shortest", str(src)], capture_output=True, check=True)
    out, mode = ffmpeg_ops.footage_to_clip(src, [(1, 3), (5, 3)], None, tmp_path / "o.mp4", 6)
    info = ffmpeg_ops.probe(out)
    assert mode == "trim" and (info["width"], info["height"]) == (1920, 1080) and abs(info["duration"] - 6) < 0.1
    streams = json.loads(subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(out)],
                                        capture_output=True, text=True, check=True).stdout)["streams"]
    assert [s["codec_type"] for s in streams] == ["video"]
    _, loop_mode = ffmpeg_ops.footage_to_clip(src, [(0, 2)], None, tmp_path / "l.mp4", 9)
    assert loop_mode == "loop"


def _transport(routes: dict[str, httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, response in routes.items():
            if str(request.url).startswith(prefix):
                return response
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_client_picks_licensed_clip_downloads_once_and_writes_sidecar(tmp_path):
    data = {"query": {"pages": [
        {"pageid": 1, "title": "File:Squid NC.webm", "imageinfo": [{"url": "https://upload.wikimedia.org/a/ab/nc.webm", "mime": "video/webm",
            "width": 1280, "height": 720, "duration": 20, "extmetadata": {"LicenseShortName": {"value": "CC BY-NC 4.0"}, "Artist": {"value": "A"}}}]},
        {"pageid": 2, "title": "File:Squid PD.webm", "imageinfo": [{"url": "https://upload.wikimedia.org/a/ab/pd.webm", "mime": "video/webm",
            "width": 1280, "height": 720, "duration": 20, "extmetadata": {"LicenseShortName": {"value": "Public domain"}, "Artist": {"value": "NOAA"}}}]}]}}
    hits = []
    transport = _transport({"https://commons.wikimedia.org/w/api.php": httpx.Response(200, json=data),
                            "https://upload.wikimedia.org/a/ab/pd.webm": httpx.Response(200, content=b"video-bytes")})
    http = httpx.Client(transport=httpx.MockTransport(lambda r: (hits.append(str(r.url)), transport.handle_request(r))[1]))
    client = FootageClient(cache_dir=tmp_path, order=("wikimedia",), http=http, limiter=RateLimiter(0, sleep=lambda s: None))
    asset = client.fetch("squid", 6)
    assert asset.candidate.provider_id == "2" and asset.path.read_bytes() == b"video-bytes" and not asset.from_cache
    side = json.loads(asset.sidecar_path.read_text())
    assert (side["author"], side["license_code"], side["source_url"]) == ("NOAA", "pd", asset.candidate.page_url)
    assert side["retrieved_at"] and any("nc" in r.lower() or "NC" in r for r in client.refusals)
    before = len(hits)
    again = client.fetch("squid", 6)
    assert again.from_cache and len(hits) == before          # search and file both come from the cache


def test_client_no_licensed_result_is_unavailable(tmp_path):
    data = {"query": {"pages": [{"pageid": 1, "title": "File:Squid.webm", "imageinfo": [{"url": "u", "mime": "video/webm", "width": 1, "height": 1,
            "extmetadata": {"LicenseShortName": {"value": "All rights reserved"}, "Artist": {"value": "A"}}}]}]}}
    http = httpx.Client(transport=_transport({"https://commons.wikimedia.org/w/api.php": httpx.Response(200, json=data)}))
    client = FootageClient(cache_dir=tmp_path, order=("wikimedia",), http=http, limiter=RateLimiter(0, sleep=lambda s: None))
    with pytest.raises(StockUnavailable, match="no licensed"):
        client.fetch("squid", 5)


def test_client_pinned_url_must_be_known_host(tmp_path):
    client = FootageClient(cache_dir=tmp_path, http=httpx.Client(transport=_transport({})))
    with pytest.raises(StockUnavailable, match="pinned footage url"):
        client.fetch("squid", 5, url="https://www.youtube.com/watch?v=abc")


def test_segment_window_and_label_notes():
    inside = segments.plan(100, 12, None, start=20, end=50)
    assert len(inside) == 2 and all(20 <= s.start and s.start + s.length <= 50 for s in inside)
    assert segments.plan(100, 5, None, start=10, end=12)[0].start == 10      # tiny window: use it whole
    with pytest.raises(ValueError):
        segments.plan(100, 5, None, start=60, end=50)
    with pytest.raises(ValidationError):
        Media(kind=MediaKind.STOCK_VIDEO, query="q", start=10, end=5)
    with pytest.raises(ValidationError):
        Media(kind=MediaKind.AI_IMAGE, prompt="p", footage_note="x")


def test_screen_labels():
    pd = _cand(author="NOAA Office of Ocean Exploration and Research")
    assert pd.screen_label == "影像：NOAA Ocean Exploration / Wikimedia Commons"
    by = _cand(author="Jozée Sarrazin", license_name="CC BY 4.0")
    assert by.screen_label == "影像：Jozée Sarrazin / Wikimedia Commons（CC BY）"
    assert _cand(provider="nasa", author="NASA JPL").screen_label == "影像：NASA"
    assert _cand(provider="pexels", author="Ann", license_name="Pexels License").screen_label == "影像：Ann / Pexels"
