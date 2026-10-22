# REPORT — pipeline 計時與加速（feat/pipeline-speed）

分支 `feat/pipeline-speed`，從 `feat/cost-fix`（3257f14）開。沒有 push、沒開瀏覽器、沒上傳、沒用付費服務；沒有跑過任何 `claude -p`（本 session 的 Bash 拒絕直接呼叫 `claude`，驗收實跑要走 `produce.py run --auto-agents`）。

## TL;DR
🟡 **計時帳本、基準、兩份離線分析做完（commit 5b84533）；第二段已做待辦 1–3 的程式與離線重放（見〈第二段〉），驗收實跑與待辦 4–9 還沒做。** 第二段數字全是離線推估，brief 點名 87–96% → 32–46%、小改 2/5 走快路；代價是第一輪涵蓋率 45–66%，要實跑確認輪數沒變多。
- 基準（九尾狐，Leon 的窗口 10-18 15:30→10-19 13:10 UTC）：牆鐘 21h34m；機器時間 3h44m（雲端 2h55m／本機 49m）；排隊 42m；等決定 3h12m；離開（≥3h）13h50m；退回造成的產出重寫 13 次 1h24m。與 Leon 給的 1,295／231 分吻合。
- 機器時間 3h44m 要降到 30 分，最大塊依序：deck 產出重寫、voice、評審輪次、media。

### 第二段更新（2026-10-23，待辦 1–3 程式與離線重放完成；仍未實跑）
🟡 三項都已寫成程式並有測試（pytest 1689 passed，比基準 1653 多 36 個新測試；另有 1 個**事前就存在**的失敗 `test_multi_provider.py::test_returns_first_provider_results`，在 `cf-pipeline-speed` 原分支同樣失敗，與本次無關）。**所有「後」的數字是離線推估（🟡）**，沒跑 `claude -p`；實跑才算數的項目列在〈第二段〉末尾。
- 1 brief 第一次就帶 rubric＋頻道規則＋Bash 用法；新白名單 `apply_deck_patch.py`。
- 2 退回清單：九尾狐 5 輪離線重放，brief 點名 87–96% → 32–46%，scope 79–95% → 30–44%，brief 字數 −43~−63%；代價是涵蓋「實際被改句」100% → 45–66%（見下）。
- 3 小改快路：九尾狐小改 5 次中 2 次（deck-6、deck-7，原 292 s／133 s）符合條件，預估 9–21 s。

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

## 第二段：待辦 1–3 的實作與前後數字（worktree `cf-pipeline-speed-2`，分支 `worktree-cf-pipeline-speed-2`，從 `feat/pipeline-speed` 2fa8940 快轉）

重放腳本（可重跑，🟢）：[replay_narrow.py](docs/pipeline-speed/replay/replay_narrow.py)（項目 2，`PER_SEAT=… HARD=…` 可調）、[replay_brief.py](docs/pipeline-speed/replay/replay_brief.py)（項目 1／2 brief 與項目 3 資格）。資料：`cf-yokai-tempo/output/yokai-kyubi-v2/review/`；用 `/Users/lileon/project/content-farm/.venv/bin/python <腳本>` 執行。重放用的「前」基準與前一段報告一致（實際被改 49/41/54/43/35%、scope 82/95/92/90/79%、ref 60/67/64/67/68%），代表重放方法有效。

### 項目 1：brief 第一次就附規則（改了哪些檔）
- [brief.py](src/content_farm/review/brief.py)（新）：`rubric_text`（取 `script_structure` 席次的 pro 角色 rubric＋過關門檻 writer_min／leave_median）、`channel_rules_text`（開場／結尾口頭禪、take ≥ `MIN_TAKE_CHARS`=80 字、吉祥物占比、不得出現他頻道口頭禪；數值直接讀 `channel_rules.py` 常數，不是複製）、`bash_text`（只列兩支腳本的完整寫法、禁止 cd／env -C／-I／串接／heredoc）。
- [deck_patch.py](src/content_farm/review/deck_patch.py)（新）＋ [apply_deck_patch.py](scripts/apply_deck_patch.py)（新）：吃 `{句子id: 新文字, "deletes": [id]}`，只動被點名句子，未知 id／空文字／同時改又刪／sentence_ids 與旁白對不上就整份拒絕且 deck.json 不動；套完跑 `deck_to_script --strict`。
- [producers.py](src/content_farm/review/producers.py)：`SCRIPTS` 加入 `apply_deck_patch.py`；`produce()` 對 `deck` 步驟（初稿與退回）把 `deck_brief` 放在任務文字之後。初稿帶 rubric；退回只帶規則＋Bash（退回是 diff，清單已說明要改什麼，而且 `test_the_rework_brief_is_a_diff_not_a_redo` 守著 brief 不要膨脹，上限由 +1500 調為 +2200 字並註明原因）。
- 前後（🟡 推估）：deck-12 因 take 73 字 < 80 被拒收還原，耗 673 s／75.9k token（占該 run 11.2 分、output 11.0%）；規則現在在第一次 brief 裡，但「agent 會不會照做」要實跑才知道。87 次被拒 Bash（占 turns 12.4%、被拒指令占 output 4.8–6.4%）：brief 現在寫明唯一可用寫法＋合法的程式化改檔途徑，預期趨近 0，要看 `trace1.json` 的 denied 欄位確認。第一輪通過率、輪數、deck 產出總秒數（基準：16 次 6,772 s）**只能實跑量**。

### 項目 2：退回清單縮窄（改了哪些檔）
- [narrow.py](src/content_farm/review/narrow.py)（新，確定性、不呼叫 LLM）：每席最多 `PER_SEAT=5` 條；排序＝事實優先 → 嚴重度 → 被幾席共同點名 → 句數少者優先；點名句子聯集超過 `HARD_SHARE=0.30`×總句數就把剩下的 issue 擱置到 `deferred`（寫進 `*.fixes.json` 的 `deferred`，下一輪評審若仍點名會再進來）；`ref.scope="global"` 且附 `why_global` 的、不點名句子的（標題／素材／影片時間）issue 不受限；`narrowing` 欄位寫進 fixes（`named_share_before/after`、`over_warn`＞25%）。`CF_REVIEW_NARROW=0` 關閉（前後對照用）。另含 `sentences_at`／`with_sentences_from_time`。
- [gate.py](src/content_farm/review/gate.py) `_rework()`：`routing.plan()` 前呼叫 narrow。
- [routing.py](src/content_farm/review/routing.py) `simple_scope`：`claim_change` 只展開到被點名句子所在**投影片**（＋`affected_slides` 最多 3 張）；整章仍回送複審（`chapters` 不變）；出現在 > 6 句的常見詞不再當連動詞。
- [schemas.py](src/content_farm/review/schemas.py)：issue 新增 `ref.scope`／`ref.why_global`／`affected_slides`；`validate()` 支援 `maxItems`／`minItems`（目前只在測試用，沒有把上限寫進評審 schema，避免違規時 schema 重試多花錢——超出由 narrow 裁切）。
- [prompts.py](src/content_farm/review/prompts.py)：RULES 加「只列不改就會流失／誤導／事實錯的」「每席 ≤8 題、觀眾 ≤3」「每題 ≤4 句」「講稿類一定要有 sentence_ids，全片性才用 scope=global＋why_global」「claim_change 要填 affected_slides」；觀眾離開點必須是第一條 fix 的第一個 id。
- [verdicts.py](src/content_farm/review/verdicts.py)：`verify_issue` 對 `target=script` 沒有句子 id 又不是 global 的 issue 丟掉（reason 寫進 dropped）；`final()` 用 `sentence_times` 把 video／audio issue 的 `ref.t` 換成「該秒所在句 ±1 句」寫進 `ref.sentence_ids`（取代觀眾自填的數字 id）。[materials_video.py](src/content_farm/review/materials_video.py) 新增 `sentence_times()`（`retention.timing.sentence_timeline` × `deck_sentences`，句數對不上就回 []，行為退回舊樣子）。

**離線重放（deck-1..5＝九尾狐講稿結構退回；分母＝被評審那一版句子數；🟢 可重跑，但「新」是推估，因評審 prompt 也變了、真評審的 issue 會不同）**

| 指標 | deck-1 | deck-2 | deck-3 | deck-4 | deck-5 | 備註 |
|---|---|---|---|---|---|---|
| 實際被改（基準） | 49% | 41% | 54% | 43% | 35% | 同前一段 |
| issue 數 前→後 | 88→29 | 67→28 | 50→20 | 65→29 | 58→27 | |
| 評審點名（ref）前→後 | 60%→22% | 67%→29% | 64%→30% | 67%→30% | 68%→29% | |
| **連動 scope 前→後** | 82%→30% | 95%→37% | 92%→44% | 90%→32% | 79%→37% | 基準 79–95% |
| **brief 不同 id 前→後** | 89%→32% | 96%→38% | 92%→46% | 94%→35% | 87%→39% | 基準 87–96% |
| brief 字數 前→後 | 26,800→9,991 | 21,745→10,895 | 18,340→9,240 | 20,940→11,437 | 19,990→11,372 | 後＝新退回 brief（含項目 1 的規則＋Bash 區塊） |
| 預期 output token（比例推估 🟡） | 59.6k→21.7k | 79.5k→31.8k | 92.2k→46.6k | 109.2k→41.1k | 88.7k→39.6k | 假設 output ∝ brief 點名句數；只是上界式推算 |
| 「實際被改的句子」仍在 scope 內 | 100%→45% | 100%→66% | 100%→59% | 100%→52% | 100%→64% | **代價**：被擱置的 issue 要靠下一輪補回 |
| scope 內真的被改的比例（precision） | 60%→73% | 44%→73% | 59%→72% | 47%→69% | 45%→61% | |

- 取捨很明確：點名比例壓到 32–46%（≈ 實際被改的 35–54%），代價是第一輪涵蓋率只剩 45–66%（producer 先前會把清單全改，所以涵蓋率不等於品質損失，但**輪數有可能增加**——這正是要實跑驗收的點）。
- 參數敏感度（同一批資料，🟢）：`PER_SEAT=8 HARD=0.4` → scope 43–57%、涵蓋 49–85%；`PER_SEAT=99 HARD=0.5` → scope 56–64%、涵蓋 78–90%。預設取報告建議的「每席 5、硬上限 30%」；若實跑輪數明顯變多，先把 `HARD_SHARE` 放到 0.40。常數在 [narrow.py](src/content_farm/review/narrow.py) 頂端。
- **要實跑才算數**：prompt 的新規則（每題 ≤4 句、scope=global）評審會不會照做；`verify_issue` 丟掉的「沒有句子 id」issue 會不會造成評審退回後沒東西改（此時 `_rework` 會合成無 id 的 open 計畫，行為同舊版）；成片階段 `sentence_times` 在真影片上的對齊（單元測試只有人工時間表）；輪數與離開比例有沒有變差。
- 成片階段 deck-12/13 的基準是「brief 內 0 個 id，但 deck 被改 36 句、新增 25 句」。新版成片 issue 會帶 id（±1 句）→ 守門變成「只能動這些句」；若成片退回確實需要新增句子，會被 touch guard 拒收（原本是 `open` 計畫允許）。這是刻意取捨，第一次實跑要看 `*.fixes.json` 的 `narrowing`／`deferred` 與是否被拒收。

### 項目 3：小改快路（改了哪些檔）
- [quick_patch.py](src/content_farm/review/quick_patch.py)（新）：符合 `eligibility` 才走——每條 fix 都有句子 id、點名句 < 10%（且 ≤ 14 句）、不是 prompt_only／標題／縮圖／說明欄、fix 文字沒有「補/找來源」「新增句／投影片」「拆」「移到…之前之後」、不是 rerouted。無工具單輪（`Call(tools=())`，`--tools ""`，不帶 `--allowed-tools`）只輸出 `{replace:{id:新文字}, deletes:[…], summary, needs_tools}`；程式用 `deck_patch.apply_patch` 套用，再跑 `deck_to_script --strict`；**任何一步不成立（資格不符、呼叫失敗、答案 needs_tools、改了未點名的句子、套用失敗、lint 失敗）→ 還原 deck.json、回到原本的有工具 agent**。touch guard 與頻道規則檢查照舊在後面把關。`CF_QUICK_PATCH=0` 關閉。
- [producers.py](src/content_farm/review/producers.py) `_quick()`：成功時回傳的 CallResult 照樣寫進 `producers.jsonl`（`quick:true`、`quick_ok`、`quick_why`，費用與 token 照算）；資格不符沒有呼叫，所以原因寫在獨立的 `review/producers/quick.jsonl`（避免污染成本／預算讀的 `producers.jsonl`）。[client.py](src/content_farm/review/client.py) `argv_for`：`tools=()` 時不傳 `--allowed-tools`。
- 離線重放（九尾狐 script_facts 各輪的真 issue，🟡 時間為模型推估＝首 token 3.3 s ＋ (patch＋300~1500 思考 token)/108 tok/s ＋ 1 s 套用）：

| 呼叫 | 點名句 | 資格 | 實測 | 預估快路 |
|---|---|---|---|---|
| deck-6（事實段 r1） | 8/126 = 6% | ✅ | 292 s／24.5k tok | 10–21 s／約 0.6–1.8k tok |
| deck-7（事實段 r2） | 6/126 = 5% | ✅ | 133 s／13.1k tok | 9–20 s／約 0.5–1.7k tok |
| deck-14 | 7/114 = 6% | ❌ fix 含「移到…之前」 | 35 s | 走原路徑 |
| deck-15／16 | 9/114 = 8% | ❌ 同上 | 54 s／153 s | 走原路徑 |
| deck-10／11 | 0 句（只改 media.prompt） | ❌ prompt_only，不是旁白 | 30／34 s | 走原路徑（任務原文把它們當對照；它們不屬旁白小改，這次沒做 media.prompt 的快路） |

  所以 5 次小改裡只有 deck-6、deck-7 走快路，**預估省 (292+133) − (19~42) ≈ 6.5~7 分鐘**；比任務原先對照的「30–35 s」少，因為 deck-10/11/14 本身就不屬於或不符合條件。deck-14/15/16 因為一條「刪除或移到…前」的 fix 被判不符；若放寬成「有替代方案時視為可做」會多省約 1.5 分，沒做（保守）。
- **要實跑才算數**：(a) `claude -p --tools ""`（無工具）能不能正常回 `--json-schema` 結構化輸出——🔴 沒對真的 claude 驗過；失敗時 `quick_deck` 回傳呼叫失敗並**自動退回有工具 agent**，最壞多花一次便宜的呼叫，看 `producers.jsonl` 的 `quick_ok:false` 與 `quick_why`。(b) 實際單輪耗時與 patch 品質（`strict` lint、touch guard 拒收率）。(c) 資格正則（`_NEEDS_TOOLS`）對別的 run 的誤判率；目前只對九尾狐 5 輪驗過。

### 第二段留下的事（給下一段）
- 驗收實跑時第一件事：看 `review/producers/*.trace1.json` 有沒有出來（stream-json 路徑仍是 🔴）；失敗就 `CF_PRODUCER_TRACE=0`。新增三個關閉開關便於 A/B：`CF_REVIEW_NARROW=0`、`CF_QUICK_PATCH=0`、`CF_PRODUCER_TRACE=0`。
- 「合併共用 id 的 issue」（報告建議的確定性去重）沒做，也沒量。
- `media.prompt` 的小改快路（deck-10/11 類）沒做。

## 待辦（依預期收益排序；每項要有前後數字；1–3 已在第二段完成，4–9 原樣保留）
1. ✅（程式＋離線重放完成，見〈第二段〉；實跑數字待驗收）**產出 brief 第一次就附 rubric＋頻道規則＋Bash 用法**（[producers.py](src/content_farm/review/producers.py) `TASKS["deck"]`；rubric 來源 `review/prompts.py`、`channels/shared/review_panels.yaml`、`production/channel_rules.py`）；白名單 `scripts/apply_deck_patch.py`（讀 `{sentence_id: text, deletes: [...]}`，套用後跑 deck_to_script --strict）。量：第一輪通過率、輪數、deck 產出總秒數（基準：16 次 6,772 s）。
2. ✅（同上）**退回清單縮窄**：套 reject-list-analysis 的 `simple_scope`（`claim_change` 只展開到投影片）、每席 top-N、`ref.scope=global` 需 `why_global`；成片階段加時間→句子對應。量點名比例 vs 實際改動比例（基準：scope 79–95%、brief 87–96%、實際 35–54%）。
3. ✅（同上；九尾狐 5 次小改只有 2 次符合資格）**小改快路**（<10% 句）：無工具單輪 agent 只吐 `{id:新文字}`，程式套用。對照 deck-10/11/14 的 30–35 s。
4. **階段並行**：runner 現在嚴格串行（steps.py 順序：…gate_deck_facts → thumbnail_spec → thumbnail → gate_title → voice → illustrate → media…）。要做兩條車道：voice（本機 GPU 獨占）‖ thumbnail_spec→thumbnail→gate_title（雲端）；illustrate 與雲端評審並行；注意 `state` 存檔要合併、`save_state` 非執行緒安全。標題階段只改 thumbnail_spec（a88b8f6），不影響配音；成片評審退回改 deck 仍會讓 voice 重跑（`voice_spoken_key` 只看旁白，已能避免畫面類改動重配）。先讀 `lanes/queue.py` 的 `SLOT_ENV`（父程序持有本機槽時子程序直接放行）。
5. **voice 記憶體宣告**：`channels/shared/heavy_work.json` voice mem_gb 18（REPORT-yokai-tempo 實測上界約 19 GB、典型 8 GB，但機器忙時量的）。要在機器閒置時用 `footprint`／`vmmap --summary` 量 VoxCPM2 worker 與 `voice_retime` 的 whisper large-v3-turbo；現值未改。
6. **配音時機／字數估音長**：先讀 media／assembly／mascot 對 `audio/scene_*.mp3` 與字幕時間的依賴（steps.py：media inputs 含 audio，assembly inputs 含 audio＋srt）；量估計誤差（字數→秒）才能決定可不可行；不可行就在報告說明。
7. **等待清單**：把每次「等人」的原因列表（規則缺口、分類器、環境檔守門、佇列）；light 步驟（policy、thumbnail）也過入場檢查而排隊 26m／13m，應讓 light（mem≤1 GB、無 GPU）步驟略過 starvation 判斷。
8. **觀眾門檻校正**（3 份稿 sonnet vs opus 同 persona 同順序；下限 0.35）、**評審並行上限 8** 實際縮到多少（看新評分卡的 `peak_parallel`）。
9. **驗收**：新片單部實跑（`produce.py run --auto-agents --no-stock --env-file …/.env`，預算 $15，停在 gate_final），之後四頻道同時；用 `produce.py timing` 填前後表。未達標列剩餘瓶頸。

## 進度紀錄（append）
- 2026-10-23 開分支；帳本、回填基準、trace、兩份離線分析完成並 commit；全套 pytest 綠。
- 2026-10-23 對話約 30 萬 token，交接。
- 2026-10-23 第二段（新 session）：待辦 1–3 實作＋測試＋離線重放完成並 commit（1689 passed、1 個事前就存在的失敗）。待辦 4–9 未動。
- 下一段建議：先做 9 的單部實跑驗收（看 trace1.json、quick.jsonl、fixes 的 narrowing），再依結果決定 4（階段並行）。

## 副作用與清理
- worktree 內：`docs/pipeline-speed/*`（已強制加入 git）；`graft/` 為索引資料夾（ignored）。
- job tmp：`/Users/lileon/.claude/jobs/f924c39e/tmp/`（patch_*.py、analyze*.py，可刪）。未動 `output/`、未 push。
- 子代理：兩個唯讀分析代理已結束。
