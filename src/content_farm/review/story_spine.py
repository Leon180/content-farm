"""Narrative spine of an explainer article (Leon 2026-10-23): decided while the article is written, not after the
deck has been rejected by script_structure (three runs in a row ended there: chipcat run1 / run2 and cel run1 — articles
that were stacks of glossaries, timelines and number tables, with no person or tension to follow).

The article producer writes ``story_spine.json`` next to ``article.md``; ``scripts/check_article.py --require-spine``
checks its shape against the article. Also here: the quantity-word rule (a sentence that says "七類" and lists the
items must list that many — cel run1 was stopped by it).
"""

from __future__ import annotations

import re
from typing import Any

SPINE_FILE = "story_spine.json"
CHARS_PER_BEAT = 450          # ≈ 80 s of narration at 5.5 chars/s: one turn or cliffhanger at least this often
MIN_BEATS = 3
MIN_TEXT = 6                  # chars: "有趣" is not a hook
BIG_SECTION_CHARS = 700       # a section this long needs a beat of its own

_ANCHOR = re.compile(r"\{#(a-[\w-]+)\}")
_CITE = re.compile(r"\[src:[\w.-]+\]")
APPENDIX_MARKER = "{#a-gossip}"

SPINE_BRIEF = f"""敘事骨架（寫文章之前先想好，並寫 {SPINE_FILE}；腳本評審的觀眾會在名詞表、時間軸、數字表堆疊的地方離開）：
1. 開場鉤子：第一段的前兩三句就拋出一個懸念、反常的事實或一個問題，之後要回答它。
2. 一條貫穿的人物或衝突：一個具名的人／公司／事件（有立場、有賭注、有對手或阻礙），或一組對立（承諾 vs. 實際、官方說法 vs. 數字）。
   每個段落都要回扣它；名詞、數字、時間點是它的證據，不是獨立的清單。選題裡找不到人物或事件主線，就用「這個數字／說法到底誰說了算」當衝突。
3. 每 60–90 秒的旁白（約 {CHARS_PER_BEAT} 字文章）至少一個轉折或懸念：反轉、揭曉、新的反問、八卦、意外的比較。連續超過兩段都在列名詞、日期或數字，就是缺留人點。
4. 收尾回扣開場的鉤子。
5. 不改事實規則：人物、情節、引述、數字都要有來源；沒有來源的轉折寫成頻道自己的判斷，不編造情節。章節錨點（{{#a-…}}）照舊保留。
{SPINE_FILE} 格式：{{"hook":"開場鉤子一句","through_line":"貫穿的人物或衝突一句","beats":[{{"section":"a-timeline","turn":"這裡的轉折／懸念"}}],"payoff":"收尾怎麼回扣"}}；
beats 至少「文章字數 ÷ {CHARS_PER_BEAT}」個（最少 {MIN_BEATS}），section 必須是文章裡存在的錨點，每個超過 {BIG_SECTION_CHARS} 字的章節至少一個。"""

QUANTITY_BRIEF = ("數量詞前後一致：句子或標題說「N 類／N 種／N 項／N 點」，下面列出的條目數就必須剛好是 N；改寫、增刪條目後，"
                  "回頭把前面的數量詞一起改。交出前逐一核對。")

_DIGITS = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
           "十一": 11, "十二": 12}
_QUANTITY = re.compile(
    r"(?P<n>十[一二]?|[一二兩三四五六七八九]|\d{1,2})\s*(?:大)?(?P<unit>類|種|項|點|個原因|個步驟|個階段)\s*[，,]?\s*"
    r"(?:分別是|分別為|包括|包含|如下|有)?\s*[：:]\s*(?P<items>[^。！？\n]+)")
_ITEM_SPLIT = re.compile(r"[、]")
_LAST_JOIN = re.compile(r"(?:和|與|及|跟)")


def _declared(n: str) -> int:
    return int(n) if n.isdigit() else _DIGITS.get(n, 0)


def _items(text: str) -> list[str]:
    parts = [p.strip() for p in _ITEM_SPLIT.split(_CITE.sub("", text)) if p.strip()]
    if parts:
        tail = _LAST_JOIN.split(parts[-1], maxsplit=1)
        parts = parts[:-1] + [t.strip() for t in tail if t.strip()]
    return parts


def check_quantifiers(article: str) -> list[str]:
    """A "N 類：a、b、c" sentence that lists a different number of items than it declares. Conservative: only the
    "<number><unit>：item、item" shape, with at least two listed items."""
    problems = []
    for number, line in enumerate(article.splitlines(), start=1):
        for match in _QUANTITY.finditer(line):
            declared, listed = _declared(match["n"]), len(_items(match["items"]))
            if declared and listed >= 2 and listed != declared:
                problems.append(f"article line {number}: says {match['n']}{match['unit']} but lists {listed} items")
    return problems


def _sections(article: str) -> dict[str, int]:
    """Anchor → characters of its section (heading line to the next anchored heading), body part only."""
    body = article.split(APPENDIX_MARKER)[0]
    sizes: dict[str, int] = {}
    current = None
    for line in body.splitlines():
        found = _ANCHOR.search(line)
        if found:
            current = found.group(1)
            sizes.setdefault(current, 0)
            continue
        if current is not None:
            sizes[current] += len(re.sub(r"[\s#>|*`\-]", "", _CITE.sub("", line)))
    return sizes


def _text(value: Any) -> bool:
    return isinstance(value, str) and len(value.strip()) >= MIN_TEXT


def check_spine(spine: Any, article: str) -> list[str]:
    """Problems with ``story_spine.json`` measured against ``article.md`` (empty = fine)."""
    if not isinstance(spine, dict):
        return [f"{SPINE_FILE} must be a JSON object"]
    problems = [f"{SPINE_FILE}: {key} is missing or shorter than {MIN_TEXT} chars"
                for key in ("hook", "through_line", "payoff") if not _text(spine.get(key))]
    beats = spine.get("beats")
    if not isinstance(beats, list):
        return problems + [f"{SPINE_FILE}: beats must be a list"]
    sections = _sections(article)
    covered = {b.get("section") for b in beats if isinstance(b, dict) and _text(b.get("turn"))}
    for index, beat in enumerate(beats):
        if not isinstance(beat, dict) or not _text(beat.get("turn")):
            problems.append(f"{SPINE_FILE}: beat #{index} needs a turn of >= {MIN_TEXT} chars")
        elif beat.get("section") not in sections:
            problems.append(f"{SPINE_FILE}: beat #{index} points at unknown section {beat.get('section')!r}")
    wanted = max(MIN_BEATS, sum(sections.values()) // CHARS_PER_BEAT)
    if len(beats) < wanted:
        problems.append(f"{SPINE_FILE}: {len(beats)} beats; the article needs >= {wanted} (one per ~{CHARS_PER_BEAT} chars)")
    problems += [f"{SPINE_FILE}: section {a!r} has {size} chars and no beat"
                 for a, size in sections.items() if size > BIG_SECTION_CHARS and a not in covered]
    return problems
