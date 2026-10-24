# REPORT — 深海大王烏賊「巨物恐懼」Wan 版（worktree-cf-deepsea-wan）

等級：🟢 本機實測 ／ 🟡 我的判讀 ／ 🔴 未做。未 push、未付費、未開瀏覽器、未上傳。雲端費用 $0。

## TL;DR
- **狀態：暫停。** Leon（經 orchestrator）要求「先做一個、效果好再續」，再改為「先完成其他影片」：只烤了 s01（3 段接長），批次已停、heavy 佇列已釋放（`pgrep mlx_video` 無程序）。
- 🟢 工具完成並 commit：接長（前段最後一格→下段起始圖，可續跑）、T2V 起點、每支片自訂 Wan 上限（`deck.wan_budget`）、Wan 放大＋銳化。單元測試全套 1973 passed／1 skipped（排除既有失敗的 test_multi_provider）。
- 🟢 s01 樣片：3 段 205 格（8.5 s），牆鐘 881.7＋962.1＋1083.2＝2927 s。檔案在 `artifacts/deepsea-mega/sample/`（未 commit 的 mp4＋commit 的 README）。
- 🟡 品質自評：前 3 秒乾淨；第 2、3 段出現水紋／雜訊漩渦（誤差累積），巨大形體只是靜止弧線、沒有「浮現再掠過」。建議接長最多 2 段（≈5.7 s）或換更保守的 prompt。
- 🔴 未做：其餘 7 段 Wan（s04 T2V、s08 接長、s10、s14、s17、s22 T2V、s27 接長）已寫進 deck 且起始圖已生，但未烤；重組裝、540p 兩段、8 格對照、QC 前後對照都還沒做。

## 做了什麼
1. 分支自 `worktree-cf-stock-footage` e255db9 fast-forward；`output/deepsea-1-mega` 複製自 `deepsea-1-stock`（沿用文章／配音／NOAA 片段）。
2. 程式（commit 229ab12）：
   - `explainer/wan_chain.py`：每段獨立快取（`<slide>.wan.seg<k>.*`，key＝起始格 sha＋prompt＋參數），中斷後從停下的那段續；用 ffmpeg 取精確最後一格（`select=eq(n,68)`）；接合時丟掉後續段重複的第一格（3 段＝69+68+68＝205 格）。
   - deck 新欄位：`media.wan_chain`（≤2 個額外 prompt）、`media.wan_t2v`、`deck.wan_budget`（≤10；bake、lint、QC、授權檢查都讀它，預設仍 3）。
   - 放大：`ffmpeg_ops.upscale_filter`，Wan 片段 lanczos＋`unsharp=5:5:0.7:5:5:0.0`（只動亮度）。授權：ffmpeg 內建濾鏡，無模型。🔴 未試 Real-ESRGAN 等超解析模型（沒做授權調查）。
   - `tests/unit/test_wan_chain.py` 13 項（含真 ffmpeg 接合與中斷續跑）。
3. deck（`output/deepsea-1-mega/deck.json`，gitignore）：8 張 `motion: wan`（`wan_budget: 8`），prompt 都是巨物恐懼構圖（尺度對比、黑暗、只露局部、無臉）；舊的 8 張起始圖移到 `assets/ai_images_old/`，新圖 z-image-turbo 每張約 50 s。
   - 🟡 s04、s22 的起始圖畫出了烏賊的眼睛，但它們是 T2V 段的退路圖；若 T2V 失敗退回視差就會露臉，要重生或改 prompt。

## 每段 Wan 規劃（時間點待重組裝後填；slide id 為準）
| slide | 型態 | 狀態 |
|---|---|---|
| s01 | I2V 接長 3 段 | 🟢 已烤 |
| s04 | T2V 遠景剪影（大王烏賊游動）1 段 | 未烤 |
| s08 | I2V 接長 3 段（觸腕從光圈邊緣伸入纏鉤再退回） | 未烤 |
| s10 | I2V 1 段（抹香鯨巨大陰影掠過） | 未烤 |
| s14 | I2V 1 段（相機被拖起，下方巨影） | 未烤 |
| s17 | I2V 1 段（藍光誘餌＋後方巨大輪廓） | 未烤 |
| s22 | T2V 遠景發光剪影 1 段 | 未烤 |
| s27 | I2V 接長 3 段（浮出水面、巨影遠去） | 未烤 |
prompt 全文在 deck.json 與 `assets/ai_motion/*.json`；s01 見 `artifacts/deepsea-mega/sample/README.md`。

## 續烤
```
env PYTHONPATH=<worktree>/src CF_MLX_VIDEO_HOME=/Users/lileon/.local/share/mlx-video \
  /Users/lileon/project/content-farm/.venv/bin/python scripts/ai_motion.py bake --run-dir output/deepsea-1-mega
```
剩 13 段 × 約 15–18 分 ≈ 3.5 小時（s01 已快取，會略過）；一次一段、峰值 ≈ 26 GB（沿用試做量測，本次 log 未印 peak）。烤完再：`produce.py run --run-dir output/deepsea-1-mega --force media --force assembly --force mix --force qc --budget-usd 20`，`scripts/encode_540p_parts.py` 轉 540p，抽 8 格，QC 對照（基準：dead zones 8、still_frames>8s 3 處）。

## 費用與牆鐘
- 雲端 $0。本機：起始圖 8 張 ≈ 7 分；Wan s01 48.8 分（排隊 0 s，開跑時機器空閒）；測試 2 分。

## 副作用
- 沒清掉：`output/deepsea-1-mega`（含 `assets/ai_images_old/`、舊的 s08/s27 stale Wan 快取）、`artifacts/deepsea-mega/sample/*.mp4`（rm 不在白名單）。
- repo 內有被追蹤的 `__pycache__/*.pyc`，跑測試會改動；我沒 commit 它們。

## 進度紀錄
- 2026-10-24：工具＋s01 完成並暫停；等 orchestrator 指示續烤。
