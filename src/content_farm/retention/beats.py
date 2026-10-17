"""Narration beat lint: something that makes a viewer keep watching at least every 10 seconds.

A *hook* sentence is one of (Leon 2026-10-17):
question（問題）, tease（預告）, reversal（數字反轉／「不是…而是」）, joke（冷笑話）,
gossip（八卦，須有來源）, analogy（比喻揭曉）, quote（人物原話）.

Rules (🟡 creator rules of thumb, research §5.1):
- adjacent hooks ≤ ``MAX_GAP`` seconds apart (also from 0 s to the first hook);
- a re-hook (question or tease) at least every ``REHOOK_MAX`` seconds;
- every chapter except the last ends with a tease of the next one (or the next chapter opens
  with a question);
- the first hook lands by ``FIRST_HOOK_MAX`` seconds.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from content_farm.retention.timing import Scene, Sentence, load_scenes, sentence_timeline

MAX_GAP = 10.0
REHOOK_MAX = 90.0
FIRST_HOOK_MAX = 15.0

_QUESTION = re.compile(r"[？?]|為什麼|怎麼|多少|哪[裡一些個家]|會不會|是不是|到底|嗎[。，]?$")
_TEASE = re.compile(r"接下來|等一下|待會|後面會|先記住|下一章|下一段|下一個|馬上|最後|答案|你會看到|你會聽到|"
                    r"先賣個關子|留到|伏筆|回到開頭")
_CONTRAST = re.compile(r"但|卻|反而|不一定|結果|其實|沒想到|竟然|偏偏|不是.{0,24}而是|不是.{0,12}，是|，不是|還是不夠")
_SURPRISE = re.compile(r"竟然|沒想到|反而|偏偏|其實")       # a reveal on its own, number or not
_REPORTED = re.compile(r"據.{0,8}報|報導|挖到|爆料|傳出")   # in a gossip slide: the sourced gossip itself
_NUMBER = re.compile(r"\d|[一二三四五六七八九十百千萬兩半]+[倍成%％年片週]|翻倍|減半")
_ANALOGY = re.compile(r"就像|好比|像是|等於|想像|用.{1,8}來想|比喻|差不多是")
_QUOTE = re.compile(r"說[：:]|自己說|親口|原話|承認|「[^」]{2,}」")  # a person's own words, not 「報導說」
_JOKE = re.compile(r"罐罐|貓砂|紙箱|我們貓|我的體重|晶片貓.{0,6}(也|都)")

HOOK_KINDS = ("question", "tease", "reversal", "joke", "gossip", "analogy", "quote")


@dataclass(frozen=True)
class Hook:
    t: float
    kind: str
    slide_id: str
    text: str
    end: float = 0.0      # when the sentence finishes (a punchline lands at the end)


@dataclass(frozen=True)
class BeatReport:
    hooks: list[Hook]
    gaps: list[dict]                 # gaps > MAX_GAP: {start, end, seconds, slide_id}
    max_gap: float
    first_hook: float | None
    rehook_gaps: list[dict]          # stretches with no question/tease > REHOOK_MAX
    chapter_teases: list[dict]       # chapter boundaries without a tease
    duration: float
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["hook_count"] = len(self.hooks)
        data["by_kind"] = {k: sum(h.kind == k for h in self.hooks) for k in HOOK_KINDS}
        return data


def classify(sentence: str, slide_beat: str | None = None) -> str | None:
    """The strongest hook kind of one sentence, or None."""
    if _TEASE.search(sentence):
        return "tease"
    if _QUESTION.search(sentence):
        return "question"
    if _SURPRISE.search(sentence) or (_CONTRAST.search(sentence) and (_NUMBER.search(sentence) or "不是" in sentence
                                                                      or "不夠" in sentence)):
        return "reversal"
    if slide_beat == "joke" and _JOKE.search(sentence):
        return "joke"
    if _JOKE.search(sentence):
        return "joke"
    if slide_beat == "gossip" and (_QUOTE.search(sentence) or _REPORTED.search(sentence)):
        return "gossip"
    if _QUOTE.search(sentence):
        return "quote"
    if _ANALOGY.search(sentence):
        return "analogy"
    return None


def find_hooks(sentences: list[Sentence], slide_beats: dict[str, str | None]) -> list[Hook]:
    hooks = []
    for sentence in sentences:
        kind = classify(sentence.text, slide_beats.get(sentence.slide_id))
        if kind:
            hooks.append(Hook(sentence.start, kind, sentence.slide_id, sentence.text, sentence.end))
    return hooks


def _gaps(times: list[float], duration: float, limit: float, scenes: list[Scene]) -> list[dict]:
    points = [0.0, *times, duration]
    out = []
    for a, b in zip(points, points[1:]):
        if b - a > limit:
            slide = next((s.slide_id for s in scenes if s.start <= a < s.end), scenes[-1].slide_id)
            out.append({"start": round(a, 1), "end": round(b, 1), "seconds": round(b - a, 1), "slide_id": slide})
    return out


def _chapter_teases(scenes: list[Scene], hooks: list[Hook]) -> list[dict]:
    missing = []
    chapters = sorted({s.chapter for s in scenes})
    for chapter in chapters[:-1]:
        last = [s for s in scenes if s.chapter == chapter][-1]
        nxt = next(s for s in scenes if s.chapter == chapter + 1)
        teased = any(h.kind == "tease" and last.start <= h.t <= last.end for h in hooks)
        opens = any(h.kind in ("question", "tease") and nxt.start <= h.t <= nxt.start + 8 for h in hooks)
        if not (teased or opens):
            missing.append({"chapter": chapter, "at": round(last.end, 1), "slide_id": last.slide_id})
    return missing


def lint(scenes: list[Scene], sentences: list[Sentence], slide_beats: dict[str, str | None]) -> BeatReport:
    duration = scenes[-1].end if scenes else 0.0
    hooks = find_hooks(sentences, slide_beats)
    times = [h.t for h in hooks]
    gaps = _gaps(times, duration, MAX_GAP, scenes)
    points = [0.0, *times, duration]
    max_gap = round(max((b - a for a, b in zip(points, points[1:])), default=duration), 1)
    rehooks = [h.t for h in hooks if h.kind in ("question", "tease")]
    rehook_gaps = _gaps(rehooks, duration, REHOOK_MAX, scenes)
    teases = _chapter_teases(scenes, hooks)
    first = hooks[0].t if hooks else None
    problems = [f"{g['start']:.0f}–{g['end']:.0f}s（{g['slide_id']}）{g['seconds']:.0f} 秒沒有鉤子" for g in gaps]
    problems += [f"{g['start']:.0f}–{g['end']:.0f}s 超過 {REHOOK_MAX:.0f} 秒沒有問題或預告" for g in rehook_gaps]
    problems += [f"第 {c['chapter']} 章結尾（{c['slide_id']}）沒有預告下一章" for c in teases]
    if first is None or first > FIRST_HOOK_MAX:
        problems.append(f"第一個鉤子在 {first if first is not None else '—'} 秒（上限 {FIRST_HOOK_MAX:.0f}）")
    return BeatReport(hooks, gaps, max_gap, first, rehook_gaps, teases, round(duration, 1), problems)


def slide_beats(run_dir: Path) -> dict[str, str | None]:
    import json

    deck_path = run_dir / "deck.json"
    if not deck_path.is_file():
        return {}
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    return {s["id"]: s.get("beat") for sec in deck.get("sections", []) for s in sec["slides"]}


def lint_run(run_dir: Path) -> BeatReport:
    scenes = load_scenes(run_dir)
    return lint(scenes, sentence_timeline(run_dir, scenes), slide_beats(run_dir))
