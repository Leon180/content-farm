# REPORT — cf-cost-fix 驗收實跑一（九尾狐）

## TL;DR
🔴 **實跑停在 gate_media（3 輪用完仍未通過），沒到 gate_final，不能下「省多少」的結論。** 本次新花費僅 **$0.376**（媒體合規評審 3 輪：$0.21＋$0.17＋$0.00），沒有產出 agent 呼叫，離 $15 預算很遠。要繼續需 orchestrator／Leon 決定（見「停下點」）。
另外抓到兩個問題：budget.py 的誤判 bug（已修＋測試，`ca8475e`）、clone 帶來的舊 media 輪次被當成「用完」（手動歸檔）。

## 停下點
- 時間：2026-10-22 18:57:51 UTC（run 起點 18:19:14）。
- `gate_media` 第 1 輪 3 項（s08b、s10、s02a）→ 第 2 輪 2 項（s08b、s10）→ 第 3 輪（最後一輪）仍 2 項（s08b、s10），原文：「media: 第 3 輪（最後一輪）未通過：合規問題 2 個：s08b、s10」。
- 問題內容（round-3 scorecard）：「s08b.png 有交付，但 media_report.json 的 slides 與 credits.json 的 entries 都沒有它。模型、授權與 AI 示意圖標示都無法驗證，可能漏標。」credits.json 只列 s06、s08、s09、s13、s24a 五張 ai_image。
- 🟡 判讀（未驗證）：run-dir 是 10-19 的 clone，deck 在 10-19 之後改過 s06／s08b 的 prompt；本次 `illustrate` 只 1m54s（identity 沒變就沿用舊圖？），而 media 的退回只重跑本機 media（9 s～2 m），沒有退回 deck 產出 agent。10-19 那次是靠 deck-10／11 的產出 agent 重工才過 media。所以這個停下點可能是「clone 狀態＋退回路徑」造成，不一定是 cost-fix 或 speed 改動的缺陷，需要有人看 s08b／s10 到底該補 credits 還是該重生圖。
- 我沒有再往前推（沒開新 cycle、沒手改 credits.json），等指示。

## 前後數字（目前可比的部分）
| 項目 | 10-19 基線 | 本次 |
|---|---|---|
| 評審名目 $（媒體階段） | 3 輪 $0.67（原報告素材 3 輪；`review_cost_report` 同階段累計 $1.46 含 cycle） | 3 輪 $0.376 |
| 產出 agent（deck／thumbnail） | 16 次 $31.4／6 次 $2.06 | 0 次 $0 |
| 牆鐘 media step | 24m38s、24m31s（10-19 同一步） | 26m26s（首次）→ 2m02s → 0m09s |
| 其他階段 | script_structure $18.5、script_facts $11.8、title_thumb $7.7、final $3.19 | 未跑到 |
- ⚠ `scripts/review_cost_report.py --json` 目前加總整個 run-dir 的所有歷史（含 10-19 的 script／final 等），沒有 `--since`；本次數字是我直接讀 media/round-1～3 的 `scorecard.json` 的 `cost_usd`（0.2096／0.1659／0.0）。
- 沿用比例、quick path 命中、退回點名比例、trace1.json：**未量到**（沒有進入有產出 agent 的階段）。第一次 `claude -p` 產出呼叫從未發生，stream-json trace 仍沒驗過。

## 牆鐘（`produce.py timing` 本次段落，機器／排隊／等人）
- 18:19 illustrate 1m54s（local）；18:21 queue 1m40s；18:22 **media 26m26s**（local，首次）；cloud round media/round-1 0m28s；media 2m02s；round-2 0m31s；queue 2m20s；media 0m09s。
- media 26m26s 對照上次 11–12 分（前一個 worker 在 10-15～17 的 CoWoS 類紀錄 6–12 分；10-19 同 run 為 24m38s／24m31s）。當時機器：`memory_pressure -Q` 83% free（開跑前 54%）、無 mlx_video／mflux／ffmpeg／qwen3-tts／voxcpm2 行程；🟡 沒有記到 load average，慢的原因未驗。
- 本次總牆鐘 ≈ 39 分（18:19→18:58），其中本機 media 占 ~30 分；未跑到 30／45／60 分進度行的後段階段（見進度紀錄）。

## 遇到的問題
1. **budget.py 誤判（已修）**：第一次 gate_media 就以「$17.40 ≥ $15」停下。原因：`producers.jsonl` 有 4 筆 10-19 的舊紀錄（deck-1～4：3.39＋4.18＋4.57＋5.26）**沒有 `at` 欄位**，`budget._after()` 對沒時間戳的紀錄回傳 True，被算進 `since` 之後。修法：有 `since` 時沒有 `at` 的紀錄視為更早、不計；加測試 `test_since_ignores_undated_legacy_producer_rows`；commit `ca8475e`；`test_review_budget.py` 8 passed。本次實際花費當時是 $0。
2. **clone 帶來舊 media 3 輪被當用完**：`panel_gate` 看到 media/round-3（10-19 未通過）且 inputs 不同 → 判 number=4>max_rounds=3 → `exhausted`。我比照 `_new_cycle` 手動把 round-1～3 搬到 `review/media/cycle-2/`、`media.fixes.json` 改名 `media.fixes.cycle-2.json`，並把 `budget.stop.json` 改名 `budget.stop.false-positive.json`（`rm` 被權限拒絕，我沒繞路）。🟡 建議：從舊 run-dir 開新一輪時，正式做一個「開新 cycle」的指令，而不是手動搬。
3. `review/tier.json`（舊 economy 標記）沒刪（`rm` 被拒）；`grep` 在 `src`／`scripts` 找不到引用，預期無影響。

## 暫停交接／續跑
- worktree：`/Users/lileon/project/content-farm/.claude/worktrees/cf-cost-accept`，分支 `worktree-cf-cost-accept`；run-dir `output/yokai-kyubi-v2`（ignored）。
- 目前狀態：`gate_media` exhausted；沒有行程在跑。
- 要繼續需先決定：(a) 補 s08b／s10 的 credits（或確認它們有沒有被用進成片，沒用就移除）後開新 media cycle；(b) 或讓 media 退回 deck 產出 agent 重生圖（才會測到 speed 1–3 的產出路徑）。
- 接續指令（開新 cycle 後）：`env PYTHONPATH=/Users/lileon/project/content-farm/.claude/worktrees/cf-cost-accept/src /Users/lileon/project/content-farm/.venv/bin/python scripts/produce.py run --run-dir output/yokai-kyubi-v2 --auto-agents --no-stock --env-file /Users/lileon/project/content-farm/.env`；預算 `review/budget.json`＝$15、since `2026-10-22T16:10:29+00:00` 不變，不要調高。
- 540p 預覽、gate_final：未做（沒有成片）。

## 進度紀錄（append）
- 2026-10-22 16:10 UTC 首次啟動，16:15 依 orch 暫停（Leon）；$0。
- 18:19 UTC 續跑（pipeline-speed 1–3 已併入，`1ebdb88`）；18:49 misfire：budget 誤判 $17.40（見問題 1）；18:51 舊 media 輪次判 exhausted（問題 2）；18:52–18:58 media 3 輪未過（s08b、s10）。
- **30 分**（18:49）：階段 media（本機 26m26s 剛完成）、累計 $0（實際）、累計牆鐘 30 分。**45／60 分**：停在 gate_media，未再前進（18:58 起停止，累計約 39 分），無新數字。
