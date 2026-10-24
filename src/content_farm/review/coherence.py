"""Continuity check for a script (quality v5 item 7): catch the same quantity told two different ways.

"全長約 8 公尺" in one slide and "十三公尺" a few minutes later; "三種方法" followed by a list of four; "第一次" claimed
twice. The detector is deliberately cheap and conservative: it pulls (context, number, unit) triples out of the narration,
and only when two sentences share a context phrase and a unit but give different values does it raise a suspicion.
It never edits anything; suspicions go to the reviewer (``coherence.txt``) and the QC report as warnings. (The
"consistency audit" idea is InkOS's; the rules are ours.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
UNITS = "公尺|公里|公分|公斤|噸|億|萬|千|倍|%|％|年|個月|週|天|小時|分鐘|秒|隻|條|種|個|次|名|家|顆|層|度|奈米|nm|GB|TB|W|元|美元"
_NUM = r"\d[\d,]*(?:\.\d+)?|[零〇一二兩三四五六七八九十百]{1,4}"
QUANTITY = re.compile(rf"(?P<ctx>[^\s，。、；：「」（）()！？\d]{{0,6}}?)(?P<approx>約|大約|近|超過|將近)?\s*(?P<num>{_NUM})\s*(?P<unit>{UNITS})")
STOP_CONTEXT = {"有", "是", "了", "的", "在", "和", "與", "及", "到", "共", "約", "就", "也", "都", "還", "再", "又"}


def to_number(text: str) -> float | None:
    """'1,200' -> 1200.0, '十三' -> 13.0, '二十' -> 20.0; None when it is not a plain number."""
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        pass
    total, current = 0, 0
    for ch in text:
        if ch in CN_DIGITS:
            current = CN_DIGITS[ch]
        elif ch == "十":
            total += (current or 1) * 10
            current = 0
        elif ch == "百":
            total += (current or 1) * 100
            current = 0
        else:
            return None
    return float(total + current)


@dataclass(frozen=True)
class Quantity:
    sentence_id: str
    context: str
    value: float
    unit: str
    approx: bool
    quote: str


@dataclass(frozen=True)
class Suspicion:
    kind: str                       # quantity | count
    first: Quantity
    second: Quantity

    def message(self) -> str:
        a, b = self.first, self.second
        return (f"[{a.sentence_id}]「{a.quote}」與 [{b.sentence_id}]「{b.quote}」："
                f"同樣的「{a.context or a.unit}」數字不同（{a.value:g} vs {b.value:g} {a.unit}）")


def extract(sentence_id: str, text: str) -> list[Quantity]:
    found = []
    for match in QUANTITY.finditer(text):
        value = to_number(match.group("num"))
        if value is None:
            continue
        context = "".join(ch for ch in match.group("ctx") if ch not in STOP_CONTEXT)[-3:]
        found.append(Quantity(sentence_id, context, value, match.group("unit").replace("％", "%"),
                              bool(match.group("approx")), match.group(0).strip()))
    return found


def _tolerates(a: Quantity, b: Quantity) -> bool:
    """Same number, or an approximation that is within 15 % of the other value (約 8 vs 8.2)."""
    if a.value == b.value:
        return True
    if a.approx or b.approx:
        return abs(a.value - b.value) <= 0.15 * max(abs(a.value), abs(b.value))
    return False


def suspicions(sentences: list[tuple[str, str]]) -> list[Suspicion]:
    """``sentences``: (id, text) in script order. Two quantities clash when the unit and a context phrase of at least two
    characters agree (a bare unit with no context never clashes: "三年" and "十年" are different things) and the values differ."""
    quantities = [q for sid, text in sentences for q in extract(sid, text)]
    out: list[Suspicion] = []
    for i, a in enumerate(quantities):
        for b in quantities[i + 1:]:
            if a.sentence_id == b.sentence_id or a.unit != b.unit or len(a.context) < 2 or a.context != b.context:
                continue
            if not _tolerates(a, b):
                out.append(Suspicion("quantity", a, b))
    return out


_ENUM_PROMISE = re.compile(r"(?P<n>[二兩三四五六七八九十])(?:個|種|大|項|步|招|點)")
_ENUM_ITEM = re.compile(r"第([一二三四五六七八九十])|(?:^|[，。；\s])([一二三四五六七八九十])[、．.]")


def enumeration_suspicions(sentences: list[tuple[str, str]]) -> list[str]:
    """A promised count ("三個方法") against the highest ordinal used afterwards ("第四…") within the next 12 sentences."""
    notes = []
    for index, (sid, text) in enumerate(sentences):
        promise = _ENUM_PROMISE.search(text)
        if not promise:
            continue
        said = to_number(promise.group("n"))
        window = sentences[index + 1:index + 13]
        ordinals = [to_number(m.group(1) or m.group(2)) for _, t in window for m in _ENUM_ITEM.finditer(t)]
        highest = max((o for o in ordinals if o is not None), default=None)
        if said is not None and highest is not None and highest > said:
            notes.append(f"[{sid}]「{promise.group(0)}」之後出現第 {highest:g} 項，數量對不上")
    return notes


def render(sentences: list[tuple[str, str]]) -> str:
    """The text the reviewers read (empty string when nothing looks wrong)."""
    items = [s.message() for s in suspicions(sentences)] + enumeration_suspicions(sentences)
    if not items:
        return ""
    return "連貫性檢查（程式找到的疑似前後矛盾，請逐條確認是否屬實；不是結論）\n" + "\n".join(f"- {i}" for i in items) + "\n"
