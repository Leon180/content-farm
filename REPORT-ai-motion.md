# AI 圖動態化接進 pipeline（feat/ai-motion）

## TL;DR
- 每張 `ai_image` 預設做 2.5D 視差，片長 ≤3 秒，在 slot 內來回播放，取代原本的 Ken Burns。用的是 Depth Anything V2 Small，每張約 3–4 秒。細長物件有三道緩解：細物攤平、邊緣羽化、位移上限。對照截圖：`docs/design/ai-motion/s24a_thin_mitigation.png`。🟢
- `motion: wan` 只給關鍵鏡頭，每支片最多 2 個，policy 和 QC 都會擋第 3 個。Wan 片段由夜間批次 `scripts/ai_motion.py bake` 先算好放進快取，正式渲染只讀快取。沒有快取時退回視差，QC 給 warn。🟢
- 九尾狐重出（沒有重配音、沒有重生圖）：
  - s06 用 Wan：baked 863.9 秒，閘門等待 0 秒。
  - s09、s13、s24a 用視差。
  - QC 0 error／0 warn。成片 `output/yokai-kyubi/assembly/draft.mp4`，519.1 秒。
  - 預覽頁：`/Users/lileon/project/content-farm/.claude/worktrees/cf-ai-motion/output/yokai-kyubi/upload/manual/preview.html`。🟢
- pytest：1 failed（基準那支 multi_provider）／1122 passed／1 skipped；新增 17 支測試。🟢
- 沒有開瀏覽器、沒有上傳、沒有 push。

## 1. 設計

| deck `media.motion` | 做法 | 成本 | 失敗時 |
|---|---|---|---|
| 省略／`parallax` | `scripts/motion_parallax_worker.py` 在 mlx-video venv 跑：深度估計 → 逐格反向映射 → H.264。1920×1080，3.0 秒（90 格 @30fps），smoothstep 緩動 | 每張約 3–4 秒，峰值約 1.6 GB（試做量測） | 退回 Ken Burns，QC warn |
| `wan` | Wan2.2-TI2V-5B q8 I2V：832×480、69 格 @24fps（2.875 秒）、20 步、guide 5.0、aggressive tiling、seed 沿用插圖。prompt 是插圖 prompt 加上 `Motion: <motion_prompt>` | 每段約 15 分鐘，峰值約 26 GB，只在夜間批次跑 | 退回視差，QC warn |
| `ken_burns` | 舊行為 | ffmpeg | — |

- **放進 slot**：`ffmpeg_ops.motion_loop` 把片段等比放大裁切到 1920×1080（lanczos，Wan 從 832×480 放大也走這裡），先正播再倒播，循環填滿 slot，再疊上 overlay。
  - 「AI 示意圖」徽章畫在 overlay 上，所以三種動態都會保留。
  - 視差頭尾的速度是 0，倒播轉向時不會頓一下。
  - Wan 是 24fps，改成逐格重新計時到 30fps（速度 0.8 倍），不補重複格，避免抖動。
- **快取**：`assets/ai_motion/<slide>.<kind>.{mp4,json}`。sidecar 的 `key` 由圖片 sha256、模型、參數、prompt 雜湊而成，任何一項變了就視為過期。
  - media 步驟的 inputs 只加 `assets/ai_motion/*.wan.*`：夜間 bake 完成會觸發 media 重跑，media 自己寫入的視差快取不會。
- **Wan 閘門**（`wan.busy_processes`，接進 `illustrate.wait_for_memory`）：
  - 先取 runner 的全機 render lock，所以 bake 期間不會有其他 pipeline 開始渲染。
  - 接著等 memory pressure 降到 normal，而且沒有其他 ffmpeg／remotion／mflux／mlx_video 程序在跑。
  - 比對的是程序實際執行的東西：執行檔本身，或直譯器正在跑的 script／`-m` 模組；只在參數裡提到這些字的程序不算。
  - 實際碰過：開工時 `pgrep -fl 'mflux|mlx_video|ffmpeg'` 命中一支 orchestrator 的 zsh，只因為它的 heredoc 文字裡有 mflux。裸 pgrep 會因此一直等下去。
  - 測試裡的反例（`grep mflux`）一開始也被我誤判成 busy，已經修正，有測試覆蓋。
- **路徑**：讀 env 或 `--env-file` 的 `CF_MLX_VIDEO_HOME`（底下有 `venv/`、`models/`），也可以用 `CF_MLX_VIDEO_PYTHON`／`CF_DEPTH_MODEL_DIR`／`CF_WAN_MODEL_DIR` 個別覆寫。程式裡沒有寫死路徑；都沒設時退回 Ken Burns。
- **credits**：每筆 ai_image 多一個 `motion` 區塊。
  - Wan：model、repo、origin_repo、license、prompt、seed、params、upscaled_to。
  - 視差：深度工具與授權、params、depth_strength、thin_share。
  - 退回時另記 `requested`、`fallback_reason`。
  - 說明欄的「AI 示意圖」段多兩行：Wan（動態）和 Depth Anything V2 Small（標為工具）。
- **QC**：
  - `policy_findings`：`wan` 超過 2 個是 error，`motion_prompt` 適用擬真／畫家字眼的規則。
  - `ai_motion_findings`：Wan 超過 2 個是 error；Wan 缺 model／prompt／seed 是 error；視差缺工具是 error；有退回是 warn。
  - 沒有 motion 欄位的舊 credits 不檢查，相容第一輪的產物。
- **deck skill**：新增「AI image motion」一節，寫明怎麼選、上限、bake 指令和路徑。

### 細長物件的緩解（決策要求寫進報告）
1. **細物攤平**：深度圖做 morphological opening，圓盤直徑 `thin_px=31`。比圓盤細的前景（蘆葦、鬚、細枝）改用它背後的深度，跟著背景一起動，不會被扯開。
2. **邊緣羽化**：dilate 9×9 後做 Gaussian σ=6，前景帶著自己的邊一起移動。
3. **位移上限**：深度造成的相對位移最多 18 px（以 1920 寬計）。超過時整體縮小深度強度（九尾狐四張的 strength 是 0.71–0.83）。
4. **降低位移量**：預設 zoom 0.06、pan ±0.02，左右方向逐張交替。試做時是 zoom 0.12、pan 0.06。

- 對照：`docs/design/ai-motion/s24a_thin_mitigation.png`，左是原圖，中是不緩解，右是緩解後，都取末格右側蘆葦。不緩解時莖會彎折、出現波紋，緩解後是直的。🟢（截圖肉眼判讀）
- 代價：被攤平的細物沒有視差，看起來和背景同層。九尾狐四張被攤平的面積佔 0.7–3.3%。🟡

## 2. 改動檔案（程式 commit `174a7ed`；merge 是 `c079cc5`）

| 檔案 | 內容 |
|---|---|
| `explainer/deck.py` | `Motion` enum；`Media.motion`、`motion_prompt`，只允許用在 ai_image；`motion_kind` |
| `explainer/motion_cache.py`（新） | env 路徑、快取路徑與 key、sidecar |
| `explainer/parallax.py`（新） | 參數（≤3 秒）、呼叫 worker、快取、credit |
| `explainer/wan.py`（新） | 模型與授權、參數驗證（4n+1、≤3 秒、32 的倍數）、prompt、argv、閘門、generate |
| `explainer/motion.py`（新） | 依序選 wan → parallax → ken burns，附退回原因 |
| `explainer/motion_bake.py`（新） | 列出 Wan 鏡頭（>2 拒絕）、只算缺的 |
| `explainer/media.py`、`media_run.py`、`ffmpeg_ops.py` | `_ai_image` 接上動態；`motion_loop`；credits 說明欄 |
| `production/qc.py`、`steps.py` | 前述 QC；media inputs |
| `scripts/motion_parallax_worker.py`（新） | 在 venv 跑的 worker |
| `scripts/ai_motion.py`（新） | `status`／`bake`，cron 範例寫在 docstring |
| `scripts/media_to_visual.py` | 讀 motion env |
| `.claude/skills/deck/SKILL.md` | motion 規則 |
| `tests/unit/test_explainer_motion.py`（新） | 17 支 |

測試涵蓋：
- schema；env 路徑與覆寫；視差 ≤3 秒與方向交替；快取 key（圖片或參數變了才重算）；worker 失敗。
- 選擇順序：沒有工具→Ken Burns；明確指定 ken_burns；Wan 已 bake／未 bake；worker 壞掉。
- Wan 參數驗證；prompt 保留插圖 prompt 並擋擬真字眼；argv。
- 閘門：3 正例、2 反例、排除自己的 pid，另有對照組。
- bake：>2 拒絕；只算缺的，沒有圖的跳過。
- QC：上限；漏記參數；退回 warn。
- 說明欄列出模型；media inputs；`motion_loop` 用 ffmpeg 實測輸出格數正好等於 slot。
- 快取檔名不互撞（見 §5 的 bug）。

## 3. 九尾狐重出

- 來源：`cf-ai-illustration/output/yokai-kyubi`（只讀），`cp -R` 到本 worktree 的 `output/`。
- deck 只改 s06：加上 `motion: wan`，以及 `motion_prompt: "the nine bushy tails sway slowly behind the beast, thin mist drifts across the mountain ridge, the beast itself stays still, static camera, gentle subtle motion"`。
  - 選 s06 的理由：它就是試做 s05「霧中擺尾」的同一題材（九尾獸站在霧中山脊），是 Wan 試做時效果最好的那一段。
- 執行順序：
  1. `ai_motion.py bake`：開跑前 `pgrep` 沒有命中。
  2. 沿用上一輪的 `after_media.py` 跑 policy → media → assembly → qc → package。這樣不走 runner 的指紋流程，**不會重配音**。
  3. `produce.py manual-kit`。
- 結果：
  - media：s06 用 Wan（`wan 69f@24 ping-pong (baked)`）；s09／s13／s24a 用視差（build 3.2–3.7 s，strength 0.71／0.83／0.76）。
  - QC：10 項全部 ok，其中 `ai_motion: motion recorded for 4 AI image(s): parallax, wan`、`ai_image: 4 … labelled 「AI 示意圖」`、`credits: 16 credited assets, none pending`。
  - 片長 519.1 秒，和前一版相同。🟢
- 前後對照（commit）：`docs/design/ai-motion/kyubi_before_after.jpg`。每列一張 AI 圖，左欄是前一版 Ken Burns 的中點，右兩欄是新版的「起點+1.5 秒」和「中點」。四列都有「AI 示意圖」徽章。
- Wan 片段本身我抽了第 0／34／68 格檢查：守住原圖，尾巴有擺動，耳朵在後段變深。🟡（我的判讀，請在 gate 看）
- 這支片仍停在 gate_final，**沒有代為核可**。看完要放行時：`python scripts/produce.py approve --run-dir output/yokai-kyubi --gate final`。
- 需要 Leon 看的：
  - s09 的白狐仍然被字卡遮住，這是上一輪留下的問題，這次沒動。
  - 來回播放的「呼吸感」在 18–22 秒的 slot 裡會重複 3–4 次。如果覺得單調，可以改成「播一次，之後接慢速 Ken Burns」，是 `motion_loop` 一處的改動。🟡

## 4. 算力預算（M 系列／32 GB，本次實測 🟢，估算 🟡）

| 項目 | 本次 | 每支片估算 |
|---|---|---|
| 視差片段 | 每張 3.2–3.7 秒（含載入深度模型）；含 overlay 的整個 slide 是 15.5–16.2 秒，前一版 Ken Burns 是 11.2–16.6 秒 | 4 張約多 20 秒；20 張約 1–2 分鐘 🟡 |
| Wan 片段（bake） | 863.9 秒；swap 6.8→10.6 GB；閘門等待 0 秒；mlx-video 這次沒有印出 peak，峰值沿用試做的 26 GB | 上限 2 段 ≈ 29 分鐘，夜間跑 |
| media 步驟 | 牆鐘 2,349 秒，其中約 30 分鐘是在等 load 降到 8 以下（其他 worker 讓 load 到 70）；實際 `Placed 29 clips … 548.4s` | 不變；動態只多幾十秒 |
| assembly | 804 秒（含等 load 約 10 分鐘） | 不變 |

結論：視差幾乎不增加成本；Wan 每支片最多約半小時，只能放夜間批次跑。

## 5. 過程中的 bug（已修）
- `clip_paths` 原本用 `Path.with_suffix`，`s06.wan` 被截成 `s06.mp4`，Wan 和視差會共用同一個檔名。第一次 bake 的產物就是這個名字。
  - 修正後我把那三個檔 `mv` 成 `s06.wan.*`。sidecar 的 key 不含檔名，所以 `status` 判定為 cached，不必重算 15 分鐘。
  - 補了回歸測試。
- 那次 bake 用的是閘門修正前的程式（會把 `grep mflux` 誤判成 busy），誤判方向只會多等、不會提早開跑；當時實際等待 0 秒。

## 6. 清理與副作用
- `output/yokai-kyubi/`（gitignored）是交付物，保留；裡面的 `media_report.json` 和 logs 是這次重寫的。
- job tmp（`~/.claude/jobs/9d9043b5/tmp/`）放了 `px/`（試跑片段）、`mark_wan.py`、`patch_*.py`、`after_media.py`、`before_after.py`、`s06_wan_strip.png`，job 刪除時一起清掉。
- `docs/design/ai-motion/`（docs/ 被 gitignore）比照前例用 `git add -f` commit 兩張圖。
- env：渲染時以 env 帶入 `CF_MLX_VIDEO_HOME=/Users/lileon/.local/share/mlx-video`，**沒有寫進任何 .env**。正式使用要把它加進主 checkout 的 `.env`；不加的話 ai_image 會退回 Ken Burns，QC 會 warn。
- 讀取了主 checkout 的 `.env`，傳給 assembly 當 `--env-file`（只讀，沒有複製進 worktree）。
- 沒有 push、沒有開瀏覽器、沒有上傳、沒有呼叫付費 API。
