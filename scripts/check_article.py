"""Check an explainer run's article.md / sources.json (and deck_outline.json if present).

Usage:
    python scripts/check_article.py --run-dir output/<run>

Checks: sources.json entries are valid deck ``Source`` objects with an
``accessed=`` date and an http(s) URL; every ``[src:id]`` in the article exists;
every source is cited; article body length; required anchors; every line of
the article holding a digit cites a source; every outline slide points at an
existing article anchor and known source ids; a "N 類：a、b、c" sentence lists N items;
story_spine.json (when present, or always with --require-spine) fits the article.

Exit codes: 0 ok, 1 problems found (all listed), 2 missing files.
No network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from pydantic import ValidationError

from content_farm.explainer.deck import Source
from content_farm.review.story_spine import SPINE_FILE, check_quantifiers, check_spine

ARTICLE_MIN_CHARS = 2500
ARTICLE_MAX_CHARS = 4000
REQUIRED_ANCHORS = (
    "a-timeline", "a-numbers", "a-chain", "a-taiwan", "a-unknowns", "a-gossip", "a-jokes",
)
APPENDIX_MARKER = "{#a-gossip}"

_CITE = re.compile(r"\[src:([\w.-]+)\]")
_ANCHOR = re.compile(r"\{#(a-[\w-]+)\}")
_ACCESSED = re.compile(r"accessed=\d{4}-\d{2}-\d{2}")
_DIGIT = re.compile(r"\d")
_STRIP_FOR_DIGITS = re.compile(r"\[src:[\w.-]+\]|\{#a-[\w-]+\}|https?://\S+")


def body_chars(article: str) -> int:
    """Visible characters before the appendices, ignoring citations and markup."""
    body = article.split(APPENDIX_MARKER)[0]
    body = _CITE.sub("", _ANCHOR.sub("", body))
    return len(re.sub(r"[\s#>|*`\-]", "", body))


def check_sources(raw: object) -> tuple[list[str], set[str]]:
    problems: list[str] = []
    if not isinstance(raw, list):
        return ["sources.json must be a JSON array"], set()
    ids: set[str] = set()
    for index, entry in enumerate(raw):
        try:
            source = Source.model_validate(entry)
        except ValidationError as exc:
            problems.append(f"source #{index}: {exc.errors()[0]['msg']}")
            continue
        if source.id in ids:
            problems.append(f"source {source.id!r}: duplicate id")
        ids.add(source.id)
        if not source.url.startswith(("http://", "https://")):
            problems.append(f"source {source.id!r}: url must be http(s)")
        if not _ACCESSED.search(source.note):
            problems.append(f"source {source.id!r}: note lacks accessed=YYYY-MM-DD")
    return problems, ids


def check_article(article: str, ids: set[str]) -> tuple[list[str], set[str]]:
    problems: list[str] = []
    cited = set(_CITE.findall(article))
    problems += [f"article cites unknown source {sid!r}" for sid in sorted(cited - ids)]
    problems += [f"source {sid!r} is never cited" for sid in sorted(ids - cited)]
    n = body_chars(article)
    if not ARTICLE_MIN_CHARS <= n <= ARTICLE_MAX_CHARS:
        problems.append(f"article body has {n} chars; target {ARTICLE_MIN_CHARS}-{ARTICLE_MAX_CHARS}")
    anchors = set(_ANCHOR.findall(article))
    problems += [f"article lacks section anchor {{#{a}}}" for a in REQUIRED_ANCHORS if a not in anchors]
    for number, line in enumerate(article.splitlines(), start=1):
        if line.lstrip().startswith(("#", ">")):
            continue
        if _DIGIT.search(_STRIP_FOR_DIGITS.sub("", line)) and not _CITE.search(line):
            problems.append(f"article line {number}: has a number but no [src:…]")
    problems += check_quantifiers(article)
    return problems, anchors


def check_outline(outline: dict, anchors: set[str], ids: set[str]) -> list[str]:
    problems: list[str] = []
    for section in outline.get("sections", []):
        for slide in section.get("slides", []):
            sid = slide.get("id", "?")
            refs = slide.get("article_refs") or []
            if not refs:
                problems.append(f"outline slide {sid}: no article_refs")
            problems += [f"outline slide {sid}: unknown anchor {r!r}" for r in refs if r not in anchors]
            problems += [
                f"outline slide {sid}: unknown source {s!r}"
                for s in slide.get("source_ids", []) if s not in ids
            ]
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--require-spine", action="store_true",
                        help="story_spine.json (hook, through-line, a beat per ~450 chars) must exist and fit the article")
    args = parser.parse_args(argv)
    run_dir = args.run_dir
    article_path, sources_path = run_dir / "article.md", run_dir / "sources.json"
    try:
        article = article_path.read_text(encoding="utf-8")
        raw_sources = json.loads(sources_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read article/sources: {exc}", file=sys.stderr)
        return 2

    problems, ids = check_sources(raw_sources)
    article_problems, anchors = check_article(article, ids)
    problems += article_problems
    spine_path = run_dir / SPINE_FILE
    if spine_path.exists() or args.require_spine:
        try:
            problems += check_spine(json.loads(spine_path.read_text(encoding="utf-8")), article)
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{SPINE_FILE}: {exc}")
    outline_path = run_dir / "deck_outline.json"
    if outline_path.exists():
        try:
            problems += check_outline(json.loads(outline_path.read_text(encoding="utf-8")), anchors, ids)
        except json.JSONDecodeError as exc:
            problems.append(f"deck_outline.json: {exc}")

    for problem in problems:
        print(f"[article] {problem}", file=sys.stderr)
    print(f"article body {body_chars(article)} chars, {len(ids)} sources, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
