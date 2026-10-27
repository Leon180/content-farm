"""Cut listening-test clips of the sentences that contain hard words (Leon 2026-10-25: pronunciation check by ear).

    python scripts/audio_check_clips.py --run-dir output/fable-x --out artifacts/fable-ep2/audio-check/x --words 喬 莊 獾

Each sentence of ``audio/speech_check.json``'s ``tts_text`` that holds one of the words is cut from its scene mp3, its
position estimated by character share of the scene (± ~1 s, so a 0.6 s margin is added on both sides). ``README.md``
lists, per clip, the text sent to the voice and what the ASR read back (the whole scene).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

MARGIN = 0.6


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def sentences(text: str) -> list[str]:
    return [s for s in re.findall(r"[^。！？!?]+[。！？!?」]*", text) if s.strip()]


def clips(run_dir: Path, out: Path, words: list[str]) -> list[dict]:
    check = json.loads((run_dir / "audio" / "speech_check.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for scene, info in sorted(check.items()):
        parts = sentences(info["tts_text"])
        total = sum(len(p) for p in parts) or 1
        length = duration(run_dir / "audio" / scene)
        cursor = 0
        for n, part in enumerate(parts, 1):
            start, end = cursor / total * length, (cursor + len(part)) / total * length
            cursor += len(part)
            hit = [w for w in words if w in part]
            if not hit:
                continue
            name = f"{scene.removesuffix('.mp3')}-s{n}.mp3"
            begin = max(0.0, start - MARGIN)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{begin:.2f}", "-t", f"{end - begin + MARGIN:.2f}",
                            "-i", str(run_dir / "audio" / scene), "-c:a", "libmp3lame", "-q:a", "4", str(out / name)], check=True)
            rows.append({"file": name, "words": hit, "tts": part, "heard": info["hypothesis"], "cer": info["cer"]})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--words", nargs="+", required=True)
    args = parser.parse_args()
    rows = clips(args.run_dir, args.out, args.words)
    lines = ["# 試聽檔（含難字的句子）\n", "每檔＝一句，位置依字數比例估計（前後各多 0.6 秒）。「送進 TTS」是實際念的字（發音表替換後），「回讀」是整個場景的 ASR 結果。\n"]
    for r in rows:
        lines.append(f"- `{r['file']}`（{'、'.join(r['words'])}；場景 CER {r['cer']}）\n  - 送進 TTS：{r['tts']}\n  - 回讀（整場景）：{r['heard']}")
    (args.out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(rows)} clips -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
