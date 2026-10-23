"""``news_script.json``: one HN-story Short, in five beats.

hook（鉤子一句）→ what（發生什麼）→ why（為什麼重要，台灣角度）→
analogy（一句國高中比喻）→ take（晶片貓觀點：原創評論，必須有）

Written by ``/news-short`` (Claude) after reading the original page; checked by
:func:`lint`, then turned into the pipeline's ``script.json`` (one scene per beat)
by :func:`to_script`.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from dataclasses import dataclass, field
from pydantic import BaseModel, ConfigDict, Field

from content_farm.explainer.deck import visible_len
from content_farm.production.news import guard
from content_farm.production.news.claims import Claim
from content_farm.production.news.series import NewsSeries
from content_farm.production.shorts_cut import shorts_title
from content_farm.production.steps import NEWS_ITEM_FILE, NEWS_SCRIPT_FILE
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.types import Orientation, VideoLength

SCRIPT_FILE = NEWS_SCRIPT_FILE
ITEM_FILE = NEWS_ITEM_FILE              # written by `news daily --pick`; marks a news Short run-dir
VOICE_TEXT_FILE = "voice_text.json"     # narration + pronunciation only (voice step input)
GLOSSARY_PATH = Path(__file__).with_name("glossary.yaml")
# Measured 2026-10-16 on the first two HN Shorts with the chipcat Fish Audio voice:
# 238 chars / 37.29 s and 234 chars / 37.02 s (visible_len) → 6.3. Re-measure if the voice changes.
CHARS_PER_SECOND = 6.3
MAX_SECONDS = 55.0                      # 60 s Shorts limit minus the end card
MIN_SECONDS = 25.0
MAX_SECONDS_AFTER_FIX = 56.0            # the claim audit's 「據…報導」 prefixes make sentences longer; 60 s − 2 s end card − margin
AFTER_FIX_STRETCH = 1.3
END_CARD_SECONDS = 2.0
BEAT_ORDER = ("hook", "what", "why", "analogy", "take")
BEAT_LABELS = {"hook": "先講重點", "what": "發生什麼", "why": "台灣為什麼要在意", "analogy": "用比喻講",
               "take": "晶片貓觀點"}
BEAT_CHARS = {"hook": (8, 45), "what": (30, 120), "why": (25, 110), "analogy": (18, 90), "take": (25, 110)}
DEFAULT_POSE = {"hook": "shocked", "what": "point", "why": "think", "analogy": "wave", "take": "smug"}
OPINION_MARKERS = ("我覺得", "我認為", "我們認為", "我的看法", "晶片貓認為", "晶片貓覺得", "我會", "我猜",
                   "我賭", "我比較在意", "值得注意的是", "重點不是", "真正", "我看")
BANNED = {r"狂|絕了|炸裂|太神": "流行語（時間久了尷尬）",
          r"買進|賣出|目標價|飆股|進場|抄底|投資建議": "投資建議（頻道規則：不報明牌）"}
FILLER = "欸"


@dataclass(frozen=True)
class Branding:
    """The channel-specific words of a news Short (chipcat's 快報 is the default; technews overrides)."""

    take_label: str = BEAT_LABELS["take"]
    byline: str = "本片是晶片貓對原文的摘要與評論，不是翻譯；細節與數字以原文為準。"
    series_line: str = "晶片貓 HN 快報：每天 1–2 則國外科技圈熱門話題，每週六整理成長片。"
    tags: tuple[str, ...] = ("Shorts", "晶片貓", "HN快報", "科技新聞")
    beat_labels: dict[str, str] = field(default_factory=dict)    # per-channel names of the beats (ent relabels them)

    def labels(self) -> dict[str, str]:
        return {**BEAT_LABELS, **self.beat_labels, "take": self.take_label}
Pose = Literal["idle", "point", "think", "shocked", "smug", "deadpan", "wave"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceRef(_Frozen):
    url: str
    title: str = Field(min_length=1, max_length=200)
    publisher: str = Field(default="", max_length=60)
    read_at: str = ""                    # ISO-8601; required for article/abstract
    kind: Literal["article", "abstract", "discussion"] = "article"


class Screen(_Frozen):
    headline: str = Field(min_length=1, max_length=16)      # big text on the page
    number: str = Field(default="", max_length=10)         # optional hero number ("70%")
    points: tuple[str, ...] = Field(default=(), max_length=3)


class Beat(_Frozen):
    kind: Literal["hook", "what", "why", "analogy", "take"]
    narration: str = Field(min_length=1)
    screen: Screen
    pose: Pose | None = None
    term: str = ""                                         # analogy: the glossary term explained
    claims: tuple[Claim, ...] = ()                         # ent: one sourced claim per factual sentence (news/claims.py)
    # visual v4: English picture brief for this beat (content only; the channel's style prefix is added). At least 3 of the 5
    # beats of a Short on an AI-illustration channel carry one (news/visuals.py); "" = this beat stays a text card.
    image_prompt: str = Field(default="", max_length=400)


class NewsScript(_Frozen):
    version: Literal[1] = 1
    item_id: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=4, max_length=60)        # " #Shorts" is appended
    summary: str = Field(min_length=10, max_length=120)    # first line of the description
    importance: int = Field(ge=1, le=5)                    # weekly roll-up picks the highest
    sources: tuple[SourceRef, ...] = Field(min_length=1)
    beats: tuple[Beat, ...] = Field(min_length=5, max_length=5)
    tags: tuple[str, ...] = ()
    pronunciation_map: dict[str, str] = {}


def load_script(run_dir: Path) -> NewsScript:
    return NewsScript.model_validate_json((run_dir / SCRIPT_FILE).read_text(encoding="utf-8"))


def load_item(run_dir: Path) -> dict:
    return json.loads((run_dir / ITEM_FILE).read_text(encoding="utf-8"))


def is_news_short(run_dir: Path | None) -> bool:
    return run_dir is not None and (run_dir / ITEM_FILE).is_file()


def load_glossary(path: Path = GLOSSARY_PATH) -> dict[str, dict[str, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    terms = data.get("terms") or {}
    if not isinstance(terms, dict):
        raise ValueError(f"{path}: 'terms' must be a mapping")
    for term, entry in terms.items():
        if not isinstance(entry, dict) or not entry.get("analogy") or not entry.get("definition"):
            raise ValueError(f"{path}: term {term!r} needs analogy and definition")
    return terms


def estimate_seconds(script: NewsScript, cps: float = CHARS_PER_SECOND) -> float:
    return round(sum(visible_len(b.narration) for b in script.beats) / cps, 1)


def _beat_problems(script: NewsScript, glossary: dict[str, dict[str, str]], *, analogy_required: bool = True,
                   after_fix: bool = False) -> list[str]:
    problems = []
    kinds = tuple(b.kind for b in script.beats)
    if kinds != BEAT_ORDER:
        problems.append(f"beats must be {' → '.join(BEAT_ORDER)}, got {' → '.join(kinds)}")
    for beat in script.beats:
        low, high = BEAT_CHARS[beat.kind]
        n = visible_len(beat.narration)
        if not (0 if after_fix else low) <= n <= (round(high * AFTER_FIX_STRETCH) if after_fix else high):
            problems.append(f"{beat.kind}: narration {n} chars, want {low}–{high}")
    by_kind = {b.kind: b for b in script.beats}
    take = by_kind.get("take")
    if take and not any(m in take.narration for m in OPINION_MARKERS):
        problems.append("take: 沒有看得出是觀點的句子（原創評論必須有；例：我覺得／重點不是…而是…）")
    analogy = by_kind.get("analogy")
    if not analogy_required:
        return problems
    if analogy and not analogy.term:
        problems.append("analogy: term is empty (name the glossary term the analogy explains)")
    elif analogy and analogy.term not in glossary:
        problems.append(f"analogy: term {analogy.term!r} not in glossary.yaml — add analogy + definition")
    return problems


def _source_problems(script: NewsScript, item: dict | None) -> list[str]:
    primary = [s for s in script.sources if s.kind in ("article", "abstract")]
    problems = []
    if not primary:
        problems.append("sources: need the original article/abstract (HN/Lobsters threads are leads, not facts)")
    problems += [f"sources: {s.url} has no read_at" for s in primary if not s.read_at]
    if item is not None:
        read = item.get("read") or {}
        if not read.get("ok"):
            problems.append("news_short.json: the original was never read successfully; do not write this one")
        urls = {read.get("url"), read.get("final_url")} - {None, ""}
        if urls and not any(s.url in urls for s in primary):
            problems.append(f"sources: none of the primary sources is the URL that was read ({', '.join(urls)})")
    return problems


def _text_problems(script: NewsScript, cps: float = CHARS_PER_SECOND, *, after_fix: bool = False) -> list[str]:
    text = "".join(b.narration for b in script.beats) + script.title
    problems = [f"{why}: {m.group(0)!r}" for pattern, why in BANNED.items() if (m := re.search(pattern, text))]
    if text.count(FILLER) > 1:
        problems.append(f"語氣詞「{FILLER}」出現 {text.count(FILLER)} 次（最多 1）")
    seconds = estimate_seconds(script, cps)
    if not (0 if after_fix else MIN_SECONDS) <= seconds <= (MAX_SECONDS_AFTER_FIX if after_fix else MAX_SECONDS):
        problems.append(f"narration ≈ {seconds}s at {cps} chars/s; want {MIN_SECONDS:.0f}–{MAX_SECONDS:.0f}s")
    return problems


def _screen_text(script: NewsScript) -> str:
    return " ".join([script.title, script.summary, *(b.narration for b in script.beats),
                     *(f"{b.screen.headline} {b.screen.number} {' '.join(b.screen.points)}" for b in script.beats)])


def _guard_problems(script: NewsScript, series: NewsSeries) -> list[str]:
    """Ent guardrails that deleting a sentence cannot fix: a forbidden topic, a source off the whitelist."""
    problems = []
    if series.topic_guard and (why := guard.blocked_reason(_screen_text(script))):
        problems.append(f"禁碰題材（{why}）：這類題目不做，整支重選題")
    problems += [f"sources: {s.url} 不在來源白名單（只能用白名單媒體）" for s in script.sources
                 if series.feeds and series.outlet(s.url) is None]
    return problems


def lint(script: NewsScript, item: dict | None = None,
         glossary: dict[str, dict[str, str]] | None = None, cps: float = CHARS_PER_SECOND,
         series: NewsSeries | None = None, after_fix: bool = False) -> list[str]:
    """Every rule the Short must pass before voice; empty list = OK. ``cps``: the channel voice's measured speed.
    ``series``: the channel's news block (ent guardrails, no analogy beat). ``after_fix``: the claim audit
    deleted unsourced sentences / added 「據…報導」, so the script may be shorter or a little longer than the usual ranges."""
    glossary = load_glossary() if glossary is None else glossary
    required = series.analogy_required if series else True
    return (_beat_problems(script, glossary, analogy_required=required, after_fix=after_fix)
            + _source_problems(script, item) + _text_problems(script, cps, after_fix=after_fix)
            + (_guard_problems(script, series) if series else []))


def _source_line(source: SourceRef) -> str:
    who = f"{source.publisher}｜" if source.publisher else ""
    if source.kind == "discussion":
        return f"{who}{source.title}（討論串，只當線索）{source.url}"
    when = f"（讀取 {source.read_at[:16].replace('T', ' ')}）" if source.read_at else ""
    return f"{who}{source.title} {source.url}{when}"


def description(script: NewsScript, branding: Branding = Branding()) -> str:
    return "\n".join([
        script.summary,
        "",
        branding.byline,
        branding.series_line,
        "",
        "#Shorts",
    ])


def pronunciation(script: NewsScript, glossary: dict[str, dict[str, str]]) -> dict[str, str]:
    text = "".join(b.narration for b in script.beats)
    found = {term: entry["say"] for term, entry in glossary.items() if entry.get("say") and term in text
             and entry["say"] != term}
    return {**found, **script.pronunciation_map}


def voice_text(script: Script) -> str:
    """Everything the TTS hears — the voice step's only input."""
    return json.dumps({"narration": [s.narration for s in script.scenes],
                       "pronunciation_map": script.pronunciation_map}, ensure_ascii=False, indent=2) + "\n"


def keep_measured(script: Script, previous: Script | None) -> Script:
    """Carry the voice step's measured scene durations over when the words are unchanged."""
    if previous is None or voice_text(previous) != voice_text(script):
        return script
    scenes = tuple(new.model_copy(update={"duration_seconds": old.duration_seconds})
                   for new, old in zip(script.scenes, previous.scenes))
    return script.model_copy(update={"scenes": scenes,
                                     "total_duration_seconds": previous.total_duration_seconds})


def to_script(script: NewsScript, glossary: dict[str, dict[str, str]] | None = None,
              branding: Branding = Branding(), cps: float = CHARS_PER_SECOND) -> Script:
    glossary = load_glossary() if glossary is None else glossary
    labels = branding.labels()
    scenes = tuple(
        Scene(scene_number=i, title=labels[b.kind], narration=b.narration,
              visual_hint=VisualHint(description=b.screen.headline, style="news_page"),
              duration_seconds=round(visible_len(b.narration) / cps, 2))
        for i, b in enumerate(script.beats, start=1))
    # Deterministic id/time: re-running prepare on the same news_script.json must not
    # change script.json, or the voice step (paid) would re-run.
    digest = uuid.uuid5(uuid.NAMESPACE_URL, script.model_dump_json())
    stamps = sorted(s.read_at for s in script.sources if s.read_at)
    return Script(
        artifact_id=digest,
        created_at=datetime.fromisoformat(stamps[-1]) if stamps else datetime(2026, 1, 1, tzinfo=timezone.utc),
        video_title=shorts_title(script.title), description=description(script, branding), scenes=scenes,
        target_length=VideoLength.SHORT, orientation=Orientation.PORTRAIT,
        total_duration_seconds=round(sum(s.duration_seconds for s in scenes) + END_CARD_SECONDS, 2),
        tags=tuple(dict.fromkeys((*branding.tags, *script.tags))),
        sources=tuple(_source_line(s) for s in script.sources),
        pronunciation_map=pronunciation(script, glossary),
    )
