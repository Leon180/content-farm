"""Name de-dup via YouTube Data API (search.list type=channel + channels.list statistics). No secret is written."""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from content_farm.production.voice_choice import env_file_defaults

ENV = Path("/Users/lileon/project/content-farm/.env")
OUT = Path("artifacts/brand-kit/name_check.json")
NAMES = {
    "chipcat": ["晶片貓"],
    "cel": ["賽璐璐研究室"],
    "yokai": ["妖怪溯源所"],
    "chipcat-news": ["晶片貓快報"],
    "deepsea": ["深潛日誌", "深海打卡", "潛入深藍"],
    "fable": ["原來如此", "寓言學堂", "先聽個故事"],
}


def call(url: str, data: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=30) as resp:
        return json.load(resp)


def main() -> int:
    env = {**env_file_defaults(ENV), **os.environ}
    token = call("https://oauth2.googleapis.com/token", {
        "client_id": env["CF_YOUTUBE_CLIENT_ID"], "client_secret": env["CF_YOUTUBE_CLIENT_SECRET"],
        "refresh_token": env["CF_YOUTUBE_REFRESH_TOKEN"], "grant_type": "refresh_token"})["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    def get(path: str, **params) -> dict:
        req = urllib.request.Request(f"https://www.googleapis.com/youtube/v3/{path}?" + urllib.parse.urlencode(params), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            return {"error": exc.code, "body": exc.read().decode()[:300]}

    result = {}
    for channel, names in NAMES.items():
        for name in names:
            search = get("search", part="snippet", type="channel", q=name, maxResults=5, regionCode="TW", relevanceLanguage="zh-Hant")
            if "error" in search:
                result[name] = search
                continue
            ids = [item["snippet"]["channelId"] for item in search.get("items", [])]
            stats = get("channels", part="statistics", id=",".join(ids)) if ids else {"items": []}
            subs = {item["id"]: item["statistics"].get("subscriberCount", "hidden") for item in stats.get("items", [])}
            result[name] = [{"title": item["snippet"]["title"], "channelId": item["snippet"]["channelId"],
                             "subscribers": subs.get(item["snippet"]["channelId"]),
                             "url": "https://www.youtube.com/channel/" + item["snippet"]["channelId"]}
                            for item in search.get("items", [])]
            print(name, len(result[name]) if isinstance(result[name], list) else result[name], flush=True)
    OUT.write_text(json.dumps({"channel_of": {n: c for c, ns in NAMES.items() for n in ns}, "results": result},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
