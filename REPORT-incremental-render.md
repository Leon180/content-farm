# REPORT — 分段增量渲染＋角色疊加加速

## TL;DR
（進行中，收工前改寫）

## 進度紀錄（append）
- 2026-10-18 分支 `feat/incremental-render` 從 `feat/cowos-v3` 2030c1e 開（worktree `cf-incremental-render`）。
- 讀過：`production/steps.py`（deck → voice → media → assembly → mascot → mix）、`media_run.py`／`media.py`（每張 12–29 s，
  24 張合計約 425 s＋轉場／縮圖約 80 s）、`mascot/*`（向量 rig 用 Playwright 逐格截圖；15k 格全部 unique，2 workers 約 490–630 s，
  overlay 42–73 s）、`voice/generator.py`（已有逐場景 identity 快取，單位是「整張投影片的旁白」，不是句子）。
- 角色動作目前依賴全片時間（眨眼／頭部事件／物理彈簧都以整支 duration 與全域 t 計算）→ 要逐場景快取，必須先改成場景本地時間。
- 句子 id（`explainer/sentence_ids.py`，`deck_to_script.py` 預設蓋章）＋ledger（`sentence_ledger.json`）＋舊 deck 遷移，commit 3f…（見 log）。
- media 逐場景快取（`explainer/media_cache.py`、`scene_cache.py`）：identity＝投影片內容＋頁碼／總頁數＋deck 標頭＋品牌＋槽長＋舞台提示＋外部檔雜湊＋渲染碼雜湊；
  轉場成品依（本張, 下一張, 轉場設定）快取。commit 8f34143。
- 角色 profile（CoWoS v3 實際 run 的第 3000–3300 格，🟢 本機可重跑：`$CLAUDE_JOB_DIR/tmp/profile_mascot*.py`）：
  | 方式 | ms/格（單 worker） |
  |---|---|
  | 現行：Playwright `page.screenshot`，軟體光柵（SwiftShader） | 143.5 |
  | 同上，CDP `optimizeForSpeed` | 105.4 |
  | 拿掉貼紙濾鏡（feMorphology＋blur）只為定位成本 | 39.8 |
  | GPU 光柵（ANGLE Metal） | 43.1 |
  | GPU＋2×2 rig iframe 一次截圖（含解碼、裁切） | 13.6 |
  | GPU＋3×3／4×3 | 11.7／10.8 |
  畫質：疊在灰底後比較，2×2 拼貼 vs 單張截圖最大差 16/255、>8 的像素 0.0000%；CPU vs GPU 光柵 >8 的像素 1.29%（邊緣反鋸齒），目視無差（`cpu_vs_gpu.png`）。
  ProRes 編碼 5 ms/格；ffmpeg 解 ProRes 7 s、解碼＋overlay 不編碼 23.5 s。
- 角色疊加改成：場景本地時間（邊緣 0.4 s 收回姿勢靜止值，鄰場景在同一參數接上）＋逐場景 alpha 快取＋GPU 2×2 拼貼截圖＋3 lanes。
  CoWoS v3 整支（15,292 格）：render 1186.1 s → 113.4 s；overlay（veryfast crf18）52.7 s；**全冷 169.4 s**（目標 ≤180 s ✓）；全熱 56.6 s。
- overlay 編碼：medium 79.7 s／veryfast 52.2 s（SSIM 0.9987 vs medium，檔案較小）／faster 75.7 s／VideoToolbox 53.3 s（162 MB）→ 用 veryfast。
- 組裝：逐段 normalize 快取（`assembly/norm_cache`），字幕燒入 medium crf23 → veryfast crf18（SSIM 0.9986 vs 舊 draft）。
  CoWoS v3：冷 150.6 s（舊碼 134.5 s）→ 熱 46.9 s。
- 配音窗口實驗（`scripts/voice_window_experiment.py`，VoxCPM2 本機，每個變體 3 個 seed，2 個場景；結果 `output/cowos-inc/experiments/voice_window_{k2,k1}/results.json`）。
  指標＝接縫兩側各 0.5 s 有聲段的音高（半音）／響度（dB）跳動，**減去原 take 同一句界的自然跳動**（自然句界本身中位就有 5.5 半音，問句→答句會重設音高）；語速＝新段字/有聲秒 ÷ 原 take。
  | 變體 | k2 音高Δ 中位/最大 | k2 響度Δ | k1 音高Δ | k1 響度Δ | 語速偏差 | 生成秒 |
  |---|---|---|---|---|---|---|
  | ±0 | 2.83/4.82 | 1.14/2.25 | 1.56/2.13 | 1.23/5.30 | 5–17% | 10–21 |
  | ±0＋前句音訊當續寫提示 | 1.21/4.74 | 0.98/2.55 | 1.27/1.80 | 1.00/1.62 | **6–37%（偏快）** | 6–15 |
  | ±1 | 3.94/6.85 | 1.74/2.35 | 3.15/6.47 | 1.20/1.46 | 0–5% | 15–30 |
  | **±2** | **1.41/4.26** | **0.75/4.76** | **0.26/0.52** | **0.35/1.68** | 1–10% | 23–34 |
  | 整場景重配 | — | — | — | — | 0–5% | 57–122 |
  → 預設 `tts_splice_radius=2`（🟡：2 場景×3 seed，音高估計用自相關、會有八度誤判；結論是「±2 兩場景都最穩、±1 兩場景都最差」）。
  VoxCPM2 能帶前後文：worker 新增 `prompt_audio/prompt_text`（續寫提示）實測可用，但語速明顯變快，不採用。
