"""Spans of subtitle text that must never be split across lines or cues.

An *atom* is a Latin/number token plus, for numbers, the unit that follows:
``CoWoS-L``, ``HBM3E``, ``3.2–3.5``, ``1,000``, ``59%``, ``2026 年``,
``3 奈米``, ``830 平方毫米``, ``US$ 1 萬``. Breaking inside one ("2025" / "年",
"Co" / "WoS", "3." / "2") reads badly in both Shorts and landscape subtitles.

Both splitters (``line_wrap`` for lines, ``estimation._split_text`` for cues)
ask :func:`is_safe_break` before cutting.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# Longest first, so "平方毫米" wins over "毫米" and "萬片" over "萬".
_UNITS = (
    "平方毫米", "平方公尺", "年代", "奈米", "毫米", "微米", "公分", "公尺", "公里", "公斤",
    "萬片", "萬人", "萬元", "億元", "兆元", "美元", "台幣", "小時", "分鐘",
    "%", "％", "元", "萬", "億", "兆", "千", "百", "年", "月", "日", "號", "週", "天", "秒",
    "片", "張", "顆", "座", "家", "間", "支", "個", "倍", "成", "度", "歲", "位", "名",
    "次", "層", "代", "季", "吋", "族",
)
_TOKEN = r"[A-Za-z0-9]+(?:[.\-–~/+:,'’][A-Za-z0-9]+)*%?"
_PREFIX = r"(?:(?:NT|US)?\$\s?|第\s?)?"
_UNIT = "|".join(re.escape(u) for u in _UNITS)
_ATOM = re.compile(rf"{_PREFIX}{_TOKEN}(?:(?<=[0-9])\s?(?:{_UNIT})|(?<=[A-Za-z])\s?版)?")   # 「L 版」 too (v3)


def protected_spans(text: str) -> tuple[tuple[int, int], ...]:
    """``(start, end)`` of every atom in ``text``; a break strictly inside one is unsafe."""
    return tuple((m.start(), m.end()) for m in _ATOM.finditer(text) if m.end() - m.start() > 1)


def is_safe_break(text: str, index: int, spans: Sequence[tuple[int, int]] | None = None) -> bool:
    """True if cutting ``text`` into ``text[:index]`` / ``text[index:]`` splits no atom."""
    if index <= 0 or index >= len(text):
        return True
    return not any(start < index < end for start, end in (spans if spans is not None else protected_spans(text)))


def broken_atoms(text: str, pieces: Sequence[str]) -> tuple[str, ...]:
    """Atoms of ``text`` that the boundaries between consecutive ``pieces`` cut through.

    ``pieces`` are what a splitter made of ``text`` (cues or lines); splitters
    drop the whitespace at a cut, so positions are compared with whitespace
    removed. Raises ``ValueError`` if the pieces are not ``text`` in order.
    """
    compact = [i for i, ch in enumerate(text) if not ch.isspace()]  # compact pos -> text index
    joined = "".join(ch for piece in pieces for ch in piece if not ch.isspace())
    if joined != "".join(text[i] for i in compact):
        raise ValueError("pieces do not spell out the text")
    cuts, pos = [], 0
    for piece in pieces[:-1]:
        pos += sum(1 for ch in piece if not ch.isspace())
        cuts.append(pos)
    to_compact = {index: n for n, index in enumerate(compact)}
    hits = []
    for start, end in protected_spans(text):
        c_start = to_compact.get(start, 0)
        c_end = to_compact[end - 1] + 1
        if any(c_start < cut < c_end for cut in cuts):
            hits.append(text[start:end])
    return tuple(hits)
