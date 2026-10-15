"""Look up YouTube channel-search results for candidate names (collision check).

Reads ytInitialData from the public results page (channel filter) and prints
channel titles / handles / subscriber text. Output JSON to argv[1].
"""
import json
import re
import sys
import urllib.parse
import urllib.request

NAMES = sys.argv[2:]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def walk(node, out):
    if isinstance(node, dict):
        if "channelRenderer" in node:
            r = node["channelRenderer"]
            out.append({
                "title": r.get("title", {}).get("simpleText", ""),
                "handle": r.get("subscriberCountText", {}).get("simpleText", ""),
                "subs": r.get("videoCountText", {}).get("simpleText", ""),
            })
        for v in node.values():
            walk(v, out)
    elif isinstance(node, list):
        for v in node:
            walk(v, out)


def search(name):
    q = urllib.parse.quote(name)
    url = f"https://www.youtube.com/results?search_query={q}&sp=EgIQAg%253D%253D&hl=zh-TW&gl=TW"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})
    html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html)
    if not m:
        return {"error": "no ytInitialData", "len": len(html)}
    out = []
    walk(json.loads(m.group(1)), out)
    return out[:8]


results = {}
for name in NAMES:
    try:
        results[name] = search(name)
    except Exception as exc:  # report, don't hide
        results[name] = {"error": repr(exc)}
    print(name, json.dumps(results[name], ensure_ascii=False), flush=True)
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(results, fh, ensure_ascii=False, indent=2)
