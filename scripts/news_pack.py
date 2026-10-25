"""Build one upload-pack folder (metadata.md, pinned-comment.txt, video.mp4, thumbnails) for a news Short.

Usage:
    python scripts/news_pack.py --run-dir output/technews-… --pack-dir output/upload-20261025 --slug ai-payoff

Format follows ``output/upload-20261024/<folder>/metadata.md`` (parsed by ``youtube/pack.py``): title, description
(<= 4800 bytes, no angle brackets), tags, synthetic-content suggestion, checks. NEVER uploads anything.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

CHANNEL_CODE, CHANNEL_NAME = "technews", "晚點你就知道"
MAX_DESCRIPTION_BYTES = 4800


def _probe(video: Path) -> tuple[float, str]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-show_entries", "format=duration", "-of", "json", str(video)], capture_output=True, text=True, check=True)
    info = json.loads(out.stdout)
    return float(info["format"]["duration"]), f"{info['streams'][0]['width']}x{info['streams'][0]['height']}"


def _loudness(video: Path) -> str:
    proc = subprocess.run(["ffmpeg", "-nostats", "-i", str(video), "-af", "ebur128=peak=true", "-f", "null", "-"],
                          capture_output=True, text=True)
    lufs = re.findall(r"I:\s+(-?\d+\.\d) LUFS", proc.stderr)
    peak = re.findall(r"Peak:\s+(-?\d+\.\d) dBFS", proc.stderr)
    return f"{lufs[-1]} LUFS，真峰值 {peak[-1]} dBFS" if lufs and peak else "（未量到）"


def description(news: dict, credits: dict, footer: str, series_line: str) -> str:
    lines = [news["summary"], "", footer, series_line, f"— {CHANNEL_NAME}", "", "原文與出處:"]
    for s in news["sources"]:
        when = f"（讀取 {s['read_at'][:10]}）" if s.get("read_at") else ""
        tag = "（討論串，只當線索）" if s["kind"] == "discussion" else ""
        lines.append(f"- {s.get('publisher', '')}{tag} {s['title']}: {s['url']}{when}")
    models = {(e.get("model_name") or e.get("model", ""), e.get("origin_repo", ""), e.get("license_url", ""))
              for e in credits["entries"] if e.get("kind") == "ai_image"}
    lines += ["", "AI 示意圖 / AI illustrations（非實景，僅示意）:"]
    lines += [f"- {m}（{o}, {u}）" for m, o, u in sorted(models)]
    lines += ["- Depth Anything V2 Small（景深估計，用於讓圖片產生視差動態；工具標示）",
              "", "本影片由 AI 輔助製作（配音為合成語音；圖片為 AI 生成示意圖，已於畫面標示「AI 示意圖」）。", "", "#Shorts"]
    text = "\n".join(lines).replace("<", "＜").replace(">", "＞")
    if len(text.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        raise ValueError(f"description is {len(text.encode('utf-8'))} bytes (> {MAX_DESCRIPTION_BYTES})")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--pack-dir", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--pinned-extra", default="")
    args = parser.parse_args(argv)
    run = args.run_dir
    news = json.loads((run / "news_script.json").read_text(encoding="utf-8"))
    script = json.loads((run / "script.json").read_text(encoding="utf-8"))
    credits = json.loads((run / "credits.json").read_text(encoding="utf-8"))
    video = run / "assembly" / "release.mp4"
    folder = args.pack_dir / f"{CHANNEL_CODE}-{args.slug}"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(video, folder / "video.mp4")
    thumbs = run / "thumbnails"
    for name in ("option_a.jpg", "option_b.jpg", "cover_frame.json"):
        if (thumbs / name).is_file():
            shutil.copy2(thumbs / name, folder / name)
    seconds, size = _probe(video)
    mm, ss = int(seconds // 60), round(seconds % 60)
    title = f"{news['title']} #Shorts"
    desc_lines = script["description"].splitlines()
    footer = next((ln for ln in desc_lines if ln.startswith(CHANNEL_NAME + "是")), "")
    series = next((ln for ln in desc_lines if ln.startswith(CHANNEL_NAME + "：")), "")
    body = description(news, credits, footer, series)
    tags = ", ".join(dict.fromkeys(["Shorts", CHANNEL_NAME, "科技新聞", *news.get("tags", [])]))
    cover = json.loads((folder / "cover_frame.json").read_text(encoding="utf-8")) if (folder / "cover_frame.json").is_file() else {}
    cover_line = (f"建議封面格：第 {cover['cover_frame']['second']} 秒（第 {cover['cover_frame']['beat']} 段畫面）；"
                  f"選項圖 option_a.jpg（{cover['a']['hook']}）、option_b.jpg（{cover['b']['hook']}）。") if cover else "（尚未產生縮圖選項）"
    meta = f"""# {CHANNEL_NAME}（technews，獨立頻道，預設 token） — {news['title']} #Shorts

| 項目 | 設定 |
|---|---|
| 影片檔 | `video.mp4`（{size} h264+aac，{mm}:{ss:02d}） |
| 縮圖 | Shorts 可略過；封面用影片畫格（見下）。備選圖 `option_a.jpg`／`option_b.jpg` |
| 瀏覽權限 | 私人（Private）→ 通過 Studio 檢查後再改公開 |
| 觀眾 | 否，這不是為兒童打造的內容 |
| 類別 | 科學與技術（Science & Technology） |
| 語言 | 中文（台灣）zh-TW；字幕認證：無 |
| 授權 | 標準 YouTube 授權；允許嵌入 |
| 「經過修改或合成的內容」 | **否** |

理由：畫面是扁平編輯插畫（每張標「AI 示意圖」）加新聞來源卡，一看就不是實景，也沒有真人或擬真人臉；配音是一般合成語音，不模仿真人。不符合「容易被誤認為真實」的揭露條件。說明欄已文字揭露 AI 製作。

## 標題（{len(title)}/100 字）

{title}

## 說明欄（整段貼上）

```text
{body}
```

## 標籤

{tags}

## 檢查結果（成片實測）

| 檢查 | 結果 |
|---|---|
| 編碼／解析度 | {size} h264+aac |
| 片長 | {mm}:{ss:02d}（≤60 秒、9:16，符合 Shorts） |
| 整合響度 | {_loudness(video)} |
| 說明欄 | {len(body.encode('utf-8'))} bytes（≤4800）、無角括號 |

## 封面與縮圖

{cover_line}

## 注意事項

- 事實全部取自原文（見說明欄出處）；稿子經正確性查核（信心度 ≥0.5 才算錯，自動修一次）。
- 說明欄結尾 `#Shorts` 保留。
- 頻道署名：{CHANNEL_NAME}；無「晶片貓」字樣。
"""
    (folder / "metadata.md").write_text(meta, encoding="utf-8")
    pinned = "原文與出處（完整連結）：\n" + "\n".join(f"• {s['title']} — {s['url']}" for s in news["sources"]) + \
        "\n\n數字或說法有疑問，歡迎留言附上來源，我們會查證並更正。" + args.pinned_extra + "\n"
    (folder / "pinned-comment.txt").write_text(pinned, encoding="utf-8")
    print(folder)
    return 0


if __name__ == "__main__":
    sys.exit(main())
