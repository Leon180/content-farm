"""What each stage's panel may read, copied into ``review/<stage>/round-N/`` so a reviewer never
needs anything outside its round folder. ``corpus`` is the text an issue's ``evidence`` quote is
checked against (issues that quote nothing in the material are dropped as unverifiable).
"""

from __future__ import annotations

import json
import random
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from content_farm.review.sentences import Sentence, deck_sentences, listing, script_sentences


@dataclass
class Materials:
    files: list[str]                                   # paths relative to the round dir, with a note each
    notes: dict[str, str] = field(default_factory=dict)
    corpus: str = ""
    sentences: list[Sentence] = field(default_factory=list)
    duration: float = 0.0                              # seconds (video stages)
    extra: dict[str, Any] = field(default_factory=dict)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _copy(src: Path, out: Path, name: str | None = None) -> str:
    target = out / (name or src.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return target.relative_to(out).as_posix()


def _put(out: Path, name: str, text: str) -> str:
    target = out / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return name


def topic(run_dir: Path, out: Path, **_: Any) -> Materials:
    data = _read_json(run_dir / "topics" / "candidates.json")
    candidates = data["candidates"] if isinstance(data, dict) else data
    order = list(candidates)
    random.Random(f"topics:{out.name}").shuffle(order)          # order differs every round
    lines = [f"[{c['id']}] {c['title']}\n  鉤子：{c.get('hook', '')}\n  預估片長：{c.get('minutes', '?')} 分\n"
             f"  來源：{'；'.join(str(s) for s in c.get('sources', []))}\n  備註：{c.get('note', '')}" for c in order]
    text = "\n\n".join(lines) + "\n"
    files = [_put(out, "candidates.txt", text)]
    past = run_dir / "topics" / "channel_history.txt"
    if past.is_file():
        files.append(_copy(past, out))
    return Materials(files, {files[0]: "候選題目（順序每輪不同）", **({files[1]: "頻道已做過的題目"} if len(files) > 1 else {})},
                     corpus=text, extra={"candidate_ids": [c["id"] for c in candidates]})


def article(run_dir: Path, out: Path, **_: Any) -> Materials:
    a = _copy(run_dir / "article.md", out)
    s = _copy(run_dir / "sources.json", out)
    corpus = (out / a).read_text(encoding="utf-8")
    return Materials([a, s], {a: "文章（每個數字、八卦都應附來源 id）", s: "來源清單（id、標題、網址）"}, corpus=corpus,
                     extra={"source_ids": _source_ids(out / s)})


def _source_ids(path: Path) -> list[str]:
    data = _read_json(path)
    items = data.get("sources", data) if isinstance(data, dict) else data
    return [str(i.get("id")) for i in items if isinstance(i, dict)]


DELTA_CONTEXT = 1   # neighbours shown on each side of an edited sentence in a delta fact-check


def _delta_listing(sentences: list[Sentence], only: frozenset[str]) -> str:
    """The edited sentences (★) with ``DELTA_CONTEXT`` neighbours each side; the rest left out."""
    marks = [i for i, s in enumerate(sentences) if s.id in only]
    keep = sorted({j for i in marks for j in range(i - DELTA_CONTEXT, i + DELTA_CONTEXT + 1) if 0 <= j < len(sentences)})
    lines = [("★ " if sentences[j].id in only else "  ") + listing([sentences[j]]).strip().splitlines()[-1] for j in keep]
    return ("差異查核：事實段已核可，這次只審標 ★ 的句子（核可後被改寫）；沒標的是前後文，不審。\n\n"
            + "\n".join(lines) + "\n")


def script(run_dir: Path, out: Path, *, id_field: str = "sentence_ids", only: frozenset[str] | None = None,
           **_: Any) -> Materials:
    deck = _read_json(run_dir / "deck.json")
    sentences = deck_sentences(deck, id_field)
    full = f"# {deck.get('title', '')}\n\n" + listing(sentences)
    text = full if only is None else f"# {deck.get('title', '')}\n\n" + _delta_listing(sentences, only)
    files = [_put(out, "script.txt", text)]
    notes = {files[0]: "講稿逐句（[句子 id] ~預估時間 句子）；指認問題時用句子 id"
             + ("；★＝這次要審的句子" if only is not None else "")}
    visual = []
    for section in deck.get("sections", []):
        for slide in section.get("slides", []):
            media = slide.get("media") or {}
            visual.append(f"[{slide.get('id')}] {slide.get('layout')}｜{slide.get('heading')}｜media={media.get('kind', 'slide')}"
                          f"{'｜' + media.get('diagram', '') if media.get('diagram') else ''}")
    files.append(_put(out, "storyboard.txt", "\n".join(visual) + "\n"))
    notes[files[-1]] = "分鏡（每張投影片的版型、標題、畫面種類）"
    for name, note in (("slides/contact_sheet.png", "投影片總覽圖"), ("article.md", "原始文章（事實依據）"),
                       ("sources.json", "來源清單"), ("promise.txt", "這支片答應觀眾什麼")):
        if (run_dir / name).is_file():
            files.append(_copy(run_dir / name, out, Path(name).name))
            notes[files[-1]] = note
    corpus = full + "\n".join(visual) + ((run_dir / "article.md").read_text(encoding="utf-8")
                                         if (run_dir / "article.md").is_file() else "")
    return Materials(files, notes, corpus=corpus, sentences=sentences,
                     extra={"source_ids": _source_ids(run_dir / "sources.json") if (run_dir / "sources.json").is_file() else []})


def short_script(run_dir: Path, out: Path, **_: Any) -> Materials:
    data = _read_json(run_dir / "script.json")
    sentences = script_sentences(data)
    text = f"# {data.get('video_title', '')}\n\n" + listing(sentences)
    files = [_put(out, "script.txt", text)]
    return Materials(files, {files[0]: "Short 講稿逐句"}, corpus=text, sentences=sentences)


def titles_text(run_dir: Path) -> tuple[list[dict], str]:
    data = _read_json(run_dir / "titles.json")
    titles = data["titles"] if isinstance(data, dict) else data
    return titles, "\n".join(f"[{t['id']}] {t['text']}" for t in titles) + "\n"


def title_thumb(run_dir: Path, out: Path, *, feeds: list[str] | None = None, **_: Any) -> Materials:
    titles, text = titles_text(run_dir)
    files = [_put(out, "titles.txt", text)]
    notes = {files[0]: "標題候選（[id] 標題）"}
    variants = sorted(p for p in (run_dir / "thumbnails").glob("variant_*.jpg") if "_phone" not in p.stem)
    for path in variants:
        files.append(_copy(path, out, f"thumbnails/{path.name}"))
        notes[files[-1]] = f"縮圖 {path.stem.split('_')[-1].upper()}"
    spec = run_dir / "thumbnail.json"
    corpus = text + (spec.read_text(encoding="utf-8") if spec.is_file() else "")
    if spec.is_file():
        files.append(_copy(spec, out))
        notes[files[-1]] = "縮圖文案與承諾（promise＝講稿裡兌現的原句）"
    if (run_dir / "deck.json").is_file():
        deck = _read_json(run_dir / "deck.json")
        summary = listing(deck_sentences(deck))
        files.append(_put(out, "script.txt", summary))
        notes[files[-1]] = "講稿（用來確認標題縮圖沒有誇大）"
        corpus += summary
    return Materials(files, notes, corpus=corpus,
                     extra={"title_ids": [t["id"] for t in titles],
                            "variants": [p.stem.split("_")[-1].upper() for p in variants], "feeds": feeds or []})


def media(run_dir: Path, out: Path, **_: Any) -> Materials:
    files, notes = [], {}
    for name, note in (("media/contact_sheet.png", "素材總覽"), ("media/media_report.json", "每張用了什麼"),
                       ("credits.json", "授權紀錄")):
        if (run_dir / name).is_file():
            files.append(_copy(run_dir / name, out, Path(name).name))
            notes[files[-1]] = note
    for path in sorted((run_dir / "assets" / "ai_images").glob("*.png"))[:40]:
        files.append(_copy(path, out, f"ai_images/{path.name}"))
        notes[files[-1]] = "AI 插圖"
    credits = _read_json(run_dir / "credits.json") if (run_dir / "credits.json").is_file() else {}
    corpus = json.dumps(credits, ensure_ascii=False)
    return Materials(files, notes, corpus=corpus, extra={"pending": credits.get("pending", [])})


BUILDERS = {"topic": topic, "shorts_topic": topic, "article": article, "script_structure": script,
            "script_facts": script,
            "shorts_script": short_script, "title_thumb": title_thumb, "shorts_title": title_thumb,
            "media": media}
