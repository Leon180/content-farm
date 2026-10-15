# 範例：CoWoS 先進封裝（v2 研究 → 文章 → deck，正式長度）

流程：`/article` → `/deck-outline` → `/deck` → 管線。資料截至 2026-10-15。

| 檔案 | 內容 |
|---|---|
| `article.md` | 研究文章（本文 3,138 字），每個數字與軼事都附 `[src:id]` |
| `sources.json` | 22 筆來源，格式可直接貼進 deck.json `sources`（`note` 內含 publisher / published / accessed / type） |
| `deck_outline.json` | 24 張大綱，每張有 `article_refs`（文章錨點）、`source_ids`、`mascot_pose`、`media_kind` |
| `deck.json` | 24 張正式稿，`draft_data: false`，`--strict` lint 0 警告；含 `mascot.pose` 與 `media` 建議 |
| `script.json` | `deck_to_script` 產出，已被 voice（macos_say）回寫實測時長：503.1 s |
| `slides/contact_sheet.png` | 24 張總覽，無溢出 |
| `draft_frame_s13.png` | `draft.mp4` 第 245 秒截圖：第 13 張與字幕對齊、字幕在安全區 |

重跑（在 worktree 根目錄；`<run>` 放 deck.json 的副本）：

```bash
python scripts/check_article.py --run-dir docs/examples/explainer-cowos
python scripts/deck_to_script.py --run-dir <run> --strict
python scripts/render_slides.py --run-dir <run>
CF_TTS_PROVIDER=macos_say python scripts/run_stage.py --stage voice --run-dir <run>
python scripts/slides_to_visual.py --run-dir <run>
python scripts/run_stage.py --stage assembly_timeline --run-dir <run>
```

`media` 目前只有 schema 驗證，畫面軌道還不會用它（等畫面 worker）。macos_say 的聲音只供測試，不可發布。
