"""Prepare one review round: ``<run>/eval/round-N/`` with every file a reviewer may read,
one brief per reviewer, and the homepage feeds. The feed answer key goes to ``eval/.keys/``.

Materials: sheets (every 5 s, 6 per sheet), subtitles, title, description, thumbnail variants,
audio.txt (one plain-language line per 10 s), objective.json (the retention report).
"""

from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

from content_farm.evaluation import homepage
from content_farm.evaluation.briefs import pro_brief, viewer_brief
from content_farm.evaluation.panel import Panels, Reviewer, roster
from content_farm.evaluation.sheets import build_sheets, extract_frames, mmss
from content_farm.retention.report import build_report, upload_video

EVAL_DIR = Path("eval")


def round_dir(run_dir: Path, round_no: int) -> Path:
    return run_dir / EVAL_DIR / f"round-{round_no}"


def _variants(run_dir: Path) -> dict[str, Path]:
    found = {p.stem.split("_")[-1].upper(): p for p in sorted((run_dir / "thumbnails").glob("variant_*.jpg"))
             if "_phone" not in p.stem}
    if not found and (run_dir / "thumbnails" / "thumbnail.png").is_file():
        found = {"A": run_dir / "thumbnails" / "thumbnail.png"}
    return found


def audio_lines(report: dict) -> str:
    lines = [f"{mmss(w['t0'])}-{mmss(w['t1'])}  {w['describe']}" for w in report["audio"].get("windows", [])]
    misread = report["audio"].get("speech_check", {})
    if misread.get("flagged"):
        lines.append("")
        lines.append("自動轉寫比對（可能念錯的段落）：" + "；".join(misread["flagged"]))
    return "\n".join(lines) + "\n"


def _title_and_description(run_dir: Path) -> tuple[str, str]:
    script = json.loads((run_dir / "script.json").read_text(encoding="utf-8"))
    return script["video_title"], script.get("description", "")


def build_feeds(out: Path, keys: dict, reviewer: Reviewer, variants: dict[str, Path], title: str,
                channel_name: str, competitors_dir: Path | None) -> list[str]:
    if competitors_dir is None or not (competitors_dir / "competitors.json").is_file():
        return []
    competitors = homepage.load_competitors(competitors_dir)
    order = list(variants)
    random.Random(f"variants:{reviewer.rid}").shuffle(order)
    names = []
    for n, key in enumerate(order, 1):
        ours = homepage.Card(variants[key], title, channel_name, ours=True)
        for device in ("phone", "desktop"):
            cards = homepage.arrange(ours, competitors, seed=f"{reviewer.rid}:{key}:{device}")
            name = f"{reviewer.rid}_feed{n}_{device}.jpg"
            homepage.feed_image(cards, out / "feeds" / name, desktop=device == "desktop")
            keys[name] = {"variant": key, "ours_card": next(i + 1 for i, c in enumerate(cards) if c.ours),
                          "cards": len(cards), "device": device}
            if device == "phone":
                names.append(name)
    return names


def prepare_round(run_dir: Path, *, round_no: int, panels: Panels, stage: str, channel_code: str,
                  channel_name: str, final_round: bool, competitors_dir: Path | None = None,
                  holdout_only: bool = False, dir_name: str | None = None) -> dict:
    video = upload_video(run_dir)
    if video is None:
        raise FileNotFoundError(f"{run_dir}/assembly has no video to review")
    out = run_dir / EVAL_DIR / dir_name if dir_name else round_dir(run_dir, round_no)
    if out.exists():
        shutil.rmtree(out)
    (out / "results").mkdir(parents=True)
    report = build_report(run_dir)
    (out / "objective.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    frames = extract_frames(video, run_dir / EVAL_DIR / ".frames")
    sheets = build_sheets(frames, out / "sheets")
    shutil.copy2(run_dir / "subtitles" / "subtitles.srt", out / "subtitles.srt")
    title, description = _title_and_description(run_dir)
    (out / "title.txt").write_text(title + "\n", encoding="utf-8")
    (out / "description.txt").write_text(description + "\n", encoding="utf-8")
    (out / "audio.txt").write_text(audio_lines(report), encoding="utf-8")
    variants = _variants(run_dir)
    (out / "thumbnails").mkdir()
    for key, path in variants.items():
        shutil.copy2(path, out / "thumbnails" / f"variant_{key}{path.suffix}")
    reviewers = roster(panels, stage, channel_code, round_no, final_round=final_round, holdout_only=holdout_only)
    keys: dict = {}
    duration = mmss(report["duration"])
    entries = []
    (out / "briefs").mkdir()
    for reviewer in reviewers:
        result = out / "results" / f"{reviewer.rid}.json"
        if reviewer.kind == "viewer":
            feeds = build_feeds(out, keys, reviewer, variants, title, channel_name, competitors_dir) \
                if panels.stages[stage].homepage else []
            text = viewer_brief(reviewer, out, sheets=len(sheets), duration=duration, channel=channel_name,
                                feeds=feeds, result=result)
        else:
            text = pro_brief(reviewer, panels, out, sheets=len(sheets), duration=duration, channel=channel_name,
                             objective=out / "objective.json", result=result)
        brief = out / "briefs" / f"{reviewer.rid}.md"
        brief.write_text(text, encoding="utf-8")
        entries.append({"rid": reviewer.rid, "kind": reviewer.kind, "role": reviewer.role,
                        "holdout": reviewer.holdout, "brief": str(brief), "result": str(result)})
    key_dir = run_dir / EVAL_DIR / ".keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / f"{out.name}.json").write_text(json.dumps(keys, indent=1), encoding="utf-8")
    manifest = {"round": round_no, "stage": stage, "video": video.relative_to(run_dir).as_posix(),
                "duration": report["duration"], "variants": sorted(variants), "reviewers": entries,
                "final_round": final_round}
    (out / "round.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest
