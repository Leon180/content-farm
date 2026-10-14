"""Builders for explainer deck tests (plain dicts, so tests can break them)."""

from __future__ import annotations

import copy
from typing import Any

NARRATION = "晶圓代工就像代工廚房，客戶給食譜，台積電負責把菜穩定地煮出來，而且一次煮一萬盤都不能走味。"


def slide(sid: str, layout: str = "bullets", **overrides: Any) -> dict[str, Any]:
    bodies: dict[str, dict[str, Any]] = {
        "title": {"subtitle": "副標"},
        "bullets": {"items": ["第一點", "第二點", "第三點"]},
        "big_number": {"value": "60", "unit": "%", "caption": "說明"},
        "compare": {
            "left": {"label": "左", "items": ["a"]},
            "right": {"label": "右", "items": ["b"]},
        },
        "timeline": {"events": [{"when": "1987", "what": "成立"}, {"when": "2020", "what": "5nm"}]},
        "quote": {"text": "引言", "who": "某人"},
    }
    data: dict[str, Any] = {
        "id": sid,
        "layout": layout,
        "heading": f"標題 {sid}",
        "body": bodies[layout],
        "narration": NARRATION,
    }
    data.update(overrides)
    return data


def deck_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "version": 1,
        "category": "tech",
        "title": "台積電到底賺什麼錢",
        "as_of": "2026-10",
        "sources": [{"id": "s1", "title": "年報", "url": "https://example.com/ar"}],
        "pronunciation_map": {"TSMC": "T S M C"},
        "sections": [
            {"title": "開場", "slides": [slide("a1", "title")]},
            {"title": "本體", "slides": [slide("b1", "big_number", source_ids=["s1"]),
                                        slide("b2", "compare")]},
            {"title": "結尾", "slides": [slide("c1", "quote")]},
        ],
    }
    data.update(overrides)
    return copy.deepcopy(data)
