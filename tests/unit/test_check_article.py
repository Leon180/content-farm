"""scripts/check_article.py — article.md / sources.json / outline consistency."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILLER = "台積電把晶片和記憶體擺在同一塊矽板上，像把樂高積木拼在同一塊底板。" * 80

SOURCE = {
    "id": "tsmc-q2",
    "title": "TSMC 2Q Earnings Call",
    "url": "https://investor.tsmc.com/x",
    "note": "publisher=TSMC; published=2026-07-17; accessed=2026-10-15; type=primary",
}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_article", ROOT / "scripts/check_article.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _article(extra: str = "") -> str:
    sections = "\n\n".join(
        f"## 段落 {{#{a}}}\n\n內文。" for a in
        ("a-hook", "a-timeline", "a-numbers", "a-chain", "a-taiwan", "a-unknowns")
    )
    return (
        "# 標題\n\n> 論點：測試\n\n"
        f"{sections}\n\n{FILLER}\n\n產能翻倍到 3 萬片 [src:tsmc-q2]。\n{extra}\n\n"
        "## 附錄 A {#a-gossip}\n\n軼事 [src:tsmc-q2]\n\n## 附錄 B {#a-jokes}\n\n笑話\n"
    )


def _run(tmp_path: Path, article: str, sources: list[dict[str, Any]],
         outline: dict[str, Any] | None = None) -> int:
    (tmp_path / "article.md").write_text(article, encoding="utf-8")
    (tmp_path / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    if outline is not None:
        (tmp_path / "deck_outline.json").write_text(json.dumps(outline), encoding="utf-8")
    return _load().main(["--run-dir", str(tmp_path)])


def _outline(**slide: Any) -> dict[str, Any]:
    base = {"id": "s01", "article_refs": ["a-hook"], "source_ids": ["tsmc-q2"]}
    return {"sections": [{"slides": [{**base, **slide}]}]}


def test_clean_run_passes(tmp_path: Path) -> None:
    assert _run(tmp_path, _article(), [SOURCE], _outline()) == 0


@pytest.mark.parametrize(("extra", "sources", "message"), [
    ("沒來源的數字 42。", [SOURCE], "has a number but no"),
    ("引用 [src:ghost]。", [SOURCE], "unknown source 'ghost'"),
    ("", [SOURCE, {**SOURCE, "id": "unused"}], "'unused' is never cited"),
    ("", [{**SOURCE, "note": "publisher=TSMC"}], "accessed="),
    ("", [{**SOURCE, "url": ""}], "http(s)"),
])
def test_article_problems_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                   extra: str, sources: list[dict[str, Any]], message: str) -> None:
    assert _run(tmp_path, _article(extra), sources) == 1
    assert message in capsys.readouterr().err


def test_short_article_and_missing_anchor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    article = "# t\n\n## x {#a-hook}\n\n短 [src:tsmc-q2]\n"
    assert _run(tmp_path, article, [SOURCE]) == 1
    err = capsys.readouterr().err
    assert "target 2500-4000" in err
    assert "{#a-timeline}" in err


@pytest.mark.parametrize(("slide", "message"), [
    ({"article_refs": []}, "no article_refs"),
    ({"article_refs": ["a-nowhere"]}, "unknown anchor"),
    ({"source_ids": ["ghost"]}, "unknown source"),
])
def test_outline_mapping(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                         slide: dict[str, Any], message: str) -> None:
    assert _run(tmp_path, _article(), [SOURCE], _outline(**slide)) == 1
    assert message in capsys.readouterr().err


def test_missing_files_exit_2(tmp_path: Path) -> None:
    assert _load().main(["--run-dir", str(tmp_path)]) == 2
