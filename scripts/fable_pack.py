"""Assemble an upload-pack folder (metadata.md, kit/, pinned-comment.txt, video.mp4, thumbnails) for one fable run.

    python scripts/fable_pack.py --run-dir output/fable-x --spec pack_spec.json --out output/upload-20261027/fable-x

``pack_spec.json`` (hand-written per video; everything else is read from the run-dir):
    {"summary": "...", "alt_titles": ["..."], "tags": ["..."], "hashtags": ["#..."], "chapters": ["0:00 ...", ...],
     "references": ["Author (year), title", ...], "synthetic_reason": "...", "notes": ["..."], "pinned": "...",
     "wan_ranges": ["0:00–0:06 ..."]}
The video is the run's ``assembly/release.mp4`` with the audio loudness-normalised to -14 LUFS (video stream copied).
Nothing is uploaded; check the result with ``scripts/upload_pack.py --dry-run --pack-dir <parent>``.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

from content_farm.production.fable import model

DESCRIPTION_MAX_BYTES = 4800
LICENSES = ("AI 示意圖 / AI illustrations：本片插圖由 AI 生成（Z-Image-Turbo (4-bit)，模型授權 Apache-2.0，"
            "https://github.com/Tongyi-MAI/Z-Image/blob/main/LICENSE），是原創動物寓言的示意畫，不是史料或實景。")
WAN_LICENSE = ("動態 / motion：部分鏡頭由 Wan2.2-TI2V-5B (MLX q8) 生成動畫（Apache-2.0，https://github.com/Wan-Video/Wan2.2/blob/main/LICENSE.txt），"
               "其餘為景深視差（Depth Anything V2 Small，工具）。")
DISCLAIMER = "角色與故事為原創寓言，只用來類比概念，現實比寓言複雜。配音為合成語音。本頻道不提供投資建議。"


def _run(args: list[str]) -> str:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{args[0]} failed: {proc.stderr[-400:]}")
    return proc.stderr


def duration(video: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def normalise(src: Path, dst: Path, target: float = -14.0) -> None:
    """Two-pass loudnorm; the video stream is copied."""
    stderr = _run(["ffmpeg", "-hide_banner", "-i", str(src), "-af", f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json",
                   "-vn", "-f", "null", "-"])
    stats = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.S).group(0))
    af = (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:"
          f"measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:offset={stats['target_offset']}")
    _run(["ffmpeg", "-y", "-hide_banner", "-i", str(src), "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "192k",
          "-movflags", "+faststart", str(dst)])


def clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def description(fable: model.Fable, spec: dict) -> str:
    parts = [spec["summary"]]
    if spec.get("chapters"):
        parts.append("章節：\n" + "\n".join(spec["chapters"]))
    parts.append("概念出處：\n" + "\n".join(f"• {r}" for r in (spec.get("references") or fable.concept.references)))
    wan = spec.get("wan_ranges") or []
    ai = LICENSES + ("\n" + WAN_LICENSE if wan else "")
    if wan:
        ai += "\nAI 動畫鏡頭時間點：" + "；".join(wan) + "。"
    parts.append(f"{ai}\n{DISCLAIMER}\n— 不奇而寓")
    parts.append(" ".join(spec["hashtags"]))
    text = "\n\n".join(parts)
    text, _ = re.subn(r"[<>]", "", text)
    if len(text.encode("utf-8")) > DESCRIPTION_MAX_BYTES:
        raise ValueError(f"description is {len(text.encode('utf-8'))} bytes (max {DESCRIPTION_MAX_BYTES})")
    return text


def metadata_md(fable: model.Fable, spec: dict, seconds: float, short: bool, desc: str) -> str:
    title = f"{fable.title} #Shorts" if short else fable.title
    size, kind = ("1080x1920", "Shorts 略過（`kit/cover_frame.png` 是建議封面格）") if short else ("1920x1080", "`thumbnail.jpg`（1280×720，變體 A；B／C 在 `kit/`）")
    alts = "\n".join(f"- {t}" for t in spec.get("alt_titles", []))
    notes = "\n".join(f"- {n}" for n in spec.get("notes", []))
    return (f"# 不奇而寓 — {fable.title}\n\n| 項目 | 設定 |\n|---|---|\n"
            f"| 影片檔 | `video.mp4`（{size} h264+aac，{clock(seconds)}（{seconds:.1f} 秒）） |\n| 縮圖 | {kind} |\n"
            "| 瀏覽權限 | 私人（Private），Leon 看過再改公開 |\n| 觀眾 | 否，這不是為兒童打造的內容 |\n| 類別 | 教育（Education） |\n"
            "| 語言 | 中文（台灣）zh-TW；字幕認證：無 |\n| 授權 | 標準 YouTube 授權；允許嵌入 |\n"
            "| 「經過修改或合成的內容」 | **否**（見下） |\n\n"
            f"理由：{spec['synthetic_reason']}\n\n## 標題（{len(title)}/100 字）\n\n{title}\n\n備選：\n{alts}\n\n"
            f"## 說明欄（整段貼上，{len(desc.encode('utf-8'))}/4800 bytes）\n\n```text\n{desc}\n```\n\n"
            f"## 標籤\n\n{', '.join(spec['tags'])}\n\n## 注意事項\n\n{notes}\n")


def to_jpeg(src: Path, dst: Path) -> None:
    Image.open(src).convert("RGB").resize((1280, 720)).save(dst, "JPEG", quality=92)


def build(run_dir: Path, spec: dict, out: Path) -> None:
    fable = model.load(run_dir)
    short = fable.format == "short"
    kit = out / "kit"
    kit.mkdir(parents=True, exist_ok=True)
    normalise(run_dir / "assembly" / "release.mp4", out / "video.mp4")
    seconds = duration(out / "video.mp4")
    desc = description(fable, spec)
    title = f"{fable.title} #Shorts" if short else fable.title
    (out / "metadata.md").write_text(metadata_md(fable, spec, seconds, short, desc), encoding="utf-8")
    (kit / "title.txt").write_text(title + "\n", encoding="utf-8")
    (kit / "description.txt").write_text(desc + "\n", encoding="utf-8")
    (kit / "tags.txt").write_text(", ".join(spec["tags"]) + "\n", encoding="utf-8")
    (out / "pinned-comment.txt").write_text(spec["pinned"].strip() + "\n", encoding="utf-8")
    shutil.copy(run_dir / "subtitles" / "subtitles.srt", kit / "subtitles.srt")
    thumbs = run_dir / "thumbnails"
    if short:
        cover = json.loads((thumbs / "cover_frame.json").read_text(encoding="utf-8"))
        shutil.copy(thumbs / "thumbnail.png", kit / "thumbnail.png")
        (kit / "cover_frame.json").write_text(json.dumps(cover, ensure_ascii=False, indent=2), encoding="utf-8")
        at = cover.get("seconds") or cover.get("at") or 0
        _run(["ffmpeg", "-y", "-hide_banner", "-ss", str(at), "-i", str(out / "video.mp4"), "-frames:v", "1", str(kit / "cover_frame.png")])
        return
    for letter in "abc":
        variant = thumbs / f"variant_{letter}.jpg"
        if variant.is_file():
            shutil.copy(variant, kit / f"thumbnail_{letter.upper()}.jpg")
    to_jpeg(thumbs / "variant_a.jpg" if (thumbs / "variant_a.jpg").is_file() else thumbs / "thumbnail.png", out / "thumbnail.jpg")
    shutil.copy(thumbs / "thumbnail.png", kit / "thumbnail.png")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build(args.run_dir, json.loads(args.spec.read_text(encoding="utf-8")), args.out)
    print(f"pack written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
