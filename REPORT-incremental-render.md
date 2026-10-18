# REPORT — 分段增量渲染＋角色疊加加速

## TL;DR
- CoWoS v3 實測（`produce.py` 正式流程，從存檔到 release.mp4）：**(a) 改一個事實的兩句旁白 180.6 s、(b) 改一張投影片畫面 143.7 s**，目標 ≤5 分 ✓；
  (c) 改一個全片出現 3 次以上的說法（含片名）548.4 s——片名印在每一幀的 meta 列，所以 24 張全部重畫，這是正確的失效。舊碼整支重渲約 1946 s（32 分）。
- 角色疊加：GPU 光柵＋2×2 拼貼截圖＋逐場景快取，整支冷渲 **1186 s → 113 s render、全步驟 169 s**（≤3 分 ✓）；快取全中時 38–57 s（只剩 overlay 編碼）。
- 配音只重配「被改句 ±2 句、限同場景」再接回原 take（實驗 ±0/±1/±2/續寫提示/整場景，±2 接縫最穩；🟡 2 場景×3 seed）。接縫無爆音、ASR CER 0.025／0.059。
- 接縫驗收（增量成品 vs 同腳本整支一次渲染）：格數 15,331＝15,331、無跳格／黑幀／重複幀，PSNR 最低 63.8 dB（中位完全相同），字幕誤差 0、響度 −14.0／−14.0 LUFS ✓。
- 改好的上片版在 `output/cowos-inc/assembly/release.mp4`（5:03 每月／封裝數＋片名、s01、k2、縮圖 A 連動），gate_final 待 Leon 審。pytest 1336 過，唯一失敗 `test_multi_provider` 是 cowos-v3 起就有的既有失敗。

## 設計
**句子 id**（`explainer/sentence_ids.py`）：每句一個 `s12.3` 形式的 id，存在 `slide.sentence_ids`，`deck_to_script.py` 預設蓋章（`--no-ids` 關）。
`sentence_ledger.json` 記住發出過的每個 id 與它最後的文字：同文同張沿用 → 同文別張（搬動）沿用 → 曾刪掉又加回的句子取回舊 id → 其餘發新號（號碼永不重用）。
舊 deck 沒有 ledger 時，`s12` 第 k 句 = `s12.k`（遷移）；deck 裡已有 id 但 ledger 遺失時，從 deck 自己的 id 重建。

**分段單位＝場景（投影片）**：
| 步驟 | 快取位置 | identity（全部雜湊；與在片中的位置無關） |
|---|---|---|
| voice | `audio/voice_identity.json`（既有，新增 `sentences`） | 供應商／聲音／模型＋TTS 文字；只差幾句時改走句子窗口 |
| media | `media/cache/<key>/` | 投影片內容（不含 sentence_ids/notes）、章節名、頁碼／總頁數、deck 片名等每幀都印的欄位、品牌、**該場景音檔雜湊**（代表槽長）、舞台提示（句子時間）、外部檔雜湊、渲染碼雜湊 |
| 轉場 | 同上 | （本張 key, 下一張 key, 轉場設定）——轉場會吃下一張的第一格 |
| assembly normalize | `assembly/norm_cache/` | 來源片段內容雜湊＋目標長度＋尺寸；concat／混音軌／字幕燒入仍整支 |
| mascot | `assembly/mascot_cache/<key>/alpha.mov` | 姿勢、前一場景姿勢、對話泡、場景音檔雜湊、**場景音檔實測長度**、種子（由 slide id 導出）、rig 碼雜湊、截圖設定 |
| mix | 無（整支重接，約 24–45 s） | |
每個快取保留最近 3 次 run 用過的項目（改回去＝免費），其餘自動刪。改到渲染碼本身時該步驟全部重畫（安全預設；不影響像素的協調模組已排除）。

**位置不得洩漏進 identity**（實測踩到三次才收斂，見進度紀錄）：角色動作改成場景本地時間——idle（眨眼、頭部、呼吸）與彈簧物理在場景頭尾 0.4 s 淡入／收回姿勢靜止值，
相鄰場景在同一組參數接上；場景起點對齊格線（≤半格，17 ms），每場景依自身音長多畫 1 格、接起來時裁到格線槽長；media 的句子時間在音檔與旁白未變時沿用上次值
（整支 SRT 的毫秒捨入會讓後面場景的 0.01 s 位移翻動）。

**修改範圍連動**（`explainer/fix_scope.py`、`scripts/fix_scope.py`）：比對 deck 核可快照（gate_deck 核可時自動存 `review/deck.approved.json`）與現在的 deck：
改寫的句子（id）、改掉的數字／英文詞／被動到的子句、加上 `--term` 指定的說法，逐詞索引所有仍是舊說法的地方（旁白句 id、標題、內文、對話泡、章節、片名、
縮圖 json、上傳標題／說明）；配音窗口＝被改句 ±radius、不跨場景；重畫場景 vs 只位移場景；片名等每幀都印的欄位一改，全部重畫並註明。有舊說法殘留就 exit 2。

**配音窗口**（`voice/window.py`、`voice/splice.py`、`VoiceGenerator._patch_take`）：比對 take 當初的逐句 TTS 文字與現在的句子，變動塊外擴 radius（預設 2）句、
重疊合併；窗口文字單獨合成（照樣過 ASR 念錯檢查與重試），在原 take 的句間停頓中點切開、保留原停頓長度、12 ms 淡入淡出接回；之後整場景 ASR 讀回一次寫入
speech_check。窗口超過該場景 75% 的句子、找不到足夠停頓、或聲音／模型變了，就退回整場景重配。`CF_TTS_SPLICE_RADIUS=-1` 可關掉。

**角色疊加加速**：見下方 profile。Chromium 軟體光柵下貼紙濾鏡（feMorphology＋blur）佔 70%；改 GPU 光柵（ANGLE Metal）＋一頁放 2×2 個 rig iframe、一次截圖、
CDP `optimizeForSpeed`，RGBA 直接餵 ffmpeg ProRes；格子永遠落在 `本地格號 % 4`，所以同一場景不管怎麼分工都是同一組像素。overlay 與字幕燒入改 x264 veryfast crf18。

## 實測時間（CoWoS v3，8:31，24 場景）
| 情境 | voice | media | assembly | mascot | mix | 合計（wall） |
|---|---|---|---|---|---|---|
| 舊碼整支重渲（cowos-v3 最後一次） | — | 504.9 | 132.1 | 1264.3 | 44.5 | ≈1946 s |
| 新碼整支冷渲（cowos-inc 暖機；assembly 的 normalize 是熱的） | 77.7 | 499.0 | 52.4 | 162.4 | 44.7 | 867.4 s |
| 新碼整支冷渲（cowos-full，機器較閒） | — | 305.1 | 64.6 | 106.7 | 23.7 | ≈500 s |
| **(a)** k2 兩句旁白 | 51.7 | 20.2 | 28.1 | 38.2 | 24.1 | **180.6 s** ✓ |
| **(b)** k2 畫面標題 | 10.9 | 20.8 | 33.0 | 36.9 | 24.0 | **143.7 s** ✓ |
| **(c)** 說法連動（含片名） | 80.6 | 314.1 | 61.3 | 48.6 | 24.0 | **548.4 s** |
(c) 的 mascot 重畫 5 場景，其中 3 個是當時仍存在的毫秒捨入翻動，之後改成以音檔實測長度為 identity（1ba27b5，單元測試涵蓋）；**修正後沒有重測 (c)** 🟡。
(a) 曾量到 468.5 s 與 425.7 s，原因與修正在進度紀錄。gate 由腳本立即核可（各 <0.5 s），不含人審時間。

## 接縫比對（`scripts/seam_check.py`，結果 `output/cowos-inc/experiments/seam_check_release.json`）
A＝(a)→(b)→(c) 增量鏈產出的 release.mp4；B＝同一份 deck、同一份音檔與字幕，清空所有快取、用同一版程式（d2e432c）整支一次渲染（`output/cowos-full`）。
| 項目 | 結果 | 門檻 |
|---|---|---|
| 格數／時間戳 | 15,331＝15,331，A 不規則步進 0 | 相同、無跳格 ✓ |
| 黑幀（blackdetect） | 只在 A 出現的 0 段 | 0 ✓ |
| 重複幀（A 靜止而 B 在動） | 0 | 0 ✓ |
| 逐格 PSNR A vs B | 最低 63.8 dB、中位 99（完全相同）、23 個場景界 ±3 格最低 64.7、<35 dB 的格 0 | — |
| 爆音（樣本跳變 >8× 局部平均） | A 417／B 417、只在 A 的 0 | 0 ✓ |
| 響度 | −14.0／−14.0 LUFS，差 0.0 | ≤0.5 LU ✓ |
| 字幕 | 149 句，最大誤差 0.000 s | ≤1 格 ✓ |
A、B 用同一份配音，所以配音拼接處另外查（`$CLAUDE_JOB_DIR/tmp/splice_clicks.py`）：兩個被拼接的 take（scene_001、scene_015）4 個接點 ±150 ms 內爆音 0；
接點兩側跳動（音高半音／響度 dB）：s01 9.75/7.77、1.22/0.48；k2 1.75/1.23、1.50/0.42。s01 第一個接點偏大，但原 take 同一句界（問句→答句）本來就是 8.59/8.23，
配對差 1.16/0.46；其餘三個接點沒有做配對比較（句界位置跟原 take 不同）🟡。ASR 讀回 CER 0.059／0.025（ok）。

## 已知限制
- 片名、資料截止月、草稿徽章、來源列、頁碼「P.14 / 24」印在每一幀：改片名或增刪投影片＝全部重畫（約 5–8 分）。要再快得把 meta 列拆成獨立疊層，這次沒做。
- 場景是最小重畫單位：一句時長變了，整個場景（含前面沒變的句子）的 media 與角色都重畫；場景外不動。
- 角色動作在每次換頁時 0.4 s 內收回姿勢（尾巴、耳朵、呼吸歸零）——為了讓場景可獨立快取；視覺上是換頁時的一個停頓，沒有請人看過 🟡。
- GPU 光柵與舊的軟體光柵在邊緣反鋸齒不同（>8/255 的像素 1.29%），目視無差；`CF_MASCOT_GPU=0` 可退回 CPU（仍是拼貼）。
- 配音窗口結論只來自 2 個場景 × 3 seed，音高用自相關估計 🟡；拼接後的 take 不再是「一次合成」，speech_check 記錄的是整場景讀回、不是重試結果。
- 字幕仍在每次 voice 時對整支重跑 whisper 對齊（約 10–15 s）；media 用「音檔未變就沿用上次句子時間」擋住它的捨入雜訊。
- `upload/manual/` 的標題、說明檔由 package／manual-kit 產生，(c) 之後沒重產（要在 gate_final 核可後跑）。
- 新增的程式碼改動（例如改了 mascot 動作模組）會讓該步驟快取全部失效，下一次就是整支冷渲（約 8–15 分），這是刻意的安全預設。

## 測試
新增：`test_sentence_ids`（7）、`test_fix_scope`（7）、`test_voice_window`（5）、`test_voice_splice`（4）、`test_voice_generator_window`（2）、
`test_mascot_scenes`（7）、`test_media_cache`（1）、`test_seam_check`（2），`test_explainer_media_browser`／`test_mascot_render`／`test_assembly_timeline_media` 各加快取重用與只重畫被改場景的案例。
`pytest tests/unit`：1336 passed、1 skipped、1 failed（`test_multi_provider.py::test_returns_first_provider_results`，cowos-v3 報告已列為既有失敗，該檔與 `visual/multi_provider.py` 本分支沒動）。

## 副作用與清理
- `output/cowos-inc/`（上片版＋實驗結果＋快取約 1 GB）、`output/cowos-full/`（接縫比對用的 B，約 0.8 GB）：都在 gitignore 的 output/，沒有 commit；
  cowos-full 驗收完可刪（`rm` 在 deny，留給 orchestrator）。
- 暫存腳本、profile 圖、被搬走的舊快取在 `$CLAUDE_JOB_DIR/tmp/`（job 刪除時一併清掉）。
- 沒動 cf-cowos-v3 的 run dir（只讀、複製）；沒 push、沒開瀏覽器、沒用付費服務。

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
- CoWoS 實測（`output/cowos-inc`，`produce.py` 正式流程，deck/media gate 由腳本立即核可；wall＝存檔到 release.mp4，🟢 log 在 `production.log.jsonl`）：
  - 舊碼整支重渲（同一 run 的 production.json）：media 504.9＋assembly 132.1＋mascot 1264.3＋mix 44.5 ≈ **1946 s（32 分）**＋改句場景配音。
  - 新碼整支冷渲：media 514.2／assembly 150.6／mascot 158.3–164.5／mix 44.3 ≈ **870 s**（media 本身沒變快，省在角色與組裝）。
  - (a) 第一次 468.5 s ✗：assembly 快取剛被清空（冷）、角色 10 場景重畫、media 4 張重畫。查出兩個「位置洩漏進 identity」：
    角色用了 cue 的次格位移；media 的句子時間來自整支 SRT，前面場景長度一變，後面句子相對時間在 0.01 s 捨入上翻動。修：角色 cue 對齊格線＋多畫 1 格再裁、media 沿用音訊未變場景的上次句子時間。
    再測 425.7 s ✗：仍有 6 場景重畫——timeline 檔名是毫秒捨入的累計值，後面場景的槽長抖 ±1 ms。修：槽長改用 10 ms 量化（後又改成以該場景音檔雜湊為準，見下）。
  - **(a) k2 兩句（200 萬／65 萬補「每月」＋封裝數）：180.6 s ✓**（voice 51.7：只重配第 3–9 句窗口；media 20.2：1 張；assembly 28.1：normalize 1 段；mascot 38.2：畫 825 格＋overlay 30.0；mix 24.1）。
  - **(b) k2 畫面標題改「封裝數不一定翻倍」：143.7 s ✓**（voice 10.9 全部沿用；media 20.8：1 張；assembly 33.0；mascot 36.9：0 場景重畫；mix 24.0）。
  - **(c) 「晶片卻不一定翻倍」→「封裝數卻不一定翻倍」（標題、s01、k2 旁白、縮圖 A）：548.4 s**（voice 80.6：兩個窗口；**media 314.1：24 張全重畫**——deck 標題印在每一幀的 meta 列（`series`），這是正確的失效；mascot 48.6：5 場景（應為 2，另 3 個是毫秒捨入翻動，已改成以場景音檔雜湊／實測長度為 identity，1ba27b5）；assembly 61.3；mix 24.0；縮圖 1.4）。
    fix_scope 修改前列出的連動處（`experiments/fix_scope_c_before.json`）：s01.4、k2.8 旁白、deck 標題、thumbnail.json promise/lines/highlight、thumbnail_variants a、upload/manual/title.txt、description.txt（後兩者由 package／manual-kit 重產）。
