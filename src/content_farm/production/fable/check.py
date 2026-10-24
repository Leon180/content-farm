"""Program checks on ``fable.json`` (the script step's ``verify``): structure, the reveal rule, the thread ledger.

The reveal rule is the channel's promise: the concept's name and every synonym stay out of the title, the
hook, the story's narration, its picture prompts and its cards until the reveal beat. Everything is a
pure function of the file, so a producer agent can run it as often as it likes.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable

from content_farm.explainer.deck import estimate_seconds
from content_farm.explainer.illustrate import forbidden_prompt_terms
from content_farm.production.fable.model import Beat, Fable

TRENDY_WORDS = ("狂", "絕了")
FILLER_LIMIT = 1                     # 「欸」 at most once per video (Leon's script-tone preference)
HUMAN_WORDS = re.compile(r"\b(man|men|woman|women|boy|girl|child|children|kid|people|person|human|king|queen|"
                         r"farmer|merchant|villager|villagers|soldier|face|portrait|selfie|crowd|customers?|shoppers?|"
                         r"passers-?by|pedestrians?|vendors?|townsfolk|market street|busy street|lanternmaker)\b", re.IGNORECASE)
# Prompts that make an animal use human hands (the owl grew hands in 3 of 9 pictures, 2026-10-24)
HANDS_WORDS = re.compile(r"\b(hands?|arms?|fingers?|holding|holds?|held|gripping|grasping|clutching|"
                         r"writing (?:with|in|on|at|quickly)|writes|carrying|reading)\b", re.IGNORECASE)
# The picture model turns a "round grey forest creature" into an existing film character (seen on the first test pictures)
LOOKALIKE_WORDS = re.compile(r"\b(tanuki|raccoon[- ]dog|big round|fat round|round grey|round gray|chubby)\b", re.IGNORECASE)
# seconds the narration should fill (estimated at deck.CHARS_PER_SECOND); the measured total is checked by QC
LIMITS = {"short": {"total": (55.0, 88.0), "before": (36.0, 62.0), "after": (16.0, 38.0), "beat": 15.0,
                    "story": (3, 6), "explain": (2, 4), "beats": 12},
          "mid": {"total": (230.0, 370.0), "before": (130.0, 270.0), "after": (70.0, 140.0), "beat": 26.0,
                  "story": (8, 18), "explain": (4, 8), "beats": 34}}
SECONDS_PER_PICTURE = 8.0


def seconds(beat: Beat) -> float:
    return estimate_seconds(beat.narration)


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def concept_terms(fable: Fable) -> tuple[str, ...]:
    """The name, its synonyms and English names, squashed and lower-cased (what must not leak)."""
    c = fable.concept
    return tuple(t for t in (_squash(x) for x in (c.name, *c.aliases, *c.english)) if len(t) >= 2)


def _beat_text(beat: Beat) -> str:
    rows = [f"{r.story} {r.concept}" for r in beat.card.rows] if beat.card else []
    title = beat.card.title if beat.card else ""
    return _squash(" ".join([beat.narration, title, *rows, *(s.image_prompt for s in beat.shots)]))


def leak_problems(fable: Fable) -> list[str]:
    """Concept terms that appear before the reveal beat (title, hook, story)."""
    terms = concept_terms(fable)
    reveal = fable.reveal_index()
    if reveal is None:
        return []
    problems = [f"標題含概念名「{t}」" for t in terms if t in _squash(fable.title)]
    for beat in fable.beats[:reveal]:
        text = _beat_text(beat)
        problems += [f"{beat.id}（揭曉前）出現概念名或同義詞「{t}」" for t in terms if t in text]
    return problems


def order_problems(fable: Fable) -> list[str]:
    acts = [b.act for b in fable.beats]
    problems = [f"beat id 要依序 b1…b{len(acts)}"] if [b.id for b in fable.beats] != [f"b{i}" for i in range(1, len(acts) + 1)] else []
    if acts[0] != "hook":
        problems.append("第一個 beat 必須是 hook（一句好奇鉤子）")
    if acts[-1] != "apply" or acts.count("apply") != 1:
        problems.append("最後一個（且只有一個）beat 必須是 apply（現實應用）")
    if acts.count("hook") != 1 or acts.count("reveal") != 1:
        problems.append("hook 與 reveal 各只能有一個")
        return problems
    rank = {"hook": 0, "story": 1, "reveal": 2, "explain": 3, "apply": 4}
    if [rank[a] for a in acts] != sorted(rank[a] for a in acts):
        problems.append("beat 順序必須是 hook → story → reveal → explain → apply")
    return problems


def count_problems(fable: Fable) -> list[str]:
    lim = LIMITS[fable.format]
    acts = [b.act for b in fable.beats]
    problems = []
    for act in ("story", "explain"):
        low, high = lim[act]
        if not low <= acts.count(act) <= high:
            problems.append(f"{act} beat 要 {low}–{high} 個，現在 {acts.count(act)}")
    if len(acts) > lim["beats"]:
        problems.append(f"beat 太多（{len(acts)} > {lim['beats']}）")
    return problems


def length_problems(fable: Fable) -> list[str]:
    lim, reveal = LIMITS[fable.format], fable.reveal_index()
    if reveal is None:
        return []
    before = sum(seconds(b) for b in fable.beats[:reveal])
    after = sum(seconds(b) for b in fable.beats[reveal:])
    problems = []
    for label, value, (low, high) in (("全片", before + after, lim["total"]), ("揭曉前（寓言）", before, lim["before"]),
                                      ("揭曉後（解釋）", after, lim["after"])):
        if not low <= value <= high:
            problems.append(f"{label}估計 {value:.0f} 秒，要 {low:.0f}–{high:.0f} 秒")
    for beat in fable.beats:
        if seconds(beat) > lim["beat"]:
            problems.append(f"{beat.id} 旁白估計 {seconds(beat):.0f} 秒，超過單一 beat 上限 {lim['beat']:.0f} 秒，拆成兩個 beat")
    return problems


def reveal_problems(fable: Fable) -> list[str]:
    reveal = fable.reveal_index()
    if reveal is None:
        return ["缺 reveal beat"]
    beat = fable.beats[reveal]
    problems = []
    if _squash(fable.concept.name) not in _squash(beat.narration):
        problems.append(f"{beat.id}（reveal）旁白要說出概念名「{fable.concept.name}」")
    if beat.card is None or not beat.card.title:
        problems.append(f"{beat.id}（reveal）要有 card.title（概念圖解的標題＝概念名）")
    hook = fable.beats[0]
    if "？" not in hook.narration and "猜" not in hook.narration:
        problems.append("hook 要是一句問句或邀請猜（含「？」或「猜」）")
    if len(hook.narration) > 60:
        problems.append("hook 要一句話（≤ 60 字）")
    return problems


def mapping_problems(fable: Fable) -> list[str]:
    ids = {e.id for e in fable.elements}
    explain = [b for b in fable.beats if b.act == "explain"]
    shown = {m for b in explain for m in b.maps}
    problems = [f"元素 {i} 沒有被任何 explain beat 對應（maps）" for i in sorted(ids - shown)]
    problems += [f"{b.id} maps 了不存在的元素 {m}" for b in explain for m in b.maps if m not in ids]
    problems += [f"{b.id}（explain）要有 card.rows（故事情節 → 概念要素）" for b in explain if not (b.card and b.card.rows)]
    return problems


def ledger_problems(fable: Fable) -> list[str]:
    """Every thread laid down before the reveal is paid off at or after it (InkOS-style hook ledger)."""
    reveal = fable.reveal_index()
    ids = {h.id for h in fable.hooks}
    problems = []
    for beat in fable.beats:
        problems += [f"{beat.id} 引用了不存在的伏筆 {i}" for i in (*beat.plants, *beat.resolves) if i not in ids]
    if reveal is None:
        return problems
    for hook in fable.hooks:
        planted = [i for i, b in enumerate(fable.beats) if hook.id in b.plants]
        paid = [i for i, b in enumerate(fable.beats) if hook.id in b.resolves]
        if not planted or planted[0] >= reveal:
            problems.append(f"伏筆 {hook.id} 沒有在揭曉前埋下（plants）")
        if not paid or paid[-1] < reveal:
            problems.append(f"伏筆 {hook.id} 沒有在揭曉（含）之後收掉（resolves）")
    return problems


def _shot_ids(fable: Fable) -> dict[str, str]:
    return {f"{b.id}.{n}": s.image_prompt for b in fable.beats for n, s in enumerate(b.shots, 1) if s.image_prompt.strip()}


def picture_problems(fable: Fable) -> list[str]:
    drawn, problems = _shot_ids(fable), []
    for beat in fable.beats:
        need = math.ceil(seconds(beat) / SECONDS_PER_PICTURE) if beat.act in ("hook", "story") else 1
        if len(beat.shots) < min(need, 3):
            problems.append(f"{beat.id} 約 {seconds(beat):.0f} 秒，至少要 {min(need, 3)} 張圖（畫面每 {SECONDS_PER_PICTURE:.0f} 秒內要換）")
        for n, shot in enumerate(beat.shots, 1):
            where = f"{beat.id}.{n}"
            problems += _shot_problems(shot.image_prompt, shot.reuse, where, drawn)
    return problems


def _position(shot_id: str) -> tuple[int, int]:
    """``b3.2`` → (3, 2); unparsable ids sort last."""
    match = re.fullmatch(r"b(\d+)\.(\d+)", shot_id)
    return (int(match.group(1)), int(match.group(2))) if match else (10**6, 0)


def _shot_problems(prompt: str, reuse: str, where: str, drawn: dict[str, str]) -> list[str]:
    if reuse:
        ok = reuse in drawn and _position(reuse) < _position(where) and not prompt.strip()
        return [] if ok else [f"{where} reuse「{reuse}」要指到更早、有圖的 shot，且不要同時寫 image_prompt"]
    if not prompt.strip():
        return [f"{where} 缺 image_prompt（或用 reuse）"]
    problems = [f"{where} 圖片提示詞出現人物或人臉字眼「{m.group(0)}」（原創動物／器物／村落角色，不用真人）"
                for m in [HUMAN_WORDS.search(prompt)] if m]
    problems += [f"{where} 提示詞「{m.group(0)}」會被畫成既有電影角色（圓胖灰色森林生物）；改寫具體外形，例如 slim red-brown fox-like animal with a ringed tail"
                 for m in [LOOKALIKE_WORDS.search(prompt)] if m]
    problems += [f"{where} 提示詞「{m.group(0)}」會讓動物長出人手；改成「道具放在旁邊的樹枝／地上／桌上」，動物翅膀收起"
                 for m in [HANDS_WORDS.search(prompt)] if m]
    bad = forbidden_prompt_terms(prompt)
    return problems +([f"{where} 提示詞要求 {bad}（非擬真、不模仿畫家）"] if bad else [])


def keep_avoid_problems(fable: Fable) -> list[str]:
    return [f"{b.id} 缺 must_keep／must_avoid（每段先寫必留與禁寫）" for b in fable.beats if not (b.must_keep and b.must_avoid)]


def tone_problems(fable: Fable) -> list[str]:
    text = "".join(b.narration for b in fable.beats)
    problems = [f"旁白用了過時流行語「{w}」" for w in TRENDY_WORDS if w in text]
    if text.count("欸") > FILLER_LIMIT:
        problems.append(f"「欸」最多 {FILLER_LIMIT} 次")
    return problems


CHECKS: tuple[Callable[[Fable], list[str]], ...] = (
    order_problems, count_problems, reveal_problems, leak_problems, mapping_problems, ledger_problems,
    keep_avoid_problems, picture_problems, length_problems, tone_problems)


def fable_problems(fable: Fable) -> list[str]:
    """Every problem with the file (empty = ready for the script panel). Ordering errors stop the rest."""
    first = order_problems(fable)
    if first:
        return first
    return [p for check in CHECKS[1:] for p in check(fable)]


def estimated_seconds(fable: Fable) -> float:
    return round(sum(seconds(b) for b in fable.beats), 1)
