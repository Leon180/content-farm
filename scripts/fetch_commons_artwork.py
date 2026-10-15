"""Find and download public-domain artwork from Wikimedia Commons, with provenance.

Usage:
    python scripts/fetch_commons_artwork.py search "Tamamo-no-Mae Sekien"
    python scripts/fetch_commons_artwork.py fetch --run-dir output/kyubi --id tamamo \\
        --file "File:SekienTamamo-no-Mae.jpg" --caption "鳥山石燕〈玉藻前〉1779" \\
        --title "玉藻前（今昔畫圖續百鬼）" --artist "鳥山石燕" --date "1779"

``fetch`` reads licence, licence URL, author and credit line from the Commons
API (``extmetadata``), refuses anything that is not public domain / CC0, saves
a ≤2400 px rendition into ``<run-dir>/assets/artwork/`` and upserts the entry
in ``artwork.json`` (validated by :class:`ArtworkEntry`). The raw API metadata
is kept next to it as ``<id>.commons.json`` so the licence claim is auditable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from content_farm.explainer.artwork import ARTWORK_DIR, ARTWORK_MANIFEST, ArtworkEntry

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "content-farm-artwork/0.1 (https://github.com/Leon180/content-farm; research use)"
PD_LICENCE = re.compile(r"public domain|^pd\b|cc0", re.IGNORECASE)
PD_MARK_URL = "https://creativecommons.org/publicdomain/mark/1.0/"
WIDTH = 2400


def _get(params: dict[str, str]) -> dict:
    url = f"{API}?{urllib.parse.urlencode({**params, 'format': 'json'})}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def image_info(file_title: str) -> dict:
    data = _get({"action": "query", "titles": file_title, "prop": "imageinfo",
                 "iiprop": "url|extmetadata|size|mime", "iiurlwidth": str(WIDTH)})
    page = next(iter(data["query"]["pages"].values()))
    if "imageinfo" not in page:
        raise ValueError(f"{file_title}: not found on Commons")
    return {"title": page["title"], **page["imageinfo"][0]}


def _meta(info: dict, key: str) -> str:
    return _plain(info.get("extmetadata", {}).get(key, {}).get("value", ""))


def cmd_search(args: argparse.Namespace) -> int:
    data = _get({"action": "query", "list": "search", "srsearch": args.query, "srnamespace": "6",
                 "srlimit": str(args.limit)})
    for hit in data["query"]["search"]:
        info = image_info(hit["title"])
        print(f"{hit['title']}\n    {info['width']}x{info['height']}  "
              f"licence={_meta(info, 'LicenseShortName')!r}  artist={_meta(info, 'Artist')[:60]!r}  "
              f"date={_meta(info, 'DateTimeOriginal')[:40]!r}")
    return 0


def _download(url: str, out: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        out.write_bytes(response.read())


def cmd_fetch(args: argparse.Namespace) -> int:
    info = image_info(args.file)
    licence = _meta(info, "LicenseShortName")
    if not PD_LICENCE.search(licence):
        raise ValueError(f"{args.file}: licence {licence!r} is not public domain / CC0")
    licence_url = _meta(info, "LicenseUrl") or PD_MARK_URL
    folder = args.run_dir / ARTWORK_DIR
    folder.mkdir(parents=True, exist_ok=True)
    source = info.get("thumburl") or info["url"]
    suffix = Path(urllib.parse.urlparse(source).path).suffix.lower() or ".jpg"
    filename = f"{args.id}{suffix}"
    entry = ArtworkEntry(
        file=filename, title=args.title, artist=args.artist, date=args.date,
        institution=args.institution or f"Wikimedia Commons（{_meta(info, 'Credit')[:80] or '來源見頁面'}）",
        object_id=info["title"], license=licence, license_url=licence_url,
        source_url=info["descriptionurl"], caption=args.caption, note=args.note,
    )
    _download(source, folder / filename)
    (folder / f"{args.id}.commons.json").write_text(json.dumps(info, ensure_ascii=False, indent=2),
                                                    encoding="utf-8")
    manifest_path = folder / ARTWORK_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    manifest = {**manifest, args.id: entry.model_dump()}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{args.id}: {filename} ← {info['descriptionurl']} ({licence})")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=8)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--run-dir", type=Path, required=True)
    fetch.add_argument("--id", required=True)
    fetch.add_argument("--file", required=True, help='Commons title, e.g. "File:X.jpg"')
    fetch.add_argument("--title", required=True)
    fetch.add_argument("--artist", required=True)
    fetch.add_argument("--date", required=True)
    fetch.add_argument("--caption", required=True)
    fetch.add_argument("--institution", default="", help="holding museum, if Commons names one")
    fetch.add_argument("--note", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return {"search": cmd_search, "fetch": cmd_fetch}[args.command](args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
