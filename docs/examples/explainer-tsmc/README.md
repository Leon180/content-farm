# 範例：台積電到底賺什麼錢（簡報式知識影片 MVP）

> ⚠️ **數字與來源全是示意、待查證**（`deck.json` 的 `draft_data: true`，每張投影片右上角都有紅色「示意數字・待查證」章）。這份 deck 只用來看版面，不可發布。

手寫的 6 張 deck，跑過 `deck → script.json → render_slides → 總覽圖`，**沒有跑 voice**（沒有呼叫任何付費 API）。

| 檔案 | 內容 |
|---|---|
| `deck.json` | 手寫原稿（三個 section = 三個 YouTube 章節；六種版型各一張；一個八卦段、一個冷笑話段） |
| `script.json` | `scripts/deck_to_script.py` 產出；`duration_seconds` 是字數估算，voice 跑完會被實測值覆寫 |
| `slides/slide_NNN.html` | 每張投影片的獨立 HTML（CSS 內嵌，可手改後重截） |
| `slides/slide_NNN.png` | 1920×1080 截圖 |
| `slides/contact_sheet.png` | 總覽圖（人工閘門 3 看這張） |
| `contact_sheet_safe_zone.png` | 同一份 deck 加 `--show-safe-zone`：紅色斜紋是燒字幕的底部 200 px，任何內容都不得進入 |

重跑（在 repo 根目錄）：

```bash
python scripts/deck_to_script.py --run-dir docs/examples/explainer-tsmc
python scripts/render_slides.py  --run-dir docs/examples/explainer-tsmc
```

`deck_to_script.py` 會印出三條 lint 警告（張數不足 15、片長不足 5 分鐘、`draft_data`），這是範例本來就短、數字本來就假的預期結果；加 `--strict` 會拒絕產出。

吉祥物：`s01`、`s02`、`s04`、`s06` 有 `mascot.pose`，但 `assets/mascot/` 沒有 PNG，所以角落留空——這是設計（素材之後由使用者提供，放 `<run_dir>/assets/mascot/<pose>.png`）。
