"""Article sentences with positional ids, quote → sentence lookup, and the delete-or-edit-only
check for article reworks (Leon 2026-10-18 decision 59fdefb32bd7 = D).

From round 2 on, a rewrite may only delete a flagged sentence or edit it in place (add a
qualifier such as 「據報導」「估計」, correct a number or an attribution). It may not add
sentences, and every sentence nobody flagged must stay word for word. ``check_rework`` compares
the article before and after the rewrite and lists every violation.

Ids are ``p<paragraph>.<n>`` (a paragraph = a non-blank line, so a table row or heading is its
own paragraph). They are positional and only used to name sentences in messages: the
comparison itself aligns the two versions by text (difflib), so a deleted sentence does not
shift what counts as changed.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"(?<=[。！？!?])")
_NORMALIZE = re.compile(r"[\s「」『』“”\"'‘’，,。．.！!？?：:；;、（）()\[\]【】—\-…~～|*#>`]+")
EDIT_SIMILARITY_MIN = 0.5      # an in-place edit keeps at least half the sentence (difflib ratio)


@dataclass(frozen=True)
class ArticleSentence:
    id: str
    text: str


def normalize(text: str) -> str:
    return _NORMALIZE.sub("", text or "").lower()


def split_article(markdown: str) -> list[ArticleSentence]:
    out: list[ArticleSentence] = []
    paragraph = 0
    for line in markdown.splitlines():
        if not line.strip():
            continue
        paragraph += 1
        parts = [p.strip() for p in _SENTENCE_END.split(line.strip()) if p.strip()]
        out += [ArticleSentence(f"p{paragraph}.{n}", part) for n, part in enumerate(parts, 1)]
    return out


def sentences_for_quote(quote: str, sentences: list[ArticleSentence]) -> list[str]:
    """Ids of the sentences a verbatim quote overlaps ([] when the quote is not in the article)."""
    needle = normalize(quote)
    if len(needle) < 2:
        return []
    spans, cursor, joined = [], 0, []
    for sentence in sentences:
        text = normalize(sentence.text)
        spans.append((cursor, cursor + len(text), sentence.id))
        joined.append(text)
        cursor += len(text)
    start = "".join(joined).find(needle)
    if start < 0:
        return []
    end = start + len(needle)
    return [sid for lo, hi, sid in spans if lo < end and hi > start]


def flagged_sentences(quotes: list[str], sentences: list[ArticleSentence]) -> set[str]:
    return {sid for quote in quotes for sid in sentences_for_quote(quote, sentences)}


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def check_rework(before: str, after: str, flagged: set[str]) -> list[str]:
    """Why ``after`` is not a delete-or-edit-only rewrite of ``before`` ([] = it is)."""
    old, new = split_article(before), split_article(after)
    matcher = difflib.SequenceMatcher(None, [normalize(s.text) for s in old], [normalize(s.text) for s in new],
                                      autojunk=False)
    problems = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        removed, added = old[i1:i2], new[j1:j2]
        unflagged = [s for s in removed if s.id not in flagged]
        if unflagged:
            problems += [f"{s.id} 沒有被點名，不能刪改：「{s.text[:40]}」" for s in unflagged]
        if len(added) > len(removed):
            extra = added[len(removed):]
            problems += [f"新增句子（第 2 輪起只准刪改）：「{s.text[:40]}」" for s in extra]
        for was, now in zip(removed, added):
            if was.id in flagged and _similar(was.text, now.text) < EDIT_SIMILARITY_MIN:
                problems.append(f"{was.id} 改寫幅度太大（不是加限定詞／改數字或歸屬）：「{was.text[:30]}」→「{now.text[:30]}」")
    return problems
