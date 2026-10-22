# REPORT — pipeline 計時與加速（feat/pipeline-speed）

分支 `feat/pipeline-speed`，從 `feat/cost-fix`（3257f14）開。沒有 push、沒開瀏覽器、沒上傳、沒用付費服務；沒有跑過任何 `claude -p`（本 session 的 Bash 拒絕直接呼叫 `claude`，驗收實跑要走 `produce.py run --auto-agents`）。

## TL;DR
🟡 **計時帳本、基準、兩份離線分析做完（commit 5b84533）；優化本身與兩次驗收實跑還沒做。** 對話已接近 30 萬 token，依規則在此交接，建議換新 session 接手「進度紀錄」的待辦。
- 基準（九尾狐，Leon 的窗口 10-18 15:30→10-19 13:10 UTC）：牆鐘 21h34m；機器時間 3h44m（雲端 2h55m／本機 49m）；排隊 42m；等決定 3h12m；離開（≥3h）13h50m；退回造成的產出重寫 13 次 1h24m。與 Leon 給的 1,295／231 分吻合。
- 機器時間 3h44m 要降到 30 分，最大塊依序：deck 產出重寫、voice、評審輪次、media。

## 已做（程式，皆有測試；全套 pytest 1653 passed → 加新測試後 +5）
| 項 | 位置 |
|---|---|
| `timing.json`（machine／queue／decision／away／unattributed 分開、退回歸因到哪一輪）；從舊 log 回填 | [timing.py](src/content_farm/production/timing.py) |
| `produce.py timing --run-dir D`（甘特文字版＋前 5 瓶頸）、`--all D...`（並排）、`--since/--until` 窗口、`--json` | [timing_view.py](src/content_farm/production/timing_view.py)、[produce.py](scripts/produce.py) |
| runner 寫 `timing.events.jsonl`（run_start/run_end、每次入場排隊秒數）、step 事件帶 lane、每次 run 結束刷新 timing.json | [runner.py](src/content_farm/production/runner.py) |
| 評分卡顯示牆鐘區塊與每輪「同時進行／上限」 | [scorecard_html.py](src/content_farm/review/scorecard_html.py) |
| 評審輪次記 `peak_parallel`、`parallel_allowed`、`parallel_cap`、`arbitration_seconds`、`started_at`（量實際並行數） | [rounds.py](src/content_farm/review/rounds.py) |
| 產出 agent 預設用 stream-json＋trace：每次寫 `<rid>.trace1.json`（工具次數／秒數、模型思考秒數、被拒指令、同檔寫幾次），CallResult 新增 `turns`、`thinking_tokens`、`started_at`；`CF_PRODUCER_TRACE=0` 關閉 | [trace.py](src/content_farm/review/trace.py)、[client.py](src/content_farm/review/client.py)、[producers.py](src/content_farm/review/producers.py) |

🔴 **stream-json 路徑沒有對真的 `claude -p` 驗過**（只有單元測試）。第一次實跑要看 `review/producers/*.trace1.json` 有沒有出來；若 `claude` 回 `stream-json ended without a result event`，設 `CF_PRODUCER_TRACE=0` 退回舊路徑並回報原文。

## 基準對照（`produce.py timing --all`，🟢 可重跑；窗口見上）
| run | 牆鐘 | 機器 | 雲端 | 本機 | 排隊 | 等決定 | 離開 | 退回 | 最大單項 |
|---|---|---|---|---|---|---|---|---|---|
| yokai-kyubi-v2（10-18 15:30→10-19 13:10） | 21h34m | 3h44m | 2h55m | 49m | 42m | 3h12m | 13h50m | 13×1h24m | producer:deck:rework 1h16m |
| cel-ep1-v2（全 run） | 89h17m | 2h03m | 47m | 1h16m | 0 | 3h10m | 82h | 1×13m | voice 40m |
| cowos-final（全 run） | 77h31m | 10h05m | 1h44m | 8h20m | 0 | 5h52m | 59h | 3×56m | mascot 2h54m |
| cel-short | 39m52s | 25m48s | 25m42s | 8s | 14m | 0 | 0 | 2×10m | round:script_structure 11m |
| chipcat-rp4 | 23m11s | 23m10s | 23m10s | 0 | 0 | 0 | 0 | 1×2m | producer:article 11m |
cel／cowos 是評審團之前的 run，產出 agent 與評審紀錄不全，機器時間偏低或偏高皆不可直接比。

**與 REPORT-yokai-tempo 的出入（🟡）**：該報告說 voice「在佇列等 3.3 小時」，但佇列歷史 `history.jsonl` 的 voice start 事件 waited＝0.1 s（12:20:35），且 09:00→12:20 之間無任何 span；較像是「沒人啟動 run」而非機器排隊。帳本把它歸「離開（≥3h）」。另有兩筆真實入場排隊：`policy` 26m22s、13m41s（light 步驟也過入場檢查，見待辦）。

## 離線分析（docs/pipeline-speed/，已 `git add -f`）
- [deck-agent-analysis.md](docs/pipeline-speed/deck-agent-analysis.md)（項目 7）：16 次 deck 呼叫共 6,772 s、69 萬 output token、$31.4；大改 7 次占 81% 時間，思考占 53%；耗時≈output÷108 tok/s（R²=0.97）；寫出 token 是成品 1.3–2.7 倍 → 很可能反覆整檔重寫（推論）；**87 次 Bash 被拒（占 turns 12.4%）**，最多是 python 內嵌 33、自寫腳本 16；16 份 brief 都沒講 Bash 能用什麼；deck-12 一次 673 s／7.6 萬 token 因頻道規則「take 旁白須 ≥80 字」被拒收還原（規則只在被拒後才附進 brief）。
  減半排序：🟢 頻道規則進第一次 brief（此 run 省 11 分）；🟢 brief 講明 Bash 用法並白名單 `apply_deck_patch.py`（5–10 分）；🟡 退回改 `{id:新文字}` patch（大改輪 output −40~43%）；🟡 小改走無工具單輪 JSON（8 次省 12–15 分）；🔴 拆章並行省 29–32 分牆鐘但 token +14~54%。前三項合計估 −52%。
- [reject-list-analysis.md](docs/pipeline-speed/reject-list-analysis.md)（項目 4）：沒有聚合 agent，退回清單是 `routing.plan()` 對每個查證通過的 issue 1:1 轉 fix；各席原始輸出聯集已占 65–73%（每席 12–18 個問題、無上限）；`claim_change=true` 每輪只有 3–7 個問題卻各展開整章，scope 升到 79–95%（連動多出的 118 句只有 8 句真被改）；實際被改 35–54%；只取評審直接點名的 `ref` 是 60–68% 且涵蓋 95–98% 被改句。成片階段觀眾離開點只有 m:ss，程式沒有時間→句子對應，brief 0 個 id。報告內含 prompt／schema／`narrow.py` 守門的 diff 草稿（未套用）。

## 待辦（依預期收益排序；每項要有前後數字）
1. **產出 brief 第一次就附 rubric＋頻道規則＋Bash 用法**（[producers.py](src/content_farm/review/producers.py) `TASKS["deck"]`；rubric 來源 `review/prompts.py`、`channels/shared/review_panels.yaml`、`production/channel_rules.py`）；白名單 `scripts/apply_deck_patch.py`（讀 `{sentence_id: text, deletes: [...]}`，套用後跑 deck_to_script --strict）。量：第一輪通過率、輪數、deck 產出總秒數（基準：16 次 6,772 s）。
2. **退回清單縮窄**：套 reject-list-analysis 的 `simple_scope`（`claim_change` 只展開到投影片）、每席 top-N、`ref.scope=global` 需 `why_global`；成片階段加時間→句子對應。量點名比例 vs 實際改動比例（基準：scope 79–95%、brief 87–96%、實際 35–54%）。
3. **小改快路**（<10% 句）：無工具單輪 agent 只吐 `{id:新文字}`，程式套用。對照 deck-10/11/14 的 30–35 s。
4. **階段並行**：runner 現在嚴格串行（steps.py 順序：…gate_deck_facts → thumbnail_spec → thumbnail → gate_title → voice → illustrate → media…）。要做兩條車道：voice（本機 GPU 獨占）‖ thumbnail_spec→thumbnail→gate_title（雲端）；illustrate 與雲端評審並行；注意 `state` 存檔要合併、`save_state` 非執行緒安全。標題階段只改 thumbnail_spec（a88b8f6），不影響配音；成片評審退回改 deck 仍會讓 voice 重跑（`voice_spoken_key` 只看旁白，已能避免畫面類改動重配）。先讀 `lanes/queue.py` 的 `SLOT_ENV`（父程序持有本機槽時子程序直接放行）。
5. **voice 記憶體宣告**：`channels/shared/heavy_work.json` voice mem_gb 18（REPORT-yokai-tempo 實測上界約 19 GB、典型 8 GB，但機器忙時量的）。要在機器閒置時用 `footprint`／`vmmap --summary` 量 VoxCPM2 worker 與 `voice_retime` 的 whisper large-v3-turbo；現值未改。
6. **配音時機／字數估音長**：先讀 media／assembly／mascot 對 `audio/scene_*.mp3` 與字幕時間的依賴（steps.py：media inputs 含 audio，assembly inputs 含 audio＋srt）；量估計誤差（字數→秒）才能決定可不可行；不可行就在報告說明。
7. **等待清單**：把每次「等人」的原因列表（規則缺口、分類器、環境檔守門、佇列）；light 步驟（policy、thumbnail）也過入場檢查而排隊 26m／13m，應讓 light（mem≤1 GB、無 GPU）步驟略過 starvation 判斷。
8. **觀眾門檻校正**（3 份稿 sonnet vs opus 同 persona 同順序；下限 0.35）、**評審並行上限 8** 實際縮到多少（看新評分卡的 `peak_parallel`）。
9. **驗收**：新片單部實跑（`produce.py run --auto-agents --no-stock --env-file …/.env`，預算 $15，停在 gate_final），之後四頻道同時；用 `produce.py timing` 填前後表。未達標列剩餘瓶頸。

## 進度紀錄（append）
- 2026-10-23 開分支；帳本、回填基準、trace、兩份離線分析完成並 commit；全套 pytest 綠。
- 2026-10-23 對話約 30 萬 token，交接。

## 副作用與清理
- worktree 內：`docs/pipeline-speed/*`（已強制加入 git）；`graft/` 為索引資料夾（ignored）。
- job tmp：`/Users/lileon/.claude/jobs/f924c39e/tmp/`（patch_*.py、analyze*.py，可刪）。未動 `output/`、未 push。
- 子代理：兩個唯讀分析代理已結束。
