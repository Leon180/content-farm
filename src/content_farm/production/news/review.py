"""The day's candidate list: ``candidates.json`` (machine) + ``candidates.html`` (Leon's phone)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from content_farm.production.news.models import Ranked
from content_farm.production.news.series import NewsSeries

TEMPLATES = Path(__file__).parent / "templates"
CANDIDATES_JSON = "candidates.json"
CANDIDATES_HTML = "candidates.html"


def render_page(day: str, series: NewsSeries, ranked: Sequence[Ranked], *, fetched_at: datetime,
                counts: dict[str, int], errors: Sequence[str]) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    count_text = "、".join(f"{ {'hn': 'HN', 'lobsters': 'Lobsters', 'arxiv': 'arXiv'}.get(k, k)} {v}"
                          for k, v in counts.items())
    return env.get_template("candidates.html.j2").render(
        day=day, series_name=series.name, ranked=ranked, fetched_at=fetched_at.strftime("%m-%d %H:%M"),
        counts=count_text, errors=errors, max_age=series.max_age_hours,
        pick_min=series.daily_shorts[0], pick_max=series.daily_shorts[1])


def write_candidates(day_dir: Path, day: str, series: NewsSeries, ranked: Sequence[Ranked], *,
                     fetched_at: datetime, counts: dict[str, int], errors: Sequence[str]) -> Path:
    day_dir.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "day": day, "fetched_at": fetched_at.isoformat(timespec="seconds"),
               "counts": counts, "errors": list(errors),
               "ranked": [r.model_dump() for r in ranked]}
    (day_dir / CANDIDATES_JSON).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    page = day_dir / CANDIDATES_HTML
    page.write_text(render_page(day, series, ranked, fetched_at=fetched_at, counts=counts, errors=errors),
                    encoding="utf-8")
    return page


def load_candidates(day_dir: Path) -> list[Ranked]:
    path = day_dir / CANDIDATES_JSON
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing; run `produce.py news daily --date …` without --pick first")
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Ranked.model_validate(item) for item in data["ranked"]]
