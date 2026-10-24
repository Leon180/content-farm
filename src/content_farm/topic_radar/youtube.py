"""YouTube Data API v3: competitor videos (search.list + videos.list) and viewer questions (commentThreads.list).

API terms followed (https://developers.google.com/youtube/terms/developer-policies):
- official API only, no scraping;
- stored API data is deleted after 30 days (``store.purge_expired``; every output file carries ``youtube_data_expires``);
- quota is counted per call (search 100 units, others 1) and capped by ``budget_units`` (default quota is 10,000/day).

Auth: OAuth refresh token (``CF_YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN``) first; if that cannot read public data
(for example the token only carries the upload scope), ``CF_YOUTUBE_API_KEY``. Secrets are never printed or stored.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from urllib.parse import quote

from content_farm.topic_radar.http import RadarHttp, SourceError
from content_farm.topic_radar.models import Competitor, ViewerQuestion

SEARCH_COST, LIST_COST = 100, 1
SEARCH_TTL = 24 * 3600
LIST_TTL = 12 * 3600
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
PROBE_VIDEO = "dQw4w9WgXcQ"
_QUESTION = re.compile(r"[?？]|為什麼|為何|怎麼|如何|是不是|有沒有|能不能|可不可以|什麼是|是什麼|求|想看|希望")


class QuotaBudgetExceeded(SourceError):
    pass


@dataclass(frozen=True)
class AuthStatus:
    mode: str            # oauth | api_key | none
    ok: bool
    detail: str          # safe to print: reasons such as insufficientPermissions, never a value


@dataclass
class YouTubeAuth:
    mode: str
    token: str = field(default="", repr=False)
    api_key: str = field(default="", repr=False)

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.mode == "oauth" else {}

    def params(self) -> str:
        return f"&key={quote(self.api_key)}" if self.mode == "api_key" else ""


def _error_reason(data: object) -> str:
    if isinstance(data, dict):
        errors = data.get("error", {})
        if isinstance(errors, dict):
            items = errors.get("errors") or [{}]
            return str(items[0].get("reason") or errors.get("status") or errors.get("message", ""))[:80]
        if isinstance(errors, str):
            return errors[:80]
    return "unknown"


def _probe(http: RadarHttp, auth: YouTubeAuth) -> tuple[bool, str]:
    reply = http.get_json(f"{API}/videos?part=id&id={PROBE_VIDEO}{auth.params()}", headers=auth.headers(), ttl=0)
    if reply.status == 200:
        return True, "videos.list answered 200"
    return False, f"videos.list http {reply.status} ({_error_reason(reply.data)})"


def _oauth(http: RadarHttp, client_id: str, client_secret: str, refresh_token: str) -> tuple[YouTubeAuth | None, str]:
    reply = http.post_form(TOKEN_URL, {"client_id": client_id, "client_secret": client_secret,
                                       "refresh_token": refresh_token, "grant_type": "refresh_token"})
    token = reply.data.get("access_token") if isinstance(reply.data, dict) else None
    if reply.status != 200 or not token:
        return None, f"token refresh http {reply.status} ({_error_reason(reply.data)})"
    auth = YouTubeAuth("oauth", token=str(token))
    ok, detail = _probe(http, auth)
    return (auth if ok else None), detail


def build_auth(http: RadarHttp, *, client_id: str, client_secret: str, refresh_token: str,
               api_key: str) -> tuple[YouTubeAuth | None, AuthStatus]:
    """Try OAuth, then the API key. The returned status records why each was or was not used."""
    notes: list[str] = []
    if client_id and client_secret and refresh_token:
        auth, detail = _oauth(http, client_id, client_secret, refresh_token)
        if auth:
            return auth, AuthStatus("oauth", True, detail)
        notes.append(f"oauth unusable: {detail}")
    else:
        notes.append("oauth credentials not set")
    if api_key:
        key_auth = YouTubeAuth("api_key", api_key=api_key)
        ok, detail = _probe(http, key_auth)
        if ok:
            return key_auth, AuthStatus("api_key", True, "; ".join([*notes, detail]))
        notes.append(f"api key unusable: {detail}")
    else:
        notes.append("CF_YOUTUBE_API_KEY not set")
    return None, AuthStatus("none", False, "; ".join(notes))


def extract_questions(comments: list[tuple[str, int]], video_url: str, limit: int = 5) -> list[ViewerQuestion]:
    """Comments that read as a question or a request, most-liked first."""
    seen: set[str] = set()
    found = []
    for text, likes in sorted(comments, key=lambda item: -item[1]):
        clean = " ".join(text.split())
        if not 6 <= len(clean) <= 140 or clean in seen or not _QUESTION.search(clean):
            continue
        seen.add(clean)
        found.append(ViewerQuestion(text=clean, likes=likes, url=video_url))
    return found[:limit]


@dataclass
class YouTubeClient:
    http: RadarHttp
    auth: YouTubeAuth
    budget_units: int = 6000
    units: int = 0

    def _spend(self, cost: int) -> None:
        if self.units + cost > self.budget_units:
            raise QuotaBudgetExceeded(f"youtube budget {self.budget_units} units used up ({self.units} spent)")
        self.units += cost

    def _get(self, path: str, query: str, ttl: float, cost: int) -> dict:
        url = f"{API}/{path}?{query}{self.auth.params()}"
        if not self.http.is_cached(url, ttl):       # a cache hit costs no quota
            self._spend(cost)
        reply = self.http.get_json(url, headers=self.auth.headers(), ttl=ttl)
        if reply.status != 200 or not isinstance(reply.data, dict):
            raise SourceError(f"youtube {path}: http {reply.status} ({_error_reason(reply.data)})")
        return reply.data

    def competitors(self, query: str, limit: int = 5) -> list[Competitor]:
        found = self._get("search", f"part=snippet&type=video&maxResults=15&order=viewCount&regionCode=TW"
                          f"&relevanceLanguage=zh-Hant&q={quote(query)}", SEARCH_TTL, SEARCH_COST)
        ids = [item["id"]["videoId"] for item in found.get("items", []) if item.get("id", {}).get("videoId")]
        if not ids:
            return []
        stats = self._get("videos", f"part=snippet,statistics&id={','.join(ids)}", LIST_TTL, LIST_COST)
        rows = [Competitor(title=item["snippet"]["title"], channel=item["snippet"]["channelTitle"],
                           views=int(item.get("statistics", {}).get("viewCount", 0)),
                           published=item["snippet"]["publishedAt"][:10],
                           url=f"https://www.youtube.com/watch?v={item['id']}")
                for item in stats.get("items", [])]
        return sorted(rows, key=lambda row: -row.views)[:limit]

    def viewer_questions(self, video: Competitor, limit: int = 5) -> list[ViewerQuestion]:
        video_id = video.url.rsplit("=", 1)[-1]
        try:
            data = self._get("commentThreads", f"part=snippet&videoId={video_id}&maxResults=50&order=relevance"
                             "&textFormat=plainText", LIST_TTL, LIST_COST)
        except QuotaBudgetExceeded:
            raise
        except SourceError as exc:
            if "commentsDisabled" in str(exc):
                return []
            raise
        comments = [(item["snippet"]["topLevelComment"]["snippet"]["textDisplay"],
                     int(item["snippet"]["topLevelComment"]["snippet"].get("likeCount", 0)))
                    for item in data.get("items", [])]
        return extract_questions(comments, video.url, limit)


def median_views(videos: list[Competitor]) -> float:
    return float(statistics.median(video.views for video in videos)) if videos else 0.0
