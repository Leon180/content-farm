"""Wikimedia Commons video (webm / ogv) through the public MediaWiki API — no key, one request at a time.

Only the licence the file page itself declares counts (``extmetadata.LicenseShortName``); :func:`parse` keeps the
author (``Artist``, tags stripped), licence name / URL and the file page, and the caller's ``screen`` drops
everything that is not PD / CC0 / CC BY / CC BY-SA. The API asks clients to identify themselves (User-Agent) and to
avoid parallel requests; both are honoured by :class:`FootageClient`.
"""

from __future__ import annotations

import html
import re
from typing import Any

from content_farm.explainer.footage.models import FootageCandidate

API = "https://commons.wikimedia.org/w/api.php"
FILE_PAGE = "https://commons.wikimedia.org/wiki/"
VIDEO_MIMES = ("video/webm", "application/ogg", "video/ogg", "video/mp4")
MAX_ORIGINAL_BYTES = 150 * 1024 * 1024
_META = "LicenseShortName|License|LicenseUrl|Artist|Credit|ImageDescription|Restrictions|Categories|Copyrighted"


def search_params(query: str, limit: int = 15) -> dict[str, Any]:
    return {
        "action": "query", "format": "json", "formatversion": "2", "generator": "search",
        "gsrsearch": f"{query} filetype:video", "gsrnamespace": 6, "gsrlimit": limit,
        "prop": "imageinfo", "iiprop": "url|size|mime|mediatype|extmetadata|timestamp",
        "iiextmetadatafilter": _META,
    }


def title_params(title: str) -> dict[str, Any]:
    name = title if title.lower().startswith("file:") else f"File:{title}"
    return {
        "action": "query", "format": "json", "formatversion": "2", "titles": name,
        "prop": "imageinfo", "iiprop": "url|size|mime|mediatype|extmetadata|timestamp",
        "iiextmetadatafilter": _META,
    }


def file_title_from_url(url: str) -> str | None:
    match = re.search(r"commons\.wikimedia\.org/wiki/(File:[^?#]+)", url)
    return html.unescape(re.sub(r"%20", " ", match.group(1))).replace("_", " ") if match else None


def _strip(text: object) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(text or ""))).split())


def _meta(info: dict, key: str) -> str:
    return _strip((info.get("extmetadata") or {}).get(key, {}).get("value", ""))


def parse(data: dict) -> list[FootageCandidate]:
    out: list[FootageCandidate] = []
    for page in (data.get("query") or {}).get("pages") or []:
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        if info.get("mime") not in VIDEO_MIMES and info.get("mediatype") != "VIDEO":
            continue
        title = str(page.get("title", ""))
        name = title.removeprefix("File:")
        license_name = _meta(info, "LicenseShortName") or _meta(info, "License")
        author = _meta(info, "Artist") or _meta(info, "Credit")
        out.append(FootageCandidate(
            provider="wikimedia",
            provider_id=str(page.get("pageid", "")),
            title=name.rsplit(".", 1)[0],
            page_url=FILE_PAGE + title.replace(" ", "_"),
            download_url=str(info.get("url", "")),
            width=int(info.get("width") or 0),
            height=int(info.get("height") or 0),
            duration=float(info.get("duration") or 0),
            author=author[:160],
            author_url="",
            license_name=license_name,
            license_url=_meta(info, "LicenseUrl"),
            description=_meta(info, "ImageDescription")[:400],
            tags=_meta(info, "Categories").replace("|", ", ")[:200],
            size_bytes=int(info.get("size") or 0),
        ))
    return out


def transcode_url(original: str, height: int = 720) -> str:
    """Commons keeps WebM transcodes next to originals: ``…/commons/a/ab/X.ogv`` → ``…/commons/transcoded/a/ab/X.ogv/X.ogv.720p.vp9.webm``."""
    match = re.match(r"(https://upload\.wikimedia\.org/wikipedia/commons)/([0-9a-f]/[0-9a-f]{2})/([^/]+)$", original)
    if not match:
        return original
    root, folder, name = match.groups()
    return f"{root}/transcoded/{folder}/{name}/{name}.{height}p.vp9.webm"
