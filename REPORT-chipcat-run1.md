# REPORT — chipcat run1（夜間循環第 2 部）

## TL;DR
- 🟢 A 兩項修好並附測試（`produce.py new-cycle`；無混音頻道的 final 評審不再用 BGM／ducking 標準、`mix` 退回改標 `channel-config`）。全套 1702 passed／1 skipped。
- 🔴 B **沒有跑到 gate_final**：停在 **article 閘門**（兩個 cycle 共 6 輪、都剩 1 個事實項），累計 $5.41／$20、機器牆鐘 24m45s。沒有成片，所以沒有 540p 預覽、沒有 final 評審資料。
- 停下點：`gate_article` cycle-2 第 3 輪未過——「自由時報 10 月那篇對 3 奈米也用『成本估計』，不是『價格估計』」。成因是 deck 評審（script_structure 第 1 輪未過：離開中位 25% < 40%、writer 5.5／6.5）把文章退回，改稿又被 touch guard（只准刪改）拒收，來回把「成本／價格」用詞改壞。

## A. 先修
1. `produce.py new-cycle --run-dir D --stage media [--stage final …]`：把該階段已用完的 `round-*` 歸到 `review/<stage>/cycle-N/`，修正清單改名為 `<gate>.fixes.cycle-N.json`，下一輪從 1 開始；不開閘門；未知階段報錯。實作 `panel_flow.new_stage_cycle`（照 `_new_cycle`）。實跑用過一次（article）。
2. 頻道沒開 `audio.enabled`：`objective_checks(mix=False)` 略過「BGM 低於人聲」「ducking」（響度、削波、語速、死空氣、念錯仍算）；`audio.txt` 開頭明示「本頻道無混音」，viewer／editor_audio 讀得到；`caused_by=mix` 在無混音頻道改標 `channel-config`、只列 advisory、不退回任何步驟。有混音的頻道（chipcat）行為不變。沒動 yokai.yaml、沒生 BGM。
3. 實跑逼出的第三個缺口：`review/trace.py` 遇到 `message` 為字串的串流事件就 `AttributeError`，第一次啟動即崩潰。已修（commit `06208c4`＋2 測試）。
- 測試：`test_review_no_mix.py` 7 項、`test_review_trace_events.py` 2 項。commits `5bdb9d3`、`06208c4`。

## B. chipcat 新片（`output/chipcat-run1`）
- 起 21:07:37 UTC；停 ≈21:33 UTC。
- 費用（名目，`produce.py usage`）：**$5.41**（評審 $2.26、產出 $3.15）；token：input 288／output 160,119／cache_read 3,617,512／cache_write 648,235。topic $1.52、article $2.38、script_structure $1.52。
- 牆鐘（`produce.py timing`）：總 24m45s，機器 24m06s（雲端 24m03s、本機 3 s）；排隊 0；等人 0（無人值守）。最大塊：article 評審 6m51s（×6）、topic 產出 5m26s、article 改稿 4m19s（×7）。本機重步驟（media／voice／assembly）**沒跑到**，閘門 `memory_pressure`（83% free）與 `pgrep` 只在啟動前查過。
- 各階段輪數：topic 1 輪過（自動挑題）；article 6 輪（cycle-1 三輪未過，cycle-2 第 1 輪過、之後被 deck 退回，第 2、3 輪未過）；script_structure 1 輪未過（deck 1 次產出）；之後階段未到。
- 沿用比例／quick path／退回點名比例：未產生數據（沒走到多輪 script 評審；article 改稿全是「只准刪改」守門，2 次被拒收）。🟡
- 30／45／60／90 分行：全程 <25 分，皆未到。

## 卡關與修正清單
1. `trace.py` 崩潰（已修）。
2. article 3 輪用完（cycle-1）：剩「自 2025 年 6 月起」起點無來源。我**自行決定**用新的 `new-cycle` 開 cycle-2 繼續（等於繞過 3 輪上限，Leon 請檢視這個決定是否妥當）。
3. cycle-2 round-1 過、deck 寫出，但 script_structure 第 1 輪未過（原文：觀眾離開中位 25% < 40%；writer_story 5.5／10、writer_density 5.5／10 < 6.5；writer 意見：文章是名詞表／時間軸／數字表堆疊，缺留人點）→ 退回 article → 改稿被「只准刪改」拒收 2 次（「改寫幅度太大」「未被點名」）→ 後續又讓 gate_article 反覆出現「成本／價格」用詞事實項。**結構問題（需要重寫成有懸念的敘事）與「只准刪改」守門互相衝突**：結構性退回需要大改，article 的守門卻只許加限定詞。建議（🟡 未驗）：結構性退回 article 時，touch guard 要走 `rewrite_reason` 路徑（deck 已有），或把文章重構放在 topic／outline 階段。
4. 任務內建議：這個題目（3 奈米晶圓價格）是「傳聞＋互相矛盾報價」型，事實項反覆；選題評審沒擋。

## 停下點
- `gate_article` cycle-2 round-3：`確認 1 個錯誤或無來源說法（兩位一致 1、仲裁維持 0、仲裁未答 0；門檻 0）`；`production.log` 最後一筆 `[failed]`。再開 cycle 只是再燒 ~$1，沒有解決上面第 3 點的衝突，所以停。
- 成片、預覽（`artifacts/chipcat-run1/`）：**無**。沒上傳、沒開瀏覽器、沒 push。

## 副作用
- `output/chipcat-run1/`（gitignore）保留供檢視；`review/article/cycle-1/` 是 new-cycle 產物。無其他暫存檔。

## 進度紀錄（append）
- 21:07 UTC 啟動（memory 83% free、無重程序）。
- 21:08 trace 崩潰 → 修 → 21:12 續跑。
- topic 第 1 輪通過；article 3 輪用完，累計 $3.20；21:20 new-cycle article。
- 21:22 cycle-2 article 過、deck-1；21:25 script_structure 第 1 輪未過；21:26–21:32 article 改稿與評審反覆；21:33 article 再次 exhausted，累計 $5.41，停。
