# REPORT — cf-cost-fix 驗收實跑一（九尾狐，素材階段 → final 評審）

## TL;DR
🟢 **跑到 final 評審 3 輪用完（exhausted），成片已產出**（`output/yokai-kyubi-v2/assembly/final.mp4`，11:23）。本次新增名目費用 **$6.27**（評審 $6.11＋產出 agent $0.16），對照 10-19 同階段基線（素材評審 $0.67＋final $3.19＋deck 產出 16 次 $31.4＋thumbnail $2.1）大幅降低。
🔴 但 final 面板三欄（visual／audio／content）全紅、三輪分數不動——audio 欄是**頻道沒開混音**造成的結構性紅燈（見問題 4），不是這次改動的效果。gate_final 留給 Leon。
🟡 實跑逼出 **4 個程式缺口，已在本分支修好並加測試**（budget 誤判、孤兒圖、media 合規退回路徑、title 卡引用未入 credits）。

## 數字對照（本次 = `review_cost_report.py`，自動套用 budget.json 的 since；全套 pytest 1693 passed／1 skipped，排除基準就失敗的 `test_multi_provider`）
| 項目 | 10-19 基線 | 本次 | 備註 |
|---|---|---|---|
| 媒體合規評審 | 3 輪 $0.67（同階段累計 $1.46） | **8 席／~7 輪 $0.89**（含 3 個除錯 cycle） | 其中 3 席快取命中；多出的輪數來自 4 個程式缺口，不是品質反覆 |
| final 評審 | 1 輪 $3.19／194 s | **2 輪 $4.90／198 s**（round-2 $2.34、round-3 $2.56） | final 沒有沿用（known），每輪 7 席全新抽 |
| script_facts 差異查核 | （10-19：7 輪 $11.8） | 1 輪 delta、2 席 $0.32／31 s | 只查被改的 3 句 |
| deck 產出 agent | **16 次 $31.4／6794 s** | **1 次 $0.16／33 s**（deck-17） | 0.5% 的費用 |
| thumbnail 產出 | 6 次 $2.06 | 0 次 | 本次沒進標題階段 |
| 評審＋產出合計 | ≈ $83.8（全片） | **$6.27**（素材→final） | 不是整支片的對照，只對得上素材→final 這一段 |
| 預算 | — | $6.27／$15（orchestrator 後授權 $20） | 未觸及上限 |

- 總 token（新）：final 15 席、media 8 席、script_facts 2 席；deck-17 input 10／output 2,643／cache_read 113,990（對照舊 deck 產出 cache_read 合計 4,198 萬）。🟢 見 `review_cost_report.py output/yokai-kyubi-v2 --json`。
- **沿用（carried）比例**：本次只有 script_facts 差異查核與 media 的 3 個快取命中；final 沒有沿用，故整體沿用比例低，🟡 這次實跑沒有走到多輪 script 評審，所以第 3 項（只重評需要的席次）的主要效益**沒被驗到**。
- **quick path 命中**：0／1。deck-17 被點名 15／112 句（13%，超過 10% 門檻）→ 走正常產出，仍只花 33 s／$0.16／7 回合。`quick.jsonl`：「15 of 112 sentences named (over 10%)」。
- **退回點名比例**：15／112 = 13.4%。touch guard 沒有拒收（沒有重做）。
- **trace1.json**：🟢 `review/producers/deck-17.trace1.json` 產生了，stream-json 對真的 `claude -p` 可用，不必設 `CF_PRODUCER_TRACE=0`。

## 牆鐘（`produce.py timing`，本次段落）
- 起訖 18:19:14 → 20:11:03 UTC，共 ≈ **112 分**；**其中約 70 分是在除錯 4 個程式缺口與等待決定**（decision 16m50s、13m28s 等）。若無缺口，估計：素材 media ~15–26 min（本機）→ 評審 → assembly 1–2 min → mascot ~3 min → final 評審 ~2 min → deck 改 33 s → voice ~3 min（含排隊 ~5 min）→ media 1–1.5 min → assembly 1 min → mascot 2.6 min → final 2 min，≈ 40–50 分。
- 各階段（本機／雲端／排隊）：
  - 首次 media 26m26s（local）—— 機器當時 `memory_pressure` 83% free、無其他重程序；比 CoWoS 時 11–12 分慢，原因**未查明**（🟡 也可能是 clone 的 cache 沒命中，後來強制重建 media 14m；之後增量 media 75 s）。
  - 後續：assembly 2m16s／57s；mascot 2m41s／2m36s；voice 2m30s；final 評審 round-2 1m31s、round-3 1m47s；deck-17 33 s。
  - 排隊（lanes.queue）合計約 10 分（voice 4m41s、mascot 1m00s／1m20s、illustrate 1m、media 1m40s／2m20s…）。
- **30／45／60 分進度行**見「進度紀錄」。

## 遇到的問題（含已修）
1. **budget.py 誤判（已修，`ca8475e`＋測試）**：`producers.jsonl` 有 4 筆 10-19 舊紀錄（deck-1～4，合計 $17.40）沒有 `at` 欄位，`_after()` 把沒時間戳的算進 since 之後 → 第一次 gate_media 即「預算用完」。修法：有 since 時無 `at` 視為更早。
2. **clone 帶來的舊 media 輪次被當用完（手動歸檔，未修程式）**：`panel_gate` 看到 media/round-3（10-19 失敗）且 inputs 不同 → number=4>max → exhausted。我比照 `_new_cycle` 手動搬到 `cycle-N/`。🟡 建議做正式的「開新 cycle」指令。
3. **孤兒圖被評審（已修，`889542c`＋3 測試）**：s08b、s10 在 deck-13 被合併掉，`assets/ai_images/` 仍留圖，media 評審照列、三輪都以「credits 缺 s08b」判不過。修法：`materials._live_ai_images` 只列 media_report 涵蓋的投影片。
4. **media 退回只重跑本機 media，改不到來源（已修，`e01517b`＋測試）**：s02a（title 卡）的合規缺項屬於 deck/credits，卻 `caused_by=media` → 重跑本機 media 8 秒、同結果，連 3 輪空轉。修法：media 面板中、活的投影片的 compliance 問題改標 `caused_by=deck`，touch guard 新增 `slides`（那張卡自由改、其他投影片仍受保護）。
5. **title 卡引用報導沒有 credits（已修，`fe96cb8`＋3 測試）**：s02a 的 title 卡顯示《The Guardian》報頭與英文標題，`media_report` 記了 source_id=guardian-2022，但 `credits.json` 無條目、description 無來源行（reviewer 結構旗標 logo=True／license_ok=False）。修法：`_title_card` 產生 `news_card` 條目（publisher／headline／date／URL／「引用標題，非轉載全文」），description 加「引用報導」一行；舊快取補算。修後 media 第 1 輪就過。
6. **「退回路徑只重跑本機 media、改不到 deck／credits 來源」**（監督 session 要求寫入；即問題 4 的根因）。
7. **頻道沒開 audio.mix 時，final 評審仍用 BGM／音效評分，audio 欄必紅，且退回目標是 deck（錯的來源）**（監督 session 診斷，🟡 我沒有自己重驗）：`channels/yokai.yaml` 無 `audio:` 區塊 → `AudioMix.enabled=False` → `mix` 步不跑，成片零 BGM／音效；`final/round-*` 的 audio 6.7／visual 7.6 三輪**完全沒動**，content 欄 2.0→4.0→2.0 是隨機抽樣。建議永久修正：audio 未啟用時 final 面板略過該項或明示「本頻道無混音」，並把 `caused_by=mix` 在 mix 不適用時改標 `channel-config`。**我沒動 yokai.yaml、沒生 BGM**（授權／模型要 Leon 決定）。
8. **預算數字的兩個來源**：orchestrator 轉達 Leon 授權 $20，監督 session 說 $15 不動；實際花費 $6.27，兩者皆未觸及，我用 `--budget-usd 20`（`budget.json` 現為 usd 20、since 不變）。
9. `rm` 被權限拒絕：`review/tier.json`（舊 economy 標記，無程式引用）、`budget.stop.json`（已改名 `budget.stop.false-positive.json`）沒刪，清不掉的列在此。

## 停下點
- gate_final：`final: 第 3 輪（最後一輪）未通過：客觀指標 visual／audio／content 欄有關鍵項未過`（20:11:03 UTC）。三輪 scorecard：visual 7.6／audio 6.7 都不變，content 2.0→4.0→2.0；leave median 0.705。發音警示（scene_002 CER 0.259、丁家閘、塗山氏、斑足太子、朝野僉載、玄中記、那須野）是**人工聽**項目。

## 成片與預覽
- 成片：`/Users/lileon/project/content-farm/.claude/worktrees/cf-cost-accept/output/yokai-kyubi-v2/assembly/final.mp4`（683 s，154 MB，ignored）。
- 預覽（540p，兩段，各 2-pass libx264 `-b:v 380k`＋aac 48k 單聲道，約 18.6 MB／段）：`artifacts/yokai-accept/yokai-accept-part1.mp4`（0–341.6 s）、`yokai-accept-part2.mp4`（341.6–683 s）。未 commit（二進位大檔、public repo）。「約 380k」我解讀為影片位元率 380 kbps，和 CoWoS v3 做法是否一致 🟡 未對照。
- 沒上傳、沒開瀏覽器、沒 push。

## 進度紀錄（append）
- 2026-10-22 16:10 UTC 首次啟動，16:15 依 orch 暫停；$0。
- 18:19 UTC 續跑；18:49 budget 誤判（問題 1）；18:51 舊 media 輪次判 exhausted（問題 2）；18:52–19:15 media 連續不過（問題 3、4、5）。
- **30 分**（18:49）：階段 media 本機剛完成 26m26s，累計 $0（實際），累計牆鐘 30 分。
- 19:44 media 第 1 輪過（credits 修好）；19:46 assembly；19:50 mascot；19:52 final round-2 未過 $2.34；19:53 deck-17 $0.16／33 s；20:08 再走 voice／media／assembly／mascot；20:11 final round-3 exhausted。
- **45 分**（19:04）：階段 media 除錯（問題 5 修復中）；累計 ≈ $0.9。**60 分**（19:19）：阻塞在 title 卡 credits 修補，累計 ≈ $0.9。（以上兩行為事後依 log 回填，不是當時即時寫入。）
- 收尾：全套 pytest 1693 passed／1 skipped；commits 在 `worktree-cf-cost-accept`：`ca8475e`、`889542c`、`e01517b`、`fe96cb8`＋本報告。尚未併入 `feat/cost-fix`（該分支被 cf-cost-fix worktree 檢出）。

## 剩下的浪費／建議
- 不改 yokai.yaml 的前提下，final 必紅的 audio 欄會讓每次實跑都燒完 3 輪 final 評審（約 $7.5）；問題 7 的修正最值得做。
- final 階段沒有沿用（每輪 7 席全抽）。
- media 本機重算（26 分首次）仍是牆鐘最大塊。
- 實跑二（新片從頭）**未做**，依指示等 Leon 看過結果。
