# REPORT — 九尾狐開台片 tempo 1.20 → 1.29（決策 40e6b445a7ed）

## TL;DR
- 🔴 **（2026-10-19 最新）照 7afa95870a4e＝A 改走兩段制，結構段 3 輪也沒過，停在 gate_deck**：編劇分數在 6.3–7.1 來回；第 3 輪觀眾離開中位 49.6%（門檻 50%），編劇 6.8／6.8（門檻 7）。事實段沒有跑。
  - 到現在兩套腳本評審共 6 輪，產出 agent 重寫 4 次，都沒有收斂。
  - 沒有片長、QC 或 preview。需要 Leon 決定，見「兩段制」一節。
- 🔴 **（2026-10-19 最新）停在第 3 步（腳本評審）**：選項 A 加了青蛙書記、走新評審流程。腳本評審 3 輪都沒過：查核錯誤 15 → 6 → 3，編劇分數 7.2／7.0 第 3 輪才過。最後只剩 3 條「無來源／超出來源」的錯誤（s24.4、s24a.7、s26.3），所以沒有片長、QC 或 preview。下一步要 Leon 或 orchestrator 決定，見「第 3 步評分卡」。
- （以下是第一次停下時的紀錄）
- 🔴 **前提失效，已停下**：`produce.py run` 在第一個步驟 `policy` 就失敗：`青蛙書記 on 0/29 slides (>= 80%)`。配音、media、assembly 都還沒跑。
- 原因：`feat/incremental-render` 帶進了 `design/channel-hosts`（d95ee3e，Leon 10-17 選的 Y14 青蛙書記，`rig_ready: true`）。這條規則要求 ≥80% 投影片有主持角色。launch 版的 run-dir 是在 `feat/channel-voices` 上做的，那條分支沒有這個 commit，所以 deck 裡 `mascot` 是 0/29。
- 要繼續就得**在 deck 裡加角色**（這是內容變更，要重審 gate_deck，還要新跑 mascot 疊加），已經超出「只改語速」的範圍。下面列了三個選項，等 Leon 決定。
- 已完成：yokai tempo 改成 1.29（只改這個頻道），測試跟著改。run-dir 複製到 `output/yokai-kyubi-v2`，音檔沒動過（`tempo.json` 仍然 29×1.2）。

## 第 3 步兩段制：結構段 3 輪也沒過（2026-10-18 16:1x–17:10 UTC）🟢
`review/script_structure/round-{1,2,3}/scorecard.json`。門檻：離開中位 ≥50%、兩位編劇都 ≥7。查核在這一段只列出、不擋。

| 輪 | 牆鐘／名目 | 離開中位（4 位） | 編劇 故事／密度 | 導演 | 未過原因 |
|---|---|---|---|---|---|
| 1 | 298.5 s／$3.11 | 72.7% | 6.4／6.5 | 6.3 | 兩位編劇 |
| 2 | 395.9 s／$3.13 | 70.7% | 7.1／**6.3** | 6.4 | 密度 |
| 3 | 435.5 s／$3.44 | **49.6%**（holdout 41.9%） | 6.8／6.8 | 6.5 | 觀眾＋兩位編劇 |

- 產出 agent 兩次重寫：882.6 s／$4.57、1002.7 s／$5.26。結構段牆鐘約 55 分鐘，名目約 $19.5（訂閱）。
- **結構段起點就沒過**：orchestrator 預期「單段第 3 輪的 65.6%／7.2／7.0 已達門檻」，但結構段第 1 輪是新的評審，兩位編劇給 6.4／6.5，沒有沿用舊分數。三輪之間編劇分數在 6.3–7.1 來回，第 3 輪的觀眾反而掉到 49.6%。重寫沒有讓分數穩定往上 🟡。
- 錯誤訊息顯示「觀眾離開中位 50% < 50%」，實際值是 0.496，只是四捨五入後看起來像相等。這是顯示問題，沒有影響判定。
- 結構段查核另外列了 8 條事實項（只列不擋）：s01.12「同一個時代」、s17.13 清代冊頁、s14.16 宋代拆廟、s21a 斑足／班足、s19.9 玉藻前被射殺、s20.9 能面、s15.2 封神演義成書年代、s16.10。原本的 s24.4、s26.3 已經不在清單上；s24a.7／s24a.9 被判為常識、風險低。
- 事實段（`gate_deck_facts`）沒有跑，因為結構段沒過，事實段就不跑。

**article.md 和講稿不同步的地方**（說明欄要以講稿為準；article 凍結沒改）：第九十六回／第九十七回、「三千年」應為「兩千多年」、郭璞是晉代人不是漢代、《繪本三國妖婦傳》的巡迴順序、「北齋一派」（大都會標 School of Katsushika Hokusai）、thepaper-2018 是澎湃文化專欄不是學者著作。

**待決定**：照規則停在結構段，沒有 override、沒有動門檻。

## 第 3 步評分卡（單段制，`output/yokai-kyubi-v2/review/script/round-{1,2,3}/scorecard.json`）🟢
| 輪 | 評審牆鐘／名目 | 觀眾離開中位（4 位） | 編劇 故事／密度 | 導演 | 查核錯誤 | 結果 |
|---|---|---|---|---|---|---|
| 1 | 283.6 s／$2.81 | 57.8% | 6.5／6.3 | 6.0 | 15 | 退回 deck |
| 2 | 339.1 s／$3.19 | 72.7% | 7.3／6.8 | 6.4 | 6 | 退回 deck（article 凍結，改派） |
| 3 | 389.9 s／$3.09 | 65.6%（holdout 54.4%） | 7.2／7.0 | 5.8 | **3** | **最後一輪未過** |

- 產出 agent（opus·high）：第 1 次重寫 652.6 s／名目 $3.39，第 2 次 835.5 s／$4.18。slides 每次約 11 s。
- 從 15:3x 到 16:16 UTC，牆鐘約 45 分鐘。名目費用合計約 $16.7，走 `claude -p` 訂閱，不是按量付費。
- 第 3 輪剩下的 3 條錯誤（查核員原文的重點，都是 unsourced 或超出來源）：
  1. **s24.4**：「韓國九尾狐同樣偏向會吃人的妖狐」，來源只支持「多半是欺騙、害人」→ 建議改成「形象同樣多半是害人的妖狐」。
  2. **s24a.7**：「後來的人看牠夜裡出沒，說牠摸不透」，跟有出處的 s24a.6 並列，寫法像在引史料，但沒有出處 → 建議併進「我們的觀察是」的框架，或補原典。
  3. **s26.3**：下集預告「天狗從中國的流星變成日本的長鼻修行者」，這集沒有出處 → 建議改成「下一集，我們追天狗」，或補《史記・天官書》。
- 查核員另外列了 article.md 跟講稿不同步的地方：九十六／九十七回、三千年改兩千多年、郭璞是晉代、三國妖婦傳的順序、北齋一派、澎湃專欄。講稿都已經改對，只有文章（凍結）沒改。說明欄如果從文章取材會再錯一次 🟡。
- 觀眾和導演還有結構上的意見，不影響門檻：第五站時序亂（2022 年的裂石新聞插在 1779 和 1803 之間）、s02.7「第三條先蓋住」看不懂、妲己替罪的因果寫得太滿。
- 改稿之後 deck 是 30 張，policy 通過，角色 pose 也保留下來了。**旁白被改寫過**，所以之後的 voice 步驟會重配改到的句子（±2 句窗口），不再是「只重算時間」。

**待決定（我沒有做）**：
- (a) 照查核員的修法改這 3 句，加開一輪腳本評審。這會超過 `max_rounds: 3`，要明確授權。
- (b) 用 `produce.py approve --gate deck --override "<理由>"` 人工放行。
- (c) 維持現狀，這支片停在這裡。

## 失敗原文 🟢
```
✗ policy: 青蛙書記 on 0/29 slides (>= 80%)
[failed] policy: 青蛙書記 on 0/29 slides (>= 80%)
```
`production.log.jsonl`：`{"at": "2026-10-18T09:25:50+00:00", "step": "policy", "outcome": "failed", "message": "青蛙書記 on 0/29 slides (>= 80%)"}`

- 規則：`src/content_farm/production/channel_rules.py:68` 的 `mascot_findings`，`MIN_MASCOT_SHARE = 0.8`；只有 `channel.mascot.rig_ready` 為 true 時才檢查。
- `channels/yokai.yaml`：`mascot: {name: 青蛙書記, ref: pngtuber/frog-scribe, host: pngtuber, rig_ready: true}`，來自 d95ee3e（2026-10-17 14:02 +0800）。
- `git branch --contains d95ee3e` 的結果是 design/channel-hosts、feat/cowos-v3、feat/incremental-render、feat/review-panels、feat/yokai-tempo，**沒有 feat/channel-voices** 🟢。
- `grep -c '"mascot"' output/yokai-kyubi-v2/deck.json` → 0 🟢。

## 選項（等 Leon 決定，我沒有做）
| 選項 | 做法 | 影響 |
|---|---|---|
| A. 加青蛙書記（建議，符合 10-17 選角） | 在 deck 的 ≥24/29 張加 `mascot` pose，重審 gate_deck，再跑 voice（只重算時間）→ media → mascot → mix | 畫面多了角色，gate_media／gate_final 都要人看；角色可能擋字，要檢查；mascot 冷渲約 3 分鐘（依 incremental-render 的數字）|
| B. 這支片暫不放角色 | 在 run-dir 層級關掉 `rig_ready`（或讓 policy 對這支 run 放行），只改語速 | 跟頻道 10-17 的設定不一致；要改程式或頻道設定，不只改 tempo |
| C. 改在 feat/channel-voices 上跑 | 從沒有 channel-hosts 的分支跑 tempo 1.29 | 拿不到 incremental-render 的快取加速；之後合併時還是會撞到同一條規則 |

## 已完成的部分
- 分支 `feat/yokai-tempo` 從 `feat/incremental-render` 1352879 開。
- `channels/yokai.yaml` 的 `voice.tempo` 從 1.20 改成 1.29。其他頻道沒動：cel 1.12、chipcat 1.15、offwork 1.0，測試裡有斷言。
- `tests/unit/test_voice_tempo.py::test_channel_tempo_follows_decision_and_enters_identity` 改成 1.29：`pytest tests/unit/test_voice_tempo.py` 3 passed 🟢。全套沒有跑，因為只改了這一支測試的斷言。
- 已確認改 tempo 不會重新合成 🟢（讀碼）：`voice/generator.py:132` 的每段 identity 只看 provider、voice、model 和 TTS 文字，不含 tempo；tempo 只走 `tempo.retime`（第 323–327 行）。
- `CF_MLX_VIDEO_HOME` 已經在主 `.env` 裡（`grep -c '^CF_MLX_VIDEO_HOME='` → 1），media 不會再退回 Ken Burns。
- run 用的參數是 `--no-stock`（不打 Pexels）加 `--env-file /Users/lileon/project/content-farm/.env`。

## 還沒量的（因為停在 policy）
新片長、QC、拼音層級的念錯檢查、各步驟耗時、preview（`output/yokai-kyubi-v2/upload/manual/preview.html` 目前是複製來的 1.20 舊版）——全部 🔴 未產生。
- 估算（不是實測）：tempo 1.20 的版本是 641.6 s，raw 是 770.2 s，770.2 ÷ 1.29 ≈ **597 s（9:57）**。字/秒 ≈ 2,358 ÷ 597 ≈ **3.95**，比 CoWoS 4.53、cel 4.47 還低，不會觸發「比其他頻道高 25%」的門檻 🟡（用 channel-voices 報告的數字算的，沒有重量）。
- 拼音層級檢查：本機在 `/` 往下 7 層內找不到 pypinyin（`find` 零命中，沒有做對照組）🟡；repo 的 venv 裡也沒有。要做的話得先決定裝在哪裡（channel-voices §9-4 的同一個問題）。

## 副作用與清理
- `output/yokai-kyubi-v2/`：完整複製的 run-dir，gitignored。`production.json` 多了一筆 policy failed 的紀錄，音檔、media、assembly 都沒變。
- job tmp：`media_report.t120.json`（複製前的 media_report，之後做 gate_media 比對用），job 刪除時一起清掉。
- 沒有背景程序殘留：run 自己以 exit 1 結束。沒開瀏覽器、沒上傳、沒 push、沒用付費服務。

## 進度紀錄（append）
- 2026-10-18 開分支，改 tempo 和測試，複製 run-dir。
- 09:25 UTC `produce.py run` 在 policy 失敗，停下回報。
- orchestrator 轉達：選 A，並照 prompt 檔「追加」一節做（merge review-panels／cowos-facts、deck 加青蛙書記、`--auto-agents` 跑第 3–6 步，gate_final 留給 Leon）。
- 已 merge：`feat/review-panels`（376208e；CLAIMS.jsonl 衝突，保留本分支版本）、`feat/cowos-facts`（dcfc682，沒有衝突）。
- 已寫好 `docs/yokai-tempo/add_frog_poses.py`，給 29/29 張投影片加 pose；原 deck 備份在 run-dir 的 `deck.before-frog.json`。
- **又停下了**：權限分類器以「Modify Shared Resources」擋掉三條指令——全套 pytest（前景、背景各一次），以及執行 add_frog_poses.py 改 run-dir 的 deck.json。deck.json 目前跟備份逐位元相同（cmp 驗過）。我沒有換別的工具繞過。merge 之後的全套 pytest **沒有跑** 🔴。
- Leon 回「放行」之後：
  - 全套 pytest：1480 passed／1 skipped／1 failed。失敗的是既有的 `test_multi_provider::test_returns_first_provider_results[asyncio]`：`--deselect` 沒寫參數後綴所以沒排除掉，它在基準就失敗 🟢。
  - deck 加 pose：29/29 張（`docs/yokai-tempo/add_frog_poses.py`，docs/ 在 gitignore，沒有 commit）🟢。
  - 寫了 `production.frozen.json`（article＋gate_article）。
  - `reject --gate deck` 成功（`deck: rejected @ d4c76e66c19d0713`）。
  - **再被權限分類器擋下**（原文：`Permission for this action was denied by the Claude Code auto mode classifier. Reason: [Modify Shared Resources].`）：`reject --gate media`，以及 `produce.py run --auto-agents --no-stock --env-file …`。
  - media／final 不撤銷也可以：tempo 和角色會讓兩個閘門的指紋改變，舊核可就對不上，評審團會照樣判。
  - 卡住的只有 run 本身，Leon 可以自己跑（見下）。
- Leon 批准（決策 2a7bbb6943dd，orchestrator 加了 allow 規則）。`produce.py run --auto-agents --no-stock` 在 2026-10-18 15:3x UTC 啟動。
- **第 3 步（腳本）3 輪都沒過，停在 gate_deck**（16:16 UTC，exit 1）。照規則停下回報，門檻沒有放寬。原文：`[failed] gate_deck: script: 第 3 輪（最後一輪）未通過：fact_checker-1 找到 3 個事實錯誤`。詳細數字見下方「第 3 步評分卡」。
- orchestrator 轉達 Leon 7afa95870a4e＝A：腳本拆成結構段＋事實段。merge `feat/cowos-facts`（拿到 06772a1，CLAIMS 衝突保留本分支版本）。
  - 舊單段的 `review/deck.fixes.json` 改名為 `deck.fixes.legacy-script.json`；`review/script/` 三輪保留不動，不算新兩段的輪數。
  - 同一條 `produce.py run --auto-agents --no-stock` 在背景重跑。
  - 接手：等它結束，看 `production.log.jsonl` 的最後幾行。中斷了就重跑同一條指令，runner 會從斷點續跑。
- 2026-10-19 orchestrator（fa762192）轉達 Leon 80bd30689ee7＝C（編劇門檻 7→6.5）：
  1. merge `feat/integrate`（08d5b79）→ 529cf76（CLAIMS 衝突保留本分支版本）🟢。
  2. 改門檻（`review/config.py` 的 `THRESHOLD_FLOOR` script_structure writer_min 7→6.5）**被權限分類器擋下**，原文：`Permission for this action was denied by the Claude Code auto mode classifier. Reason: [Modify Shared Resources].`。
     - 已經改好的測試改動（test_review_verdicts）我還原了，worktree 是乾淨的。沒有 commit。
     - 要改的地方：`review/config.py:78`、`channels/shared/review_panels.yaml:201`（script_structure）與 `:259`（shorts_script，「所有階段」），`tests/unit/test_review_config.py:152`（chipcat 預設 ==7）、`tests/unit/test_review_verdicts.py:50-54`（6.5 改成 6.4，訊息改成 `< 6.5`）。
  3. **起點那份 deck 不存在** 🟢：舊單段第 3 輪（7.2／7.0／65.6%）審的那份 deck 是 deck-2 產出 agent 的成品，沒有任何備份。
     - 本機只有 `deck.round2.json`（00:06，deck-2 的輸入）和 `deck.round3.before.json`（00:55，結構段第 2 輪那份），兩份都不含那一版的 s02.7「第三條先蓋住」。
     - 那一版只剩旁白文字和 storyboard 一行一張的摘要，還留在 `review/script/round-3/script.txt`、`storyboard.txt`；條列、media、角色欄位都沒有，沒辦法逐欄還原。
     - 另外，同一份稿（`cmp` 確認 `script/round-3/script.txt` 與 `script_structure/round-1/script.txt` 完全相同）在結構段第 1 輪被重新評成 6.4／6.5。新門檻 6.5 之下，故事 6.4 仍然不過，所以它不一定是「最好的稿」🟡。
- 舊的接手方式：Leon 選了選項之後，A 要先改 deck（加 mascot pose）並重審 gate_deck，再執行 `PYTHONPATH=<wt>/src .venv/bin/python scripts/produce.py run --run-dir output/yokai-kyubi-v2 --no-stock --env-file /Users/lileon/project/content-farm/.env`。
