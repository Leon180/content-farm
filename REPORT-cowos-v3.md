# REPORT — CoWoS v3（eval 修正＋留存節拍＋BGM／音效＋上線前 eval 工具）

## TL;DR
（進行中，收工前改寫）

## 進度紀錄（append）
- 2026-10-17 分支 `feat/cowos-v3` 從 `feat/channel-voices` a5a4e41 開，merge `design/channel-hosts` a6885eb。
  衝突：`channels/{yokai,cel,offwork}.yaml`（mascot 取 hosts、voice 取 voices；依 Leon 決策 offwork/cel 用 `-3d` 包、yokai 用平面包）、
  `CLAIMS.jsonl`（換成本分支自己的）。`test_production_channels.py` 的 cel 包斷言同步改成 `paint-bottle-3d`。
- 合併後 pytest：1 失敗 `test_multi_provider.py::test_returns_first_provider_results`——該檔與 `visual/multi_provider.py`
  最後修改在 dc3f094（遠早於本分支），屬既有失敗，非本分支造成。
- Leon 追加（任務中）：「影片封面有點太弱，建議上網研究別人怎麼做」→ 派研究子代理，產出 `docs/research/thumbnails-2026-10.md`。
  結果：Test & Compare 機制 🟢（最多 3 款、以觀看時間占比判勝、最長 2 週、僅桌機、Shorts 不適用）；
  **別台頻道縮圖樣式未取得**（搜尋只拿到泛用頁，表格標「未取得」，需人工截圖補）。新 3 款規格：共用淺底 #F0F4F8／深藍 #0F1B2D／橘 #D9480F，
  左上固定「台積電 · CoWoS」標籤；A「晶片不一定翻倍？」＋驚訝貓、B「卡在封裝？」＋自繪剖面圖、C「一片晶圓 70→5」。
- 已寫：`src/content_farm/retention/{timing,beats}.py`（句子時間軸、鉤子分類與節拍 lint）。下一步：畫面／聲音探測、死區、混音。
