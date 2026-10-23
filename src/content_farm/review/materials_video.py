"""Materials for the stages that look at pictures or video: homepage feeds (title & thumbnail)
and the finished cut (frame sheets, subtitles, audio description, objective metrics) — reusing
the cowos-v3 eval tooling (``evaluation/``)."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from content_farm.evaluation import homepage
from content_farm.review.materials import Materials, _copy, _put, titles_text
from content_farm.review.sentences import deck_sentences


def homepage_feeds(out: Path, rid: str, variants: dict[str, Path], title: str, channel_name: str,
                   competitors_dir: Path | None) -> tuple[list[str], dict]:
    """Phone feeds (one per variant) with our card hidden among competitors; returns names + answer key."""
    if competitors_dir is None or not (competitors_dir / "competitors.json").is_file():
        return [], {}
    competitors = homepage.load_competitors(competitors_dir)
    order = list(variants)
    random.Random(f"variants:{rid}:{out.name}").shuffle(order)
    names, keys = [], {}
    for n, key in enumerate(order, 1):
        ours = homepage.Card(variants[key], title, channel_name, ours=True)
        cards = homepage.arrange(ours, competitors, seed=f"{rid}:{key}:{out.name}")
        name = f"feeds/{rid}_feed{n}.jpg"
        homepage.feed_image(cards, out / name)
        keys[Path(name).name] = {"variant": key, "ours_card": next(i + 1 for i, c in enumerate(cards) if c.ours),
                                 "cards": len(cards)}
        names.append(name)
    return names, keys


def variant_images(run_dir: Path) -> dict[str, Path]:
    return {p.stem.split("_")[-1].upper(): p for p in sorted((run_dir / "thumbnails").glob("variant_*.jpg"))
            if "_phone" not in p.stem}


def best_title(run_dir: Path) -> str:
    """The title the title & thumbnail panel picked (``review/title.choice.json``), else the first."""
    titles, _ = titles_text(run_dir)
    choice = run_dir / "review" / "title.choice.json"
    best = json.loads(choice.read_text(encoding="utf-8")).get("best_title") if choice.is_file() else None
    chosen = next((t for t in titles if str(t["id"]) == str(best)), titles[0])
    return str(chosen["text"])


NO_MIX_NOTE = ("【本頻道無混音】channels 設定沒有開 audio.mix：成片沒有配樂（BGM）也沒有音效，這是頻道設定，不是缺陷。"
               "請不要以配樂、BGM 與人聲比例、ducking、音效位置扣分，也不要把問題歸因到 mix。\n")


def audio_mix_enabled(run_dir: Path) -> bool:
    """Whether the run's channel mixes BGM / SFX (``audio.enabled``). True when the channel cannot be read, so
    a run-dir without ``production.json`` is judged by the full audio standard as before."""
    from content_farm.production.channels import load_channel
    from content_farm.production.state import read_channel_code

    try:
        return load_channel(read_channel_code(run_dir)).audio.enabled
    except (OSError, ValueError, KeyError):
        return True


def without_audio(report: dict) -> dict:
    """The retention report without its sound measurements: sound is not judged by the panels (Leon 2026-10-23)."""
    return {k: v for k, v in report.items() if k != "audio"}


def final(run_dir: Path, out: Path, *, vertical: bool = False, **_: Any) -> Materials:
    from content_farm.evaluation.sheets import build_sheets, extract_frames, mmss
    from content_farm.retention.report import build_report, upload_video

    video = upload_video(run_dir)
    if video is None:
        raise FileNotFoundError(f"{run_dir}/assembly has no video to review")
    report = build_report(run_dir, vertical=vertical)
    files = [_put(out, "objective.json", json.dumps(without_audio(report), ensure_ascii=False, indent=1))]
    notes = {files[0]: "自動量測（節拍、靜止、死區……；聲音不在評審範圍）"}
    frames = extract_frames(video, run_dir / "review" / ".frames")
    for sheet in build_sheets(frames, out / "sheets"):
        files.append(sheet.relative_to(out).as_posix())
        notes[files[-1]] = "畫面截圖表（每 5 秒一格、每張 6 格、左上角是時間戳）"
    files.append(_copy(run_dir / "subtitles" / "subtitles.srt", out))
    notes[files[-1]] = "旁白逐字稿（含時間）"
    mix = audio_mix_enabled(run_dir)
    corpus = (out / "subtitles.srt").read_text(encoding="utf-8")
    if (run_dir / "titles.json").is_file():
        files.append(_put(out, "title.txt", best_title(run_dir) + "\n"))
        notes[files[-1]] = "正式標題"
    for key, path in variant_images(run_dir).items():
        files.append(_copy(path, out, f"thumbnails/variant_{key}.jpg"))
        notes[files[-1]] = f"縮圖 {key}（確認跟影片內容一致）"
    if (run_dir / "deck.json").is_file():
        sentences = deck_sentences(json.loads((run_dir / "deck.json").read_text(encoding="utf-8")))
    else:
        sentences = []
    return Materials(files, notes, corpus=corpus, sentences=sentences, duration=float(report["duration"]),
                     extra={"objective": report, "duration_text": mmss(report["duration"]), "audio_mix": mix,
                            "sentence_times": sentence_times(run_dir, sentences)})


def sentence_times(run_dir: Path, sentences: list) -> list[list]:
    """``[id, start, end]`` per deck sentence from the voice step's measured scene lengths (whisper-aligned
    when the subtitles match), so a viewer's m:ss can be turned into sentence ids. [] when it cannot line up."""
    from content_farm.retention.timing import sentence_timeline

    try:
        timed = sentence_timeline(run_dir)
    except (OSError, ValueError, KeyError):
        return []
    if not sentences or len(timed) != len(sentences):
        return []
    return [[s.id, t.start, t.end] for s, t in zip(sentences, timed)]
