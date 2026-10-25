#!/usr/bin/env python3
"""Fill the "CLIP pick" half of ``artifacts/quality-v5/clip-compare/compare.json``.

For each stock_video slide in compare.json: take the candidates the keyword search already cached
(``<footage cache>/_search``), screen and keyword-rank them exactly as the pipeline does, then re-rank the top ones with the
local CLIP embedder against the slide's narration and cut 5 s of the new first pick. Needs ``CF_CLIP_MODEL_DIR`` (weights) and
``sentence-transformers``; downloads a clip only when the CLIP pick differs and is not cached (free, open-licence hosts).

    CF_CLIP_MODEL_DIR=... PYTHONPATH=src python scripts/clip_compare.py --cache .cache/footage --dir artifacts/quality-v5/clip-compare
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from content_farm.explainer.footage import clip_rank
from content_farm.explainer.footage.client import DEFAULT_ORDER, FootageClient
from content_farm.explainer.stock import relevance_terms


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--min-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)
    embedder = clip_rank.from_env()
    if embedder is None:
        print("CF_CLIP_MODEL_DIR is not set (or not a directory): nothing to compare", file=sys.stderr)
        return 2
    client = FootageClient(cache_dir=args.cache)
    rows = json.loads((args.dir / "compare.json").read_text(encoding="utf-8"))
    for row in rows:
        terms = relevance_terms(row["query"], tuple(row["keywords"]))
        found = [c for p in DEFAULT_ORDER for c in (client._search_cache(p, row["query"]) or [])]  # noqa: SLF001
        good = client._rank(client._screened(found), terms, args.min_seconds)  # noqa: SLF001
        order, record = clip_rank.rerank(good, row["narration"], embedder)
        pick = order[0]
        row["clip_pick"] = {"provider": pick.provider, "provider_id": pick.provider_id, "title": pick.title,
                            "page": pick.page_url, "same_as_keyword_pick": pick.provider_id == str(row["keyword_pick"]["provider_id"]),
                            "ranking": record}
        asset = client._store(row["query"], pick)  # noqa: SLF001
        clip = args.dir / f"{row['slide_id']}-clip-pick.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-t", "5", "-i", str(asset.path), "-an", "-vf",
                        "scale=640:-2", "-c:v", "libx264", "-crf", "28", "-preset", "fast", "-pix_fmt", "yuv420p", str(clip)],
                       check=True)
        row["clip_pick"]["file"] = clip.name
        print(row["slide_id"], "same" if row["clip_pick"]["same_as_keyword_pick"] else "different", pick.title[:50])
    (args.dir / "compare.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
