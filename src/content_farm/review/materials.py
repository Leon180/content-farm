"""What each stage's panel may read, copied into ``review/<stage>/round-N/`` so a reviewer never
needs anything outside its round folder. ``corpus`` is the text an issue's ``evidence`` quote is
checked against (issues that quote nothing in the material are dropped as unverifiable).
"""

from __future__ import annotations

import hashlib
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
    audience: dict[str, tuple[str, ...]] = field(default_factory=dict)   # file → reviewer kinds shown it (absent: all)
    derived: frozenset[str] = frozenset()              # files that picture other files: left out of cache keys
    content_key: str | None = None                     # digest of the content when the files themselves are volatile

    def visible_to(self, kind: str) -> Materials:
        """The files a reviewer of ``kind`` is shown (a viewer never gets sources.json, a fact-checker never the
        storyboard picture …): what it is not shown it does not read, and does not pay for."""
        files = [f for f in self.files if kind in self.audience.get(f, (kind,))]
        return Materials(files, {f: n for f, n in self.notes.items() if f in files}, self.corpus, self.sentences,
                         self.duration, self.extra, self.audience, self.derived, self.content_key)


VIEWERS, PROS, FACTS, PRODUCERS, DESIGNERS = "viewer", "pro", "fact", "producer", "designer"


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
             + (f"  來源：{'；'.join(str(s) for s in c.get('sources', []))}\n" if c.get('sources') else "")
             + f"  備註：{c.get('note', '')}" for c in order]
    text = "\n\n".join(lines) + "\n"
    files = [_put(out, "candidates.txt", text)]
    past = run_dir / "topics" / "channel_history.txt"
    if past.is_file():
        files.append(_copy(past, out))
    stable = "\n".join(sorted(lines)) + (past.read_text(encoding="utf-8") if past.is_file() else "")   # order is per-round
    return Materials(files, {files[0]: "候選題目（順序每輪不同）", **({files[1]: "頻道已做過的題目"} if len(files) > 1 else {})},
                     corpus=text, extra={"candidate_ids": [c["id"] for c in candidates]},
                     audience={files[1]: (PROS, PRODUCERS)} if len(files) > 1 else {},
                     content_key=hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24])


def article(run_dir: Path, out: Path, *, only: frozenset[str] | None = None, **_: Any) -> Materials:
    if only is None and (fresh := _structure_rewrite_ids(run_dir)):
        # the script panel sent the article back for its structure: the unchanged sentences passed the fact check
        # and the program verified their numbers / source ids did not move, so only the new ones are checked
        from content_farm.review.article_diff import mark_article

        a = _put(out, "article.md", mark_article((run_dir / "article.md").read_text(encoding="utf-8"), fresh))
        note = ("文章（結構改寫後的差異查核：只審標 ★ 的新句，每一句的數字、八卦、因果都要回來源查；沒標的句子前一輪已通過事實查核、"
                "數字與來源 id 經程式比對沒有變，當前後文讀就好）")
    elif only is None:
        a = _copy(run_dir / "article.md", out)
        note = "文章（每個數字、八卦都應附來源 id）"
    else:    # delta fact-check: the earlier rounds already cleared the unmarked sentences
        from content_farm.review.article_diff import mark_article

        a = _put(out, "article.md", mark_article((run_dir / "article.md").read_text(encoding="utf-8"), only))
        note = "文章（差異查核：只審標 ★ 的句子，沒標的前幾輪已審過，當前後文讀就好；每個數字、八卦都應附來源 id）"
    s = _copy(run_dir / "sources.json", out)
    corpus = (out / a).read_text(encoding="utf-8").replace("★", "")
    return Materials([a, s], {a: note, s: "來源清單（id、標題、網址）"}, corpus=corpus,
                     extra={"source_ids": _source_ids(out / s)}, audience={s: (FACTS,)})


def _structure_rewrite_ids(run_dir: Path) -> frozenset[str]:
    """Ids of the article sentences new since a pending structure rewrite's fact-locked baseline."""
    from content_farm.production.panel_flow import changed_since_lock

    article_md = run_dir / "article.md"
    return frozenset(changed_since_lock(run_dir, article_md.read_text(encoding="utf-8"))) if article_md.is_file() else frozenset()


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
    audience: dict[str, tuple[str, ...]] = {}
    visual = []
    for section in deck.get("sections", []):
        for slide in section.get("slides", []):
            media = slide.get("media") or {}
            visual.append(f"[{slide.get('id')}] {slide.get('layout')}｜{slide.get('heading')}｜media={media.get('kind', 'slide')}"
                          f"{'｜' + media.get('diagram', '') if media.get('diagram') else ''}")
    files.append(_put(out, "storyboard.txt", "\n".join(visual) + "\n"))
    notes[files[-1]] = "分鏡（每張投影片的版型、標題、畫面種類）"
    audience[files[-1]] = (VIEWERS, PROS)
    # who needs what: viewers read the script and storyboard, not the sources; fact-checkers read the sentences and
    # the sources, not the pictures; only the professionals look at the contact sheet
    for name, note, kinds in (("slides/contact_sheet.png", "投影片總覽圖", (PROS,)),
                              ("article.md", "原始文章（事實依據）", (FACTS,)),
                              ("sources.json", "來源清單", (FACTS,)),
                              ("promise.txt", "這支片答應觀眾什麼", (VIEWERS, PROS))):
        if (run_dir / name).is_file():
            files.append(_copy(run_dir / name, out, Path(name).name))
            notes[files[-1]] = note
            audience[files[-1]] = kinds
    from content_farm.review import script_checks

    for name, note, text, kinds in (("hooks.txt", "伏筆帳本：每條埋下的線、誰收、現在狀態", script_checks.hooks_text(run_dir, deck), (PROS,)),
                                    ("coherence.txt", "程式找到的疑似前後矛盾（數量詞、清單項數）",
                                     script_checks.coherence_text(deck), (PROS, FACTS))):
        if text:
            files.append(_put(out, name, text))
            notes[files[-1]] = note
            audience[files[-1]] = kinds
    corpus = full + "\n".join(visual) + ((run_dir / "article.md").read_text(encoding="utf-8")
                                         if (run_dir / "article.md").is_file() else "")
    return Materials(files, notes, corpus=corpus, sentences=sentences,
                     extra={"source_ids": _source_ids(run_dir / "sources.json") if (run_dir / "sources.json").is_file() else []},
                     audience=audience, derived=frozenset({"contact_sheet.png"}))


def short_script(run_dir: Path, out: Path, **_: Any) -> Materials:
    data = _read_json(run_dir / "script.json")
    sentences = script_sentences(data)
    text = f"# {data.get('video_title', '')}\n\n" + listing(sentences)
    note = "Short 講稿逐句"
    extra: dict[str, Any] = {}
    if any(str(s.get("transition", "")).startswith("pause:") for s in data.get("scenes", [])):
        from content_farm.production import skit

        text = _skit_outline(data) + "\n" + text
        note = ("冷笑話小劇場劇本：先列場景結構（場景 id、鋪陳／笑點／收尾、金魚表情、停頓秒數），再逐句（[句子 id] ~預估時間 句子）；"
                "停頓是該場景之後的無聲留白，不是句子")
        extra["duration_text"] = f"約 {skit.estimated_seconds(data):g} 秒（字數估計，含停頓）"
    files = [_put(out, "script.txt", text)]
    return Materials(files, {files[0]: note}, corpus=text, sentences=sentences, extra=extra)


def _skit_outline(data: dict[str, Any]) -> str:
    from content_farm.production import skit

    lines = ["## 場景結構"]
    for scene in data.get("scenes", []):
        pause = skit.pause_after(scene)
        face = (scene.get("visual_hint") or {}).get("description", "")
        lines.append(f"[c{scene.get('scene_number')}] {skit.beat_of(scene) or scene.get('title')}｜金魚表情 {face}"
                     + (f"｜之後停頓 {pause:g} 秒" if pause else ""))
    return "\n".join(lines) + "\n"


def titles_text(run_dir: Path) -> tuple[list[dict], str]:
    data = _read_json(run_dir / "titles.json")
    titles = data["titles"] if isinstance(data, dict) else data
    return titles, "\n".join(f"[{t['id']}] {t['text']}" for t in titles) + "\n"


def title_thumb(run_dir: Path, out: Path, *, feeds: list[str] | None = None, **_: Any) -> Materials:
    titles, text = titles_text(run_dir)
    files = [_put(out, "titles.txt", text)]
    notes = {files[0]: "標題候選（[id] 標題）"}
    variants = sorted(p for p in (run_dir / "thumbnails").glob("variant_*.jpg") if "_phone" not in p.stem)
    audience: dict[str, tuple[str, ...]] = {}
    for path in variants:
        files.append(_copy(path, out, f"thumbnails/{path.name}"))
        notes[files[-1]] = f"縮圖 {path.stem.split('_')[-1].upper()}"
    spec = run_dir / "thumbnail.json"
    corpus = text + (spec.read_text(encoding="utf-8") if spec.is_file() else "")
    if spec.is_file():
        files.append(_copy(spec, out))
        notes[files[-1]] = "縮圖文案與承諾（promise＝講稿裡兌現的原句）"
        audience[files[-1]] = (DESIGNERS, PRODUCERS)
    if (run_dir / "deck.json").is_file():
        deck = _read_json(run_dir / "deck.json")
        summary = listing(deck_sentences(deck))
        files.append(_put(out, "script.txt", summary))
        notes[files[-1]] = "講稿（用來確認標題縮圖沒有誇大）"
        audience[files[-1]] = (PRODUCERS,)       # viewers judge title + picture; only the producer checks the promise
        corpus += summary
    return Materials(files, notes, corpus=corpus, audience=audience,
                     extra={"title_ids": [t["id"] for t in titles],
                            "variants": [p.stem.split("_")[-1].upper() for p in variants], "feeds": feeds or []})


def _live_ai_images(run_dir: Path) -> list[Path]:
    """The generated pictures of slides the current media report covers. A picture left behind by a slide that a
    later deck merged away is not delivered, so it is neither reviewed nor asked for credits (cf-cost-accept:
    s08b / s10 were orphans after deck-13 and failed the compliance panel three rounds in a row)."""
    paths = sorted((run_dir / "assets" / "ai_images").glob("*.png"))
    report = run_dir / "media" / "media_report.json"
    if not report.is_file():
        return paths[:40]
    live = {s.get("slide_id") for s in _read_json(report).get("slides", [])}
    return [p for p in paths if p.stem in live][:40] if live else paths[:40]


def _media_identity(run_dir: Path) -> str:
    """What the compliance reviewer's verdict depends on: each slide's media identity, the generated pictures'
    bytes and the credits — not the contact sheet (a picture of them) nor timings and timestamps."""
    parts: list[str] = []
    report = run_dir / "media" / "media_report.json"
    if report.is_file():
        for slide in _read_json(report).get("slides", []):
            parts.append(f"{slide.get('slide_id')}|{slide.get('identity')}|{slide.get('used')}|{slide.get('note')}")
    for path in _live_ai_images(run_dir):
        parts.append(f"{path.name}={hashlib.sha256(path.read_bytes()).hexdigest()[:16]}")
    credits = run_dir / "credits.json"
    if credits.is_file():
        from content_farm.review.cache import file_digest

        parts.append(f"credits={file_digest(credits)}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:24]


def media(run_dir: Path, out: Path, **_: Any) -> Materials:
    files, notes = [], {}
    for name, note in (("media/contact_sheet.png", "素材總覽"), ("media/media_report.json", "每張用了什麼"),
                       ("credits.json", "授權紀錄")):
        if (run_dir / name).is_file():
            files.append(_copy(run_dir / name, out, Path(name).name))
            notes[files[-1]] = note
    for path in _live_ai_images(run_dir):
        files.append(_copy(path, out, f"ai_images/{path.name}"))
        notes[files[-1]] = "AI 插圖"
    credits = _read_json(run_dir / "credits.json") if (run_dir / "credits.json").is_file() else {}
    corpus = json.dumps(credits, ensure_ascii=False)
    return Materials(files, notes, corpus=corpus, extra={"pending": credits.get("pending", [])},
                     derived=frozenset({"contact_sheet.png"}), content_key=_media_identity(run_dir))


BUILDERS = {"topic": topic, "shorts_topic": topic, "article": article, "script_structure": script,
            "script_facts": script,
            "shorts_script": short_script, "title_thumb": title_thumb, "shorts_title": title_thumb,
            "media": media}
