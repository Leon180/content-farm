# AI 短影片本機試做（≤3 秒）＋ 2.5D 視差對照（feat/ai-video-trial）

## TL;DR
- 本機實測兩個 Apache-2.0 模型（都是 MLX，都用九尾狐 klein 圖當起始畫面），各做 4 段 I2V＋1 段 T2V，每段 2.9 秒（69 格 @24fps，832×480）。另外做了 2.5D 視差對照組。🟢
  - **Wan2.2-TI2V-5B（q8，20 步）**：每段 12.6–17.7 分鐘。畫風和構圖都守得住起始圖，動作自然（擺尾、轉頭、緩推、橫移）。**I2V 畫質最好。**
  - **FastWan2.2-TI2V-5B（DMD 3 步）**：每段 6.0–8.1 分鐘，去噪只要 28 秒，VAE 解碼佔大部分時間。I2V 第 1 格就跳離起始圖，改畫成飽和、偏卡通的畫風，s09 還**自己蓋了假紅印**。**不建議用在 I2V。**
  - **2.5D 視差**（Depth Anything V2 Small＋逐格位移＋ffmpeg）：每段 2–3 秒，峰值 1.6 GB。完全不改畫，但只有鏡頭在動，細長的蘆葦會被拉扯變形。
- 記憶體：峰值 footprint 兩個模型都約 26 GB（Wan 25.9、FastWan 26.0），32 GB 機器幾乎吃滿；生成時整機 swap 衝到 13–31 GB。**AI 影片不能和渲染或 mflux 並行。**
- 建議：**視差當 `ai_image` 的預設動態**（取代 Ken Burns，幾乎零成本）；**Wan2.2 I2V 只給每支片 2–3 個關鍵鏡頭**，夜間批次跑；FastWan 不收。
- 最新的 LTX-2.3（2026）合計要 ≈46 GB 下載，超過 30 GB 上限，**沒試**；授權是年營收 < US$10M 才免費、產出要標示機器生成。要不要試由 Leon 決定（§6）。

## 1. 候選模型調查（2026-10-16）

證據等級：🟢 本機實測／親讀原始檔　🟡 二手（模型 card 作者自報、部落格）　🔴 未驗

| 模型 | 版本／發布 | 參數 | Mac 支援 | 權重（實際要下載的） | 授權（原始 repo LICENSE） | 結論 |
|---|---|---|---|---|---|---|
| **Wan2.2-TI2V-5B** | Wan2.2，2025-07-28 | 5B | MLX：`Blaizzy/mlx-video`（pin `87db56a`）🟢 本機跑通 | `Anes1032/Wan2.2-TI2V-5B-mlx-q8`：DiT 5.40＋T5 11.36＋VAE 2.82＝**19.6 GB** 🟢 | `Wan-Video/Wan2.2` 的 `LICENSE.txt`＝未修改的 Apache-2.0 全文 🟢 | **實測 #1** |
| **FastWan2.2-TI2V-5B**（DMD 3 步蒸餾） | FastVideo（hao-ai-lab） | 5B | MLX 權重 `lBroth/FastWan2.2-TI2V-5B-MLX`；**上游 mlx-video 沒有 DMD 取樣器**，本次自寫 `fastwan_generate.py` 補上 🟢 | 只下 DiT `model.safetensors` **10.0 GB**，T5／VAE 與上一列共用（symlink）🟢 | 原始 HF repo `FastVideo/FastWan2.2-TI2V-5B-FullAttn-Diffusers` card 標 `apache-2.0`、無 LICENSE 檔；FastVideo GitHub repo 的 LICENSE＝Apache-2.0（GitHub API 判定）；基底 Wan2.2 是 Apache-2.0 🟢 | **實測 #2** |
| LTX-2.3 distilled（22B） | 2026-03 🟡 | 22B | MLX：`dgrauet/ltx-2-mlx` v0.16.3（2026-10-09，仍活躍）🟡；`mlx-video` 也支援 LTX-2 | q4 包 distilled 子集 ≈20.5 GB＋Gemma-3-12B 文字編碼器（≈7–24 GB）🔴；與 Wan 合計 **≈46 GB，超過 30 GB 上限** | `Lightricks/LTX-2` 的 `LICENSE-2_x`（LTX-2.x Community License，2026-08-11）：年營收 ≥ US$10M 的實體要買授權（第 99 行）；產出必須「expressly and intelligibly disclaiming that the information and/or content is machine generated」（第 510 行）；授權方不主張產出權利 🟢 | **有條件可商用**；超預算未試，見 §6 |
| LTX-2.5 | 2026-08-11 開權重 🟡 | 22B＋Gemma-4-12B | MLX 包 47 GB（int4）起 🟡 | 太大 | 同 LTX-2.x 授權 🟡 | 不試 |
| LTX-Video 0.9.8 2B distilled | 2025 | 2B | 無 MLX；diffusers MPS 無實測報告 🔴 | 6.34 GB＋T5-XXL ≈9.5 GB 🔴 | LTXV Open Weights License：同樣 US$10M 門檻 🟡 | 舊世代，被 LTX-2／Wan 5B 取代 |
| Wan 2.5／2.6／2.7／3.0 | — | — | — | **沒有釋出權重**（3.0 只有 API）🟡 | — | 不可能本機跑 |
| Wan2.1-T2V-1.3B | 2025-02 | 1.3B | mlx-video 支援，但**只有 T2V** 🟡 | 4-bit 0.8 GB＋共用 T5 | Apache-2.0 🟡 | 不能做 I2V，不選 |
| Kandinsky 5.0 I2V Lite | 2025-09 起 | 2B | 無 Mac 實測證據 🔴 | 文字編碼器 Qwen2.5-VL-7B ≈16 GB 🔴 | MIT 🟡 | 授權乾淨但 Mac 不確定，列「僅參考」 |
| HunyuanVideo 1.5 | 2025-11 | 8.3B | 無 MLX／MPS 報告 🔴 | 大 | Tencent Hunyuan Community：排除 EU／UK／南韓，MAU > 1 億要另談 🟡 | 太大，「僅參考」 |
| CogVideoX-5B-I2V／Mochi／Pyramid Flow／SkyReels／Step-Video | — | — | 無 MLX 🔴 | — | 混雜（CogVideoX-5B 要商用登記）🔴 | 不試 |

**深度模型（2.5D 對照組）**：`depth-anything/Depth-Anything-V2-Small-hf`，24.8M 參數、99 MB。官方 GitHub README 的 LICENSE 段原文：「Depth-Anything-V2-Small model is under the Apache-2.0 license. Depth-Anything-V2-Base/Large/Giant models are under the CC-BY-NC-4.0 license.」，repo 的 LICENSE 檔 GitHub API 判定 Apache-2.0 🟢。**只有 Small 可商用**，不要升級成 Base／Large。Apple Depth Pro 的權重是研究用授權，不可商用 🟡。

**安裝陷阱**：PyPI 上的 `mlx-video` 不是 Blaizzy 的專案（是另一個同名套件）🟡，一律從 git 裝並 pin commit。mlx-video 從 2026-05-13 起沒有新 commit 🟡。

**為什麼選這兩個**：唯一能在 30 GB 下載上限內「兩個都可商用、都能 I2V、都有 MLX」的組合，就是 Wan2.2-5B ＋ FastWan（共用 11.4 GB 的 T5 和 VAE）。換成兩個不同家族（例如 Wan＋LTX-2.3）會到 ≈46 GB。代價是兩個模型同源，差別主要在「20 步 vs 3 步」的速度／畫質取捨，不是兩種架構的比較。

（完整調查含所有來源連結：子代理報告，未 commit；重點都已收進上表。）

## 2. 試做設定

- **起始畫面**：`feat/ai-illustration` 的 FLUX.2 [klein] 4B 試作圖（1024×576，seed 42），從唯讀 worktree 複製到 `output/ai-video-trial/src/`。
- **段落**（`docs/design/ai-video-trial/shots.json`）：

  | id | 起始圖 | 想要的動態 |
  |---|---|---|
  | s05-tails | s05 青丘九尾獸 | 霧中擺尾 |
  | s09-push | s09 塗山白狐 | 鏡頭緩推 |
  | s13-lantern | s13 拜狐神 | 燈籠搖曳、香煙 |
  | s24a-reeds | s24a 田邊墳地 | 蘆葦擺動、狐狸回頭、橫移 |
  | t2v-fox-fields | （無，純文字） | 同 s24a 題材的 T2V 對照 |

- **AI 參數**：832×480（Wan 480P 標準尺寸；必須是 32 的倍數），69 格（必須是 4n+1；@24fps＝2.875 秒，≤3 秒），seed 42。
  - Wan：UniPC 20 步、guide 5.0、shift 5.0（官方建議 40 步，減半換時間）。
  - FastWan：DMD 3 步，sigmas [1.0, 0.757, 0.522, 0]，guide 1、renoise（照 model card）。
  - VAE 解碼：第一段 s09 用 `auto` tiling，其餘用 `aggressive`，想降記憶體（見 §3）。
- **視差參數**：1280×720、72 格（3.0 秒）。深度圖先 dilate 再模糊，免得前景邊緣撕裂。動態是 smoothstep 緩動的縮放加橫移，近景的位移量大於遠景。
- **紀律**：
  - 一次只跑一段，每段獨立程序，生完就卸載，段與段之間停 10 秒。
  - 每段開跑前檢查閘門：有 ffmpeg／remotion／assembly 在跑，或有 mflux 在生圖（orchestrator 中途追加的要求），就等它結束。實際等過 3 次 cf-ai-illustration 的 ffmpeg，共 90 秒。
  - 閘門已做正反對照：真正的 `mflux-generate…` 程序會擋；只在參數裡提到 mflux 的程序不擋。
- **「AI 示意圖」**：三組都在左上角燒入，樣式沿用 ai-trial 的 `labelled()`（字高約畫面高度的 1/28，半透明黑底）。
- **工具**（都在 `docs/design/ai-video-trial/`）：
  - `run_video.py`：逐段生成＋量測。有閘門，單段超過 30 分鐘就殺掉並記錄。中斷後可以續跑。
  - `fastwan_generate.py`：上游 mlx-video 沒有 DMD 取樣器，這支自己補上。
  - `parallax.py`：視差組。
  - `clip_stats.py`：客觀數字，見 §4。
  - `build_gallery.py`：產生 gallery 和總覽圖。
  - `trial_common.py`：標籤、swap 取樣、閘門。

## 3. 實測數字 🟢

秒數是整個程序的牆鐘時間，包含載入模型。swap 是整台機器的數字，同時段還有其他 session 在跑，所以**不能全部算在本程序頭上** 🟡。

| 模型 | 段 | 秒 | T5 編碼 | 去噪 | VAE 解碼 | 取樣 RSS 峰值 | swap 前→最高→後（MB） |
|---|---|---|---|---|---|---|---|
| Wan2.2-5B | s09-push（auto tiling） | 821.8 | 76.2 | 389.7 | 347.4 | 5.22 GB | 8283→**31166**→11484 |
| Wan2.2-5B | s05-tails | 1059.9 | 45.0 | 378.0 | 630.8 | 5.23 | 10910→26052→16372 |
| Wan2.2-5B | s13-lantern | 937.7 | 50.0 | 372.4 | 509.6 | 5.21 | 12139→19424→16625 |
| Wan2.2-5B | s24a-reeds | 835.5 | 40.0 | 374.7 | 413.0 | 5.41 | 11236→18011→10190 |
| Wan2.2-5B | t2v-fox-fields | 756.5 | 28.8 | 351.0 | 372.8 | 5.21 | 5989→14442→8519 |
| FastWan-5B | s09-push | 362.4 | 20.6 | 28.2 | 308.1 | 9.76 | 8140→13279→8464 |
| FastWan-5B | s05-tails | 392.0 | | | | 9.49 | 8320→13980→8545 |
| FastWan-5B | s13-lantern | 368.8 | | | | 10.30 | 8545→14550→9043 |
| FastWan-5B | s24a-reeds | 457.3 | | | | 9.72 | 8979→19230→8899 |
| FastWan-5B | t2v-fox-fields | 487.6 | | | | 9.20 | 8867→18068→8794 |
| 視差 | 4 段合計 | 16.4（含 torch 載入）；單段 2.1–3.1 | — | 深度 0.15–0.49 | — | 0.91 GB | 無變化 |

（FastWan 後 4 段的分項時間在各段 `raw/*/*.log`，表上只列 s09 當代表。）

**峰值記憶體**：取樣 RSS 嚴重低估 MLX 的用量，因為 GPU 端的配置不算在 RSS 裡。所以另外用 `/usr/bin/time -l` 各重跑一段 s09，讀 `peak memory footprint` 🟢：

| | peak memory footprint | maximum RSS | 牆鐘 |
|---|---|---|---|
| 視差（4 段一起跑） | **1.63 GB** | 0.91 GB | 16.4 s |
| FastWan-5B（bf16 DiT） | **25.97 GB** | 10.16 GB | 502.5 s |
| Wan2.2-5B（q8 DiT） | **25.94 GB** | 5.59 GB | 1111.9 s（去噪 423.6、VAE 629.2） |

兩個模型的峰值幾乎一樣（約 26 GB）。q8 和 bf16 的 DiT 差了約 5 GB，峰值卻沒有跟著拉開。所以峰值多半不是 DiT 決定的，而是 bf16 的 T5（11.4 GB）加上 VAE 解碼的暫存 🟡（推論；沒有逐階段量）。

讀法：
- 時間大頭是 **VAE 解碼（5–10 分鐘）**，不是去噪。FastWan 把去噪從約 6 分鐘壓到 28 秒，但整段只快 2 倍左右，因為 VAE 解碼省不掉。
- `aggressive` tiling 沒有變快（解碼 373–631 秒，`auto` 是 347 秒），swap 峰值倒是從 31 GB 降到 14–26 GB。但 swap 會受其他 session 影響，這個改善只能算 🟡。
- 32 GB 機器上，生成期間其他工作會明顯變慢。orchestrator 中途回報整機 swap 92%、load 27，當時 f9ab0177 的 mflux 也在跑。

## 4. 畫質判讀

客觀數字（`clip_stats.py`，畫面縮到 256 寬比較；`output/ai-video-trial/clip_stats.json`）🟢：
- **pop**：第 0 格到第 1 格的平均差。這個值遠大於 motion，就代表影片一開始就跳離起始圖，接在靜態圖後面會像跳接。
- **motion**：之後相鄰格差的中位數。
- **drift**：首尾兩格的差。
- **亮度變化**：末格減首格的 RGB 平均（負值＝變暗）。

| 段 | 視差 pop／motion／亮度 | Wan pop／motion／亮度 | FastWan pop／motion／亮度 |
|---|---|---|---|
| s05-tails | 0.07／0.53／−2 | 1.1／0.57／+3 | **8.6**／1.29／**−29** |
| s09-push | 0.10／1.03／+3 | 2.7／3.58／+2 | **11.5**／1.18／**−34** |
| s13-lantern | 0.04／1.29／−5 | 6.9／7.97／−5 | **12.7**／1.03／**−37** |
| s24a-reeds | 0.07／1.54／0 | 4.2／16.5／−2 | **15.6**／2.34／**−27** |
| t2v | — | 1.2／1.39／−3 | 2.4／1.97／+4 |

以下是我的判讀 🟡（gallery 可以直接看）：
- **Wan2.2 I2V**：
  - 四段都守住起始圖的筆觸和構圖，首格銜接很順（pop ≤ motion）。
  - s05 尾巴有在擺。s09 有緩推，白狐轉頭時臉會短暫變得像貓。s13 香煙升起、鏡頭微動，但燈籠幾乎沒擺。s24a 狐狸轉頭，鏡頭往左橫移，速度比 prompt 寫的「slow」快（所以 motion 高達 16.5）；後段月亮淡出畫面。
  - 可以當「插圖活起來」的關鍵鏡頭。
- **Wan2.2 T2V**：畫面偏白藍，像雪地白天，不是 prompt 寫的夜晚水墨；狐狸在走，但構圖鬆散。**T2V 比不上「klein 出圖＋I2V」**。
- **FastWan I2V**：四段的第 1 格都跳離起始圖（pop 8.6–15.6），整體變暗變飽和，筆觸換成平塗卡通。s09 旅人轉成正面，還**自己蓋了紅色假印章**（與 ai-trial 報告裡 schnell 的問題相同，觀眾可能誤以為是古畫落款）。
  - 我的取樣器是照 model card 自己寫的，**不能排除是我實作有誤** 🟡。但 T2V 正常，問題集中在 I2V，比較像模型本身的 I2V 條件化偏弱。
  - 想深究要拿 FastVideo 官方 diffusers 管線做對照，還要再下載約 24 GB，這次沒做。
- **FastWan T2V**：夜景、紅狐、土墳、月亮都對，構圖比 Wan T2V 好，但畫風偏卡通，不是水墨。
- **視差**：
  - 完全保留原圖，緩推的 s09 和 s05 效果最好，看起來像有景深的鏡頭運動。
  - 弱點有兩個：只有鏡頭在動，物體本身不會動；細長的蘆葦（s24a）和前景邊緣會被拉扯變形。我已經把 s24a 的橫移量從 0.06 降到 0.035，還是看得出來。
  - 適合大多數「插圖段落」，成本幾乎是零。

## 5. 接進 pipeline 的建議

現況：`MediaKind.AI_IMAGE` 由 `explainer/media.py:_ai_image` 處理，對靜態圖做 `ffmpeg_ops.ken_burns`。`production/publish.py:uses_ai_images` 決定上架時要不要做 AI 揭露。

1. **視差先做（低風險、立即有感）**：不新增 kind。在 `ai_image` 加一個 `motion: ken_burns | parallax` 欄位，預設用 `parallax`。
   - 深度模型只用 DA-V2 **Small**（Apache-2.0，99 MB）。
   - 一段 2–3 秒，可以和現有 media 步驟一起跑。
   - `credits.json` 把深度模型記成工具，不記成素材來源。
2. **新增 `media.kind: ai_video`**（Wan2.2-TI2V-5B I2V）：
   - 輸入是同一張 `ai_image` 圖，加上一句動態 prompt；沒有影片時退回 parallax。
   - credits 記錄 `model`、`repo`、`steps`、`seed`、`prompt`、`license: Apache-2.0`。
   - `uses_ai_images` 要把 `ai_video` 也算進去，才會觸發 AI 揭露。
   - QC 規則：`ai_video` 沒有「AI 示意圖」標籤就判 error，比照 ai_image。
   - 片長 ≤3 秒（69 格）。需要更長時，用視差補，或把同一段做慢放／倒放循環，不要拉長生成長度：記憶體和時間都會往上跳。
3. **每支片放幾段**：建議 **2–3 段 ai_video**，放在開場、轉折這類關鍵鏡頭；其餘插圖段落一律用視差。
4. **算力預算**（M5／32 GB 實測）：
   - Wan 一段約 15 分鐘，3 段約 45 分鐘；視差 20 段約 1 分鐘。
   - 必須排在**沒有渲染、沒有 mflux 的時段**（例如夜間），而且一次只跑一段。`run_video.py` 的閘門可以直接搬進 pipeline。
   - 生成期間這台機器不適合同時做別的重工作。
5. **還可以加速的地方**（未驗 🔴）：VAE 解碼佔一半時間，可以試 `tiling none`（快，但更吃記憶體），或常駐程序重用 T5 和 VAE（省下每段 30–75 秒的 T5 載入與編碼）。

## 6. 需要 Leon 決定的事

1. **要不要採用上面的分工**：視差當預設、Wan I2V 只給關鍵鏡頭、FastWan 不收。
2. **要不要試 LTX-2.3**（2026 年最新、畫質與音訊最強）：
   - 還要再下載約 26 GB，本次合計會超過 30 GB 上限。
   - 峰值記憶體報告是 ≈30 GB，在 32 GB 機器上很勉強。
   - 授權條件：年營收 ≥ US$10M 要付費；產出必須明確標示機器生成。我們的「AI 示意圖」標籤與上架揭露看起來可以滿足，但要 Leon 確認。
3. **權重要不要保留**：Wan q8（19.6 GB）、FastWan DiT（10 GB）和 mlx-video 的 venv 都放在本 job 的 tmp，會隨 job 刪除。要保留本機 AI 影片能力，請先把 Wan q8 和 venv 搬到持久位置（例如 `~/.local/share/mlx-video/`）。FastWan 不建議留。
4. **夜間批次的排程權**：誰負責確保 AI 影片生成時沒有渲染在跑？目前只有 `run_video.py` 的閘門，沒有跨 session 的鎖。

## 7. 產物與副作用

- commit（`docs/design/ai-video-trial/`，docs/ 在 .gitignore 裡，比照 ai-trial 前例用 `add -f`）：
  - 腳本 7 支、`shots.json`、`models.json`
  - `gallery.html`：離線、`<video autoplay loop muted>`
  - `clips/`：15 段，832 寬，CRF 24
  - `contact_sheet.jpg`
  - 大小見 CLAIMS。
- 不 commit（`output/ai-video-trial/`）：原始與標籤版影片、`results.jsonl`、`clip_stats.json`、全尺寸 gallery 和 contact_sheet.png、`PROGRESS.md`、`src/` 起始圖複本。
- 權重與 venv：`~/.claude/jobs/a4c4f187/tmp/{models,venv-depth,venv-mlxvideo}`，約 30 GB＋venv，會隨本 job 刪除。另有量測用的 `footprint_*.mp4`、檢查用的 `chk_*.png`、`ctl/`（閘門對照用），都在同一個 tmp。
- **我造成的一次中斷**：我用 `until grep …; do sleep; done; kill` 想在 s13 寫入結果後停掉舊 runner，但 grep 在 s13 還沒寫入時就判定成立，runner 在 s13 生成途中被殺。孤兒的生成程序我隨即也殺了，s13 用新閘門重跑，數字以重跑為準。
  - 誤判原因沒查。可能是 rtk hook 改寫了 grep 🔴：同一個 session 裡另一次多檔 `grep -h` 的輸出順序也和檔案順序不同。
- 沒有開瀏覽器、沒有上傳、沒有呼叫付費 API、沒有 push。
