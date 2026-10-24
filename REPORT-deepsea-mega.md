# REPORT — 深海大王烏賊「巨物恐懼」Wan 版（worktree-cf-deepsea-wan）

等級：🟢 本機實測 ／ 🟡 我的判讀 ／ 🔴 未做。未 push、未付費、未開瀏覽器、未上傳。雲端費用 $0（gate 沿用核可、評審已關閉，沒跑 `claude -p`）。

## TL;DR
- 🟢 依 Leon「四個左右就好」改為 **4 個 Wan 鏡頭**：s01（3 段接長 8.5 s）＋ s08、s10、s27（各 2 段接長 5.7 s）。成片已重組裝、轉 540p 兩段、抽 8 格對照。
- 🟢 工具 commit：接長（可續跑）、T2V 起點、`deck.wan_budget`、Wan 放大＋銳化；全套單元測試 1973 passed／1 skipped。
- 🟡 品質：s10（鯨魚巨影）、s27（潛水器上浮、下方巨影遠去）乾淨；s01 前 3 秒佳、後段有雜訊累積；s08 第一版第二段崩壞（綠色色塊、畫面撕裂），改保守 prompt 重烤後乾淨。接長 2 段明顯比 3 段穩。
- 🟢 QC：仍 1 error（dead_zones），9 段 >10 s（前一版 8 段），多出的是 **0–19 s**——開場 s01 的 Wan 畫面暗且慢，被偵測器當成靜止。still_frames 超 8 s 仍 3 處（最長 27.25 s）。見 §5。
- 🔴 沒做：Real-ESRGAN 等超解析模型（只用 ffmpeg lanczos＋unsharp）；沒有人完整看過成片，只抽 8 格＋每個 Wan 片 4 格；T2V（`wan_t2v`）只有單元測試，沒實烤。

## 1. 四個 Wan 鏡頭（時間點為成片近似值，扣除 0.25 s 轉場累計；成片約 591.5 s）
| slide | 成片時間 | 型態 | 起始圖／prompt |
|---|---|---|---|
| s01 | 0–29 s | 3 段，205 格 8.5 s | 見下 |
| s08 | 129–150 s | 2 段，137 格 5.7 s | 見下 |
| s10 | 175–190 s | 2 段，137 格 5.7 s | 見下 |
| s27 | 570–592 s | 2 段，137 格 5.7 s | 見下 |
共同：832×480、20 步、guide 5.0、seed 42、negative `face distortion, morphing`；起始圖 z-image-turbo 1280×720（頻道深海插畫風前綴），後段起始圖＝前段最後一格。其餘 22 張維持原圖＋視差。

**s01**（lower）圖：A tiny camera rig with a small strobe light hangs on a cable in the upper left of a vast pitch-black abyss, a faint teal glow around it, marine snow drifting, far below at the edge of the glow a colossal dark curved shape is barely visible, immense scale, mostly empty black water, no eyes, no creature close-up。
 動：(1) slow camera descent, marine snow drifting upward past the lens, the small strobe pulses softly, the huge dark curved shape far below stays almost still, pitch black water (2) the camera keeps sinking slowly, the enormous dark shape below drifts sideways into the faint edge of the glow showing only a vast curved wall of dark skin, marine snow, very slow and heavy, no close-up (3) the giant shape glides slowly past beneath the light and fades back into the black, the tiny strobe shrinks in the corner, marine snow drifts upward, calm awe

**s08**（lower）圖：A baited line with a hook hanging in the small pool of a strobe light in black water, at the far edge of the light a thick pale rope-like tentacle tip reaches in from the dark, the rest of an enormous body hidden in total darkness, no eyes visible。
 動（重烤版）：(1) the strobe flashes softly, a few particles of marine snow drift slowly, the line hangs still, the thick pale tentacle at the edge of the light stays almost motionless, static camera, calm dark water (2) the thick pale tentacle drifts very slowly a little closer to the hook and then holds still, the strobe flashes softly, marine snow drifts, static camera, calm dark water
 第一版（觸腕伸入、纏鉤、拉緊再退）第二段崩壞，檔留在 `assets/ai_motion/s08.wan.try1-bad.mp4`，耗 1597 s。

**s10**（lower）圖：A tiny submersible lamp glows in the upper corner of a vast black ocean, far below a gigantic dark whale-shaped shadow glides silently across a faint blue haze, only its outline visible, immense scale contrast, no face detail。
 動：(1) a gigantic dark whale-shaped shadow glides slowly across the faint blue haze below, slow heavy movement, the tiny lamp stays steady in the corner, marine snow drifts, the camera slowly sinks, no close-up (2) the whale-shaped shadow keeps gliding slowly across the haze and fades into the black below, the tiny lamp stays steady in the corner, marine snow drifts upward, calm awe

**s27**（panel_left）圖：A tiny camera pod with a small lamp on the right rises through vast black water, far below in the dark an immense pale shape slowly turns away, faint surface light high above, teal marine snow, mostly empty dark water, no eyes。
 動：(1) the camera pod rises slowly, marine snow streams downward, the small lamp glows steady, the immense dark shape far below slowly drifts away (2) the pod keeps rising, the water above turns slightly lighter teal, the vast shape below fades into the dark, particles stream downward

🟡 巨物恐懼的效果：s10、s27 靠「小光點對巨大輪廓」成立；s08 的巨大本體只是一塊黑影，觸腕只在光圈邊緣微動；s01 的巨影是一道靜止弧線，沒有「浮現再掠過」。Wan 對「緩慢浮現的大型形體」不太聽話，主要效果來自構圖與黑暗。
🟡 畫面是座鯨（s10、s27 的形體像座頭鯨）而非烏賊——s27 的「巨大淡色形體」被畫成鯨魚輪廓；旁白沒有提到，但觀眾可能以為那是大王烏賊。若要避免，s27 換 prompt 重烤。

## 2. 接長
`explainer/wan_chain.py`：每段獨立快取（`<slide>.wan.seg<k>.{mp4,json}`，key＝起始格 sha＋prompt＋參數），中斷後續跑；用精確的最後一格（`select=eq(n,68)`）當下一段起始圖；接合時丟掉後續段重複的第一格（2 段 137 格、3 段 205 格）；中間用 CRF 12 H.264。deck 欄位 `media.wan_chain`（≤2）、`media.wan_t2v`、`deck.wan_budget`。
🟢 誤差累積是真的：s01 第 3 段、s08 第一版第 2 段都出現水紋／雜訊；建議上限 2 段，prompt 越保守越穩（s08 重烤即證）。
成片在 slot 內仍是 ping-pong 循環（正播＋倒播），所以長 slot（s01 29 s）會循環數次；接長的「浮現」在倒播時會「退回」。🟡

## 3. 放大
Wan 832×480 → 1920×1080：`ffmpeg lanczos` ＋ `unsharp=5:5:0.7:5:5:0.0`（只動亮度），在 `motion_loop` 內一次完成；授權＝ffmpeg 內建濾鏡，無模型。🔴 未試 Apache／MIT 超解析模型（沒查授權也沒下載）。樣片 1080p 版 `artifacts/deepsea-mega/sample/s01-wan-1080p.mp4`。

## 4. 烤與組裝時間（牆鐘）
| 項目 | 秒 |
|---|---|
| s01 3 段 | 881.7＋962.1＋1083.2＝2927.0 |
| s08 第一版（廢）2 段 | 1597.1 |
| s08 重烤 2 段 | 1484.8（748.3＋736.5） |
| s10 2 段 | 1544.3 |
| s27 2 段 | 1518.6 |
| Wan 合計（含廢的一次） | 9071.8（≈151 分；有效 7474.7≈125 分） |
| 起始圖 8 張（其中 4 張後來退回原圖） | ≈410（約 51 s／張） |
| media／assembly／mix／qc | 378.0／73.4／27.1／約 40 |
- 排隊：s01 開跑時機器空閒（0 s）；因 Leon 指示「先完成其他影片」，批次暫停並等 heavy 佇列清空（fable 系列影片）才續烤，約 10 小時牆鐘（含 orchestrator 指示往返）。s08 第一版 gate 等 30 s；s10 開跑前記錄到 swap 91–93% 與他人持鎖等待，最終 gate 等待記為 0 s（紀錄值，🟡）。
- 記憶體：log 沒印 peak（`reported_peak_gb: null`）；沿用試做的 footprint ≈ 26 GB（REPORT-ai-video-trial §3）。生成時整機 swap 91–93%（他人同時在跑）。🟡
- 單元測試 1973 passed／1 skipped，約 2 分。
- 費用：雲端 $0。

## 5. QC 前後（`qc/qc_report.json`）
| | 前（deepsea-1-stock） | 後（本版） |
|---|---|---|
| dead_zones（>10 s） | 8 段，error | **9 段**，error：0–19、67–83、116–128、152–171、177–192、249–280 s … |
| still_frames >8 s | 3 處（最長 27.25 s） | 3 處（最長 27.25 s） |
| speech_check／beat_gap | warn／warn | warn／warn（沿用舊配音，未變） |
🟡 新增的 0–19 s 是 s01 的 Wan：幾乎全黑、動作慢，偵測器判為靜止。這是「巨物恐懼」風格與 dead-zone 規則的衝突，不是退化——但若要過 QC，開場 19 s 需要更多可見變化。
其餘 dead zone 為 AI 圖視差 >14 s 的長段（與前一版相同，本任務沒處理）。

## 6. 產物
- 540p 兩段：`artifacts/deepsea-mega/deepsea-mega-part1.mp4`（13.02 MB）、`-part2.mp4`（12.93 MB）——part1 以十進位 MB 計略超 13（13,022,620 B），以 MiB 計 12.4。
- 8 格對照：`artifacts/deepsea-mega/compare-8frames.png`（上排前一版 stock、下排本版；時間 14／140／182／580 s）。
- 樣片：`artifacts/deepsea-mega/sample/`（s01 原檔、1080p、起始圖、README）。
- 這些 mp4／png 未 commit（public repo；只 commit 報告與 README）。

## 7. 沒清掉／副作用
- `output/deepsea-1-mega`（含 `assets/ai_images_old/`、`s08.wan.try1-bad.mp4`、s04／s14／s17／s22 已退回原圖與視差）；`artifacts/` 的 mp4／png（rm 不在白名單，交 orchestrator）。
- 被追蹤的 `__pycache__/*.pyc` 跑測試會被改動，未 commit。

## 進度紀錄
- 2026-10-24：全部完成。分支 `worktree-cf-deepsea-wan`。
