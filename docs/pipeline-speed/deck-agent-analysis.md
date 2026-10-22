# deck 產出 agent 耗時分析（九尾狐 run，16 次 `claude -p`）

資料：`/Users/lileon/project/content-farm/.claude/worktrees/cf-yokai-tempo/output/yokai-kyubi-v2/`（以下簡稱 RUN）。標記：🟢 = 直接由原始檔算出、可重跑；🟡 = 推論／估算；🔴 = 沒有證據或風險高。

## TL;DR

1. 16 次 deck 呼叫共 6,772 s（113 分）、689,852 output token、US$31.4；其中 7 次「大改」占 5,506 s（81%）、578k token，思考占 53%，寫出占 47%。🟢
2. 大改的「寫出 token」是成品 deck.json 的 1.3–2.7 倍（deck-12/13 約 0.7–1.3 倍），而這幾輪的最小 patch 只需約 4–15k token：agent 幾乎確定在整檔（或大段）重寫。🟡
3. 浪費最大的單點不是 Bash 被拒，而是 deck-12（673 s、75.9k token）整個被「頻道規則 take≥80 字（實 73 字）」拒收還原，deck-13 又重做一次。🟢
4. 被拒 87 次 / 702 turns（12.4%），被拒指令本身只占 output 約 5–6%；真正的損失是「想用 python 程式化修改被拒，改成手寫」。brief 從頭到尾沒講 Bash 能用什麼。🟢
5. 「只換寫出部分為 {id: 新文字}」估 −40~43% output（思考不變）；再加單輪無工具小改與前置頻道規則可達 ≈ −52%。拆章並行省約 29–32 分牆鐘，但 token +14~54%，不算減半。🟡

## (a) 每次呼叫與分類彙總

來源：`deck-N.attempt1.json` 的 `duration_ms`、`usage.output_tokens`、`usage.output_tokens_details.thinking_tokens`、`usage.cache_read_input_tokens`、`num_turns`。寫出 = 輸出 − 思考。

| call | 模型/effort | 耗時 s | output | 思考 | 思考% | 寫出 | turns | s/turn | cache_read÷turn | tok/s | 被拒 | 句子被改（輸入→輸出版） |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| deck-1 | opus/high | 651 | 59,574 | 27,710 | 47% | 31,864 | 66 | 9.9 | 62.5k | 92 | 5 | 54/99 = 55% |
| deck-2 | opus/high | 833 | 79,542 | 40,828 | 51% | 38,714 | 67 | 12.4 | 72.2k | 95 | 5 | 2+3 合計 75/108 = 69% |
| deck-3 | opus/high | 881 | 92,224 | 47,412 | 51% | 44,812 | 67 | 13.2 | 79.4k | 105 | 7 | （同上） |
| deck-4 | opus/high | 1,002 | 109,206 | 46,817 | 43% | 62,389 | 80 | 12.5 | 76.4k | 109 | 6 | 69/119 = 58% |
| deck-5 | opus/high | 910 | 88,654 | 46,974 | 53% | 41,680 | 72 | 12.6 | 85.2k | 97 | 4 | 63/126 = 50% |
| deck-6 | opus/high | 292 | 24,525 | 10,697 | 44% | 13,828 | 62 | 4.7 | 30.3k | 84 | 5 | 6+7+8 合計 7/126 = 6% |
| deck-7 | opus/high | 133 | 13,083 | 5,030 | 38% | 8,053 | 28 | 4.7 | 26.7k | 99 | 6 | （同上） |
| deck-8 | opus/high | 328 | 29,970 | 13,902 | 46% | 16,068 | 59 | 5.6 | 62.6k | 91 | 8 | 做標題/縮圖，旁白幾乎不動 |
| deck-9 | sonnet/med | 207 | 22,255 | 8,455 | 38% | 13,800 | 48 | 4.3 | 34.6k | 107 | 7 | 18/126 = 14%（後被還原，見 c） |
| deck-10 | sonnet/med | 30 | 3,632 | 99 | 3% | 3,533 | 10 | 3.0 | 10.4k | 122 | 2 | 0（只改 AI 圖 prompt） |
| deck-11 | sonnet/med | 33 | 3,121 | 627 | 20% | 2,494 | 9 | 3.7 | 14.8k | 94 | 2 | 0（同上） |
| deck-12 | sonnet/med | 672 | 75,900 | 52,634 | 69% | 23,266 | 41 | 16.4 | 82.6k | 113 | 7 | 被頻道規則拒收並還原，成果丟棄 |
| deck-13 | sonnet/med | 557 | 73,031 | 41,823 | 57% | 31,208 | 38 | 14.7 | 81.0k | 131 | 11 | 12+13 合計 49/114 = 43% |
| deck-14 | sonnet/med | 35 | 2,982 | 332 | 11% | 2,650 | 13 | 2.7 | 8.2k | 84 | 1 | 7/114 = 6% |
| deck-15 | sonnet/med | 54 | 6,821 | 1,570 | 23% | 5,251 | 22 | 2.5 | 15.3k | 125 | 6 | 因「新增句子」被拒收（log 有 problems） |
| deck-16 | sonnet/med | 153 | 5,332 | 1,310 | 25% | 4,022 | 20 | 7.7 | 16.7k | 35 | 5 | 15+16 淨改 3/112 = 3% |

分類彙總（deck-9 單列，因 14% 介於兩者之間；deck-10/11 是 0 句）：

| 類別 | calls | 耗時合計 / 平均 | output | 思考% | 寫出 | turns | s/turn | cache_read÷turn | 費用 |
|---|---|---|---|---|---|---|---|---|---|
| 初稿 | 0 次 | — | — | — | — | — | — | — | — |
| 大改（>30% 句） | 1,2,3,4,5,12,13 | 5,506 s / 787 s | 578,131 | 53% | 273,933 | 431 | 12.8 | 76.5k | $25.51 |
| 中改（10–30%） | 9 | 207 s | 22,255 | 38% | 13,800 | 48 | 4.3 | 34.6k | — |
| 小改（<10%） | 6,7,8,14,15,16 | 995 s / 166 s | 82,713 | 40% | 49,872 | 204 | 4.9 | 34.8k | — |
| 零句（只改 media prompt） | 10,11 | 63 s / 32 s | 6,753 | 11% | 6,027 | 19 | 3.3 | 12.5k | $0.25 |

- 「初稿」0 次：producers.jsonl 從 deck-1 開始，而 deck-1 的 brief 已是「第 1 輪評審未過、退回重做」，輸入是 10-18 的舊 29 張稿（`deck.before-frog.json`）。初稿發生在 10-15（production.log.jsonl 有 deck exit 0，但沒有 producer 紀錄），所以沒有初稿的 token 數據。🟢
- 耗時迴歸（16 點）：`dur = 25.7 + 0.0092 × output`（R²=0.973，即 108 tok/s）；`dur = −28.3 + 0.0079 × output + 2.50 × turns`（R²=0.983，≈127 tok/s + 2.5 s/turn）。牆鐘基本上就是 output token 數。🟢
- 每 turn 寫出 token：小改 200–290，大改 480–820。差額（約 300–600 token/turn）就是 Write/Edit 的內容引數。🟢

### 成品 deck.json 的 token 與「是否反覆整檔重寫」

- 最終 deck.json：69,951 bytes、49,325 字元（CJK 9,950；ASCII 39,011，含兩格縮排）。其中 `sources[]` 15,748 字元（32%，與 sources.json 重複一份）、`sections` 19,132 字元（39%）。🟢
- 估法：token ≈ 字元 ÷ 2（下界）～ ÷ 1.5（上界），得 24.7k–32.9k token。若改按 CJK ≈ 0.8–1.0 token/字、ASCII ≈ 3–4 字/token，約 18–23k。以下倍數用較大的分母（保守，倍數是下限）。🟡

| call | 寫出 | 輸出版 deck 字元 | 該版 token（÷2～÷1.5） | 寫出 ÷ 成品 |
|---|---|---|---|---|
| deck-1 | 31,864 | 32,369（V1 `deck.round2.json`） | 16.2–21.6k | 1.5–2.0× |
| deck-3 | 44,812 | 42,327（`deck.round3.before.json`） | 21.2–28.2k | 1.6–2.1× |
| deck-2 | 38,714 | 無快照（介於 V1 與 V3） | ≈18.5–24.7k | ≈1.6–2.1× |
| deck-4 | 62,389 | 46,888（`deck.structure-r3.json`） | 23.4–31.3k | 2.0–2.7× |
| deck-5 | 41,680 | 48,663（cycle-2/round-2 snapshot） | 24.3–32.4k | 1.3–1.7× |
| deck-12 | 23,266 | ≈49k | 24.5–32.7k | 0.7–0.9× |
| deck-13 | 31,208 | ≈49k | 同上 | 1.0–1.3× |

- 對照「最小 patch」（只列必須寫的：被改的句子、被改的欄位、新增投影片整張 JSON、新增來源）：deck-1 約 6.3k 字元 ≈ 4.0–6.6k token；deck-4 約 9.6k 字元 ≈ 5.8–9.5k token（見 e）。實際寫出是最小 patch 的 5–11 倍（deck-6+7+8 為 23–46 倍，因其中 deck-8 在做縮圖）。🟡
- 推論 🟡：agent 很可能反覆整檔（或整張投影片）重寫，不是逐句 Edit。證據：(1) 寫出是成品的 1.3–2.7 倍，而被點名要改的只有 36–55% 句子；(2) deck-12/13 只淨改 26 句旁白（約 700 字）卻各寫出約 1 個成品；(3) deck-4 先 `cp deck.json deck.round3.before.json`、再兩次嘗試跑 `_round3_restructure.py` 被拒，之後寫出最大（62k）；(4) deck-12 自己 `cp deck.before-final-round1.json deck.json` 還原重來。**缺 per-turn transcript，無法直接證明**，這是上限推論。
- 這批 brief 的任務文字是舊的「照 skill 直接寫 deck.json」；`TASKS_REWORK`（要求用 Edit 逐句改、不要整份重寫、不要重讀 skill）要到 commit `c50eb84`（2026-10-22）才進 `src/content_farm/review/producers.py`，而這個 run 是 10-18～10-19。所以本表是「新 brief 之前」的基線，新 brief 的效果未量測。🟢

## (b) permission_denials

來源：16 個 attempt1.json 的 `permission_denials[]`，全部是 Bash，共 87 次，占 702 turns 的 12.4%（大改 45/431 = 10.4%；小改 38/252 = 15.1%；deck-10/11 4/19 = 21%）。逐筆分類用規則式（`h.py`），見「方法」。🟢

最常見的 5 種被拒型態（依次數）：

| # | 型態 | 次數 | 其中「想程式化修改」 | 例子（decks） |
|---|---|---|---|---|
| 1 | python 內嵌：`python -c "…"`、`python - <<'EOF'`、`python3 - <<'E'` | 33（38%） | 16 | 讀 ledger／印句子（1,2,5,6）；批次取代 deck.json 句子或 AI 圖 prompt（3,4,8,9,10,11,12,13,15） |
| 2 | 執行自己寫的腳本（`/tmp/*.py`、run-dir 的 `_edit.py`、`_round3_restructure.py`、`kyubi_sources.py`） | 16（18%） | 11 | 3,4,7,8,9,12,13,15 |
| 3 | 唯讀探索 shell：`wc -l …/SKILL.md`、`grep -n …`、`cat`、`ls`、`sed -n` | 15（17%） | 1 | deck-1～5 開場固定先 `wc -l` 兩份 skill 檔 |
| 4 | `cd <repo>; …` 或 `env -C <dir> …` 換目錄 | 12（14%） | 0 | 1,2,3,4,5,7,8,13,14,16 |
| 5 | 要跑 deck_to_script.py 但前綴不符（`env -C … python scripts/deck_to_script.py`、`python -I …`、前面串 `cat > fix.py <<`） | 7（8%） | 6 | 1,4,10,11,13,15 |
| — | 其他：curl（維基文庫 API）2、ffmpeg/rm 縮圖 2、graft CLI 1 | 6 | 2 | 2,8 |

「想程式化修改卻被拒、改手寫」：以 `json.dump`／`write_text`／`sed -i`／`.replace(`／`cat >`／`_edit*`／`restructure` 等字樣偵測，36 次（41%），分布在 13 次呼叫（2,3,4,5,7,8,9,10,11,12,13,15,16）。🟡（改成手寫是由「呼叫仍有改動輸出」推論，缺 transcript）
- 被拒指令字元共 65.7k，其中修改類 50.2k，約 25–33k（÷2～÷1.5）~ 33–44k token（全部）；占全部 output 的 4.8–6.4%，≈ 5–7 分鐘純輸出時間。🟢
- deck-10：被拒的取代腳本 3,738 字元，約占該次寫出 3,533 token 的 53–70%；deck-13：被拒 18.7k 字元（≈ 9–12k token），11 次被拒占 38 turns 的 29%。🟡
- 這些腳本被拒後，同一批取代字串又得用 Edit 手寫一遍，等於內容寫兩次。🟡

brief 有沒有說 Bash 能用什麼：**沒有**。16 份 prompt 對 `Bash`／`heredoc`／「不能用 python」全部 0 次命中；只有一句「寫完跑 `<venv python> <repo>/scripts/deck_to_script.py --run-dir … --strict`」。白名單在 `src/content_farm/review/producers.py`：
- `TOOLS = Read, Write, Edit, Glob, Grep, WebSearch, WebFetch`
- `Bash(<python> <REPO>/scripts/{check_article,deck_to_script,make_thumbnail,render_slides}.py:*)`，Claude Code 逐字比前綴，所以加了 `env -C`、`cd`、`-I`、`&&` 的同一支腳本也被拒（deck-1、4、10、11、13、15）。
- 這代表 agent 沒有任何合法的「程式化改 JSON」途徑，只能 Edit/Write。

## (c) 同一句被改幾次

方法：把各版 deck.json 的 narration 以 `。？！；` 切句；先全域精確比對、再同投影片 SequenceMatcher（≥0.30）、再全域（≥0.45）追蹤「句子血統」。全部 100% 命中 sentence_ledger.json 文字（ledger 共 507 個 id，395 個已 retired，現存 112）。版本鏈 V0 `deck.before-frog.json` → V1 `deck.round2.json`（deck-1 輸出）→ V3 `deck.round3.before.json` → V4 `deck.structure-r3.json` → cycle-2/round-2 snapshot → `deck_facts.locked.invalid-e02675f.json` → `deck.title-rework-1.json` → `deck.locked.cycle-2.json` → script_structure/round-1 snapshot → script_facts/round-2 snapshot → `deck.json`。🟢（deck-2、7、8 等中間輸出沒有快照）

現存 112 句各被改幾次：

| 被改次數 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| 句數 | 41 | 22 | 23 | 14 | 7 | 3 | 1 | 1 |

- ≥1 次 71 句（63%）、≥2 次 49 句（44%）、≥3 次 26 句（23%），平均 1.48 次。排除 deck-9 後被還原的旁白版：0:42、1:25、2:25、3:14、4:5、5:1。
- 整條版本鏈合計 362 次「換掉一句」才得到 112 句（約 3.2 次/句）。ledger 的 395 個 retired id 是同一現象的另一種計數。
- 最常被改的句子：s14「據一篇文化專欄的整理…二手整理」7 次（事實查核員反覆質疑二手來源）、s16a「元代說書人的底本武王伐紂平話…」6 次、s01「但最早的原典裡，牠會吃人」5 次、s04 郭璞注、s17a 回顧北齋素描 5 次。
- 依章：開場章平均 2.43 次/句、第一站 2.00、第四站 1.74，反而是句數最多的第二站最低（1.12）。
- 注意：V6（deck-6/7/8 輸出）與 V8（deck.locked.cycle-2）旁白逐句完全相同，也就是 deck-9 的 title-rework-1 對旁白的 18 句修改後來被整批還原（17 句）；deck-12 被頻道規則還原；deck-15 因「新增句子／改寫幅度太大」被拒收，deck-16 重做。這三個呼叫（deck-9/12/15）的旁白成果都沒留下。🟢

每次退回：清單點名 ÷ 實際被改 ÷ 總句數（「實際被換掉」用輸入版句子集合 − 輸出版句子集合；`n.py`）：

| 呼叫 | 清單項數 | 指名句 | 指名∪連動範圍 | 實際被換掉 | 輸入總句數 | 指名/總 | 範圍/總 | 實改/總 | 實改/範圍 | 指名但沒改 | 沒被指名卻被改 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| deck-1 | 88 | 59 | 81 | 49 | 99 | 60% | 82% | 49% | 60% | 11（19%） | 0 |
| deck-2+3 | 67+50 | 120（80 仍存在） | 146（96） | 62 | 99 | — | — | — | — | 19（24%） | 0 |
| deck-4 | 65 | 72 | 97 | 47 | 108 | 67% | 90% | 44% | 48% | 27（38%） | 0 |
| deck-5 | 58 | 81 | 94 | 43 | 119 | 68% | 79% | 36% | 46% | 39（48%） | 0 |
| deck-6+7+8 | 6+3+1（deck 句） | 24（22） | 37（33） | 8 | 126 | — | — | 6% | — | 14（64%） | 0 |
| deck-14 | 7 | 7 | 7 | 7 | 114 | 6% | 6% | 6% | 100% | 0 | 0 |
| deck-15+16 | 5+5 | 9 | 9 | 5 | 114 | 8% | 8% | 4% | 56% | 4（44%） | 0 |

- 觸碰守衛有效：沒被指名卻被改 = 0。🟢
- 大改輪的清單點名 67–68% 的句子、連動範圍涵蓋 79–90%，最後只換掉 36–49%。agent 為了改 36–49% 的句子，得先把近 8–9 成句子都納入考量。清單項數（50–88 項）遠多於指名句數，代表同一句被多位評審重複點名。🟡
- 清單中約一半的項目已經附上「改成「…」」的完整替代文字（deck-1 48%、deck-2 51%、deck-3 50%、deck-4 54%、deck-5 48%、deck-6 50%、deck-14 43%），agent 其實只需照貼。🟢

## (d) 大改拆「按章節並行」的估算

假設與模型（🟡）：
1. 每個 chunk 只收：自己那章的 sections JSON + 相關清單項 + 共用前言（hook／promise／sources 摘要）。
2. 每章的工作量 ∝ 「單一章內可完成」的清單項數；跨章項（指名∪連動範圍落在 ≥2 章）留給串行的「接縫 pass」。跨章項占比：deck-1 13%（11/88）、deck-2 22%、deck-3 26%、deck-4 20%、deck-5 16%。
3. chunk 牆鐘 = 25.7 s + 0.0092 s/token（上面迴歸）× chunk output；思考與寫出不減少，每 chunk 另加固定 2–4k token（讀 brief、回報）。
4. 最後 +45 s 做合併、lint（deck_to_script --strict）、一次檢查。
5. 章節句數（現行稿）：開場 7、一站 8、二站 25、三站 21、四站 19、五站 23、結論 9，共 112；最長 chunk 約占 22%。

| 呼叫 | 觀察 | 並行章 chunk 最長 | + 接縫 pass | 預期牆鐘（含合併） | 省 | 總 output（觀察→預期） |
|---|---|---|---|---|---|---|
| deck-1 | 651 s | 156–175 s | 113–131 s | 314–351 s | 5.0–5.6 分 | 60k → 76–92k |
| deck-2 | 833 s | 252–270 s | 208–226 s | 505–541 s | 4.9–5.5 分 | 80k → 96–112k |
| deck-3 | 881 s | 214–232 s | 265–283 s | 523–560 s | 5.4–6.0 分 | 92k → 108–124k |
| deck-4 | 1,002 s | 291–310 s | 245–263 s | 581–618 s | 6.4–7.0 分 | 109k → 124–140k |
| deck-5 | 910 s | 213–231 s | 171–189 s | 429–465 s | 7.4–8.0 分 | 89k → 102–118k |

五次合計省約 29–32 分鐘牆鐘，但 output token 增加 14–54%（重複前言、固定開銷），cache_write 也要付 7 份前言，費用粗估 +10–35%（未量測）。它省的是時間，不是 token，達不到「output 減半」。

接縫風險（附本 run 證據）：
- 章節銜接：跨章清單項占 13–26%。例子：「把 s17a 整組移到 s21a 後面」（第四站→第五站）、「s15.4 歸到 s16」、每站開頭加路標句與章末預告（deck-13 清單）。這些只能放在串行接縫 pass。
- 重複：deck-4 清單本身就有「結論兩次問『為什麼偏偏是…』」「s26.1 與 s25.8 重複」，各章各自寫會更容易重複免責與收尾句。
- 回扣：開場殺生石（s02）↔ 結尾 s23 回收；墓頂九尾（s11a）↔ 第四站「還記得墓頂那隻」；開場北齋素描 ↔ s17a。改一端要同步另一端，chunk 看不到。
- 共用來源 id：49 條 sources，45 條被引用，13 條被 ≥2 章引用（baihutong 5 章、shj-dating 3 章、thepaper-2018 3 章）。同時各 chunk 新增來源會撞 id、改 sources.json 會互相覆寫；要改成 chunk 只回傳 `sources_add`，由合併者統一發 id 並同步 deck.sources。
- sentence id 與 ledger：21/112 句的 `sentence_ids` 帶別張投影片的前綴（例如 s02a 含 `s02.13`、`s03.6`），ledger 是單一檔案；平行寫會 id 撞號，合併者必須統一配號。
- 全片預算：開場 15 秒內要有鉤子、約 8 分鐘（現稿旁白 3,026 字）等是全片約束，chunk 需要明確的每章字數預算。

## (e)(f) 結構化修改 `{句子id: 新文字}` 的預估

「最小 patch」= 輸入版→輸出版真正變動的內容：新寫的旁白句、被改的非旁白欄位、新增投影片整張 JSON、新增來源條目。token = 字元 ÷2～÷1.5 + 每個 entry 8–12 token 的 JSON 開銷；跨兩次呼叫的群組乘 1.0–1.5（第二次會重做部分）。🟡

| 群組 | 觀察 output（寫出/思考） | patch 字元 / entries | patch token | 思考「不變」時的結構化 output | 相對觀察 |
|---|---|---|---|---|---|
| deck-1 | 59.6k（31.9k/27.7k） | 6,290 / 109 | 4.0–6.6k | 31.7–34.3k | −42~−47% |
| deck-2+3 | 171.8k（83.5k/88.2k） | 11,394 / 179 | 7.1–14.6k | 95.4–102.9k | −40~−44% |
| deck-4 | 109.2k（62.4k/46.8k） | 9,630 / 124 | 5.8–9.5k | 52.6–56.3k | −48~−52% |
| deck-5 | 88.7k（41.7k/47.0k） | 8,146 / 118 | 5.0–8.2k | 52.0–55.2k | −38~−41% |
| deck-12+13 | 148.9k（54.5k/94.5k） | 4,687 / 69 | 2.9–5.9k | 97.4–100.4k | −33~−35% |
| 五組合計 | 578.1k | — | — | 329–349k | −40~−43% |

- 若思考也降到每個清單項 150–300 token（觀察值：deck-1 約 315、deck-2 約 610、deck-3 約 950、deck-4 約 720、deck-5 約 810、deck-12/13 約 1.2–1.5k token/項），五組合計 78–151k，相對觀察 −74~−87%。
- 要在大改輪達到「減半」，思考只需比現在少 12–17%（總量 ≤289k）。換言之，單靠「寫出改成 patch」已接近一半，加一點思考預算就過。🟡
- 限制：patch 無法表達「搬移投影片、拆張、整章重排」（deck-4 清單的 s17a 搬家、s08 拆兩張），這些要用 ops（move/split/insert slide）；deck-12/13 的 35 項裡有 22 項是 assembly(8)／mix(6)／voice(3)／mascot(2)／illustrate(1)／media(2)，deck agent 本來就做不了，思考花在這些上等於浪費。🟢（項目類型計數）

**小改（<10% 句）走「無工具單輪、只吐 JSON，程式套用」的預期耗時（f）**🟡

假設：首 token 約 3.3 s（deck-1 `ttft_ms` = 3,374）、輸出 108 tok/s、程式套用＋lint 約 1 s（log 顯示 deck_to_script 0.2–0.3 s）。patch 0.1–0.5k token，思考 0.3–1.5k（取已觀察的小改範圍 99–1,570）。預期單輪耗時 9–30 s。

| 呼叫 | 實測 | 預估單輪 | 備註 |
|---|---|---|---|
| deck-10 / deck-11 | 30.3 s / 33.8 s（9–10 turns） | 約 9–20 s | patch 只是 3–4 段英文 prompt；實測中被拒腳本占了約 53–70% 的寫出 |
| deck-14 | 35 s（13 turns） | 約 9–24 s | 7 句、222 字 |
| deck-15 / 16 | 54 s / 153 s | 約 9–25 s | deck-15 被拒收；deck-16 35 tok/s，疑似在等 WebFetch |
| deck-6 / deck-7 | 292 s / 133 s（62／28 turns） | 約 12–30 s | deck-6 為了 3 個事實錯誤跑了 62 turns |

- 與 deck-10/11/14（30–35 s）相比，單輪省約 10–25 s/次，相對 −30~−75%；真正的大額是 deck-6（292 s）、deck-7（133 s）、deck-16（153 s）這幾次「為幾句話探索很久」。8 次合計實測 945 s，預期 70–240 s，省約 12–15 分鐘。
- 前提：清單項不需要新來源。deck-6 的 6 項中有 3 項是「unsourced」，要查來源或刪句；這類要 fallback 到有 WebFetch 的 agent。清單已有「改成「…」」的項目（約一半）甚至可以不用 LLM，由程式直接套。🟡

## 結論：同品質下 output token 減半的最小改法（依「最小改動 × 預期節省」排序）

| 順位 | 改法 | 預期節省 | 標記 |
|---|---|---|---|
| 1 | 把「頻道規則」（例如 `take: true` 旁白 ≥80 字）在第一次 brief 就寫進去，或送進 agent 前先跑 `deck_rule_findings` 預檢。目前規則只在被拒後才附上（`panel_flow.py` 約 335–346 行）。本 run：deck-12 因 73 字 < 80 字被拒收還原，deck-13 重做。 | 這個 run 省 673 s（11.2 分）與 75.9k token（占全 run output 11.0%）；發生頻率只有 1/16，其他 run 不保證 | 🟢 |
| 2 | brief 加一句 Bash 用法（「Bash 只能跑 deck_to_script.py，絕對路徑、不加 env -C／cd；改檔用 Edit」），並把一支 `apply_deck_patch.py`（吃 `{id:新文字}`）加進 `SCRIPTS` 白名單，讓程式化修改合法。 | 少掉被拒指令約 33–44k token（4.8–6.4%）＋ 87 個 turn（≈ 5–10 分） | 🟢 |
| 3 | 退回重做改成 patch 契約：agent 只吐 `{id: 新文字, slide 欄位, new_slides, sources_add}`，程式套用（觸碰守衛已在）。`c50eb84`（10-22）的 TASKS_REWORK 已要求「用 Edit 逐句改」，要先用新 brief 重量一次基線。 | 大改輪寫出 274k → 約 20–38k：output −40~−43%（思考不變）至 −74~−87%（思考也縮）；約 −37 分鐘（只算寫出）到 −60 分鐘 | 🟡 |
| 4 | 小改（清單項少、不需新來源）走無工具單輪 JSON；需要新來源的才 fallback 到有工具 agent；清單已附「改成「…」」的由程式直接套。 | 8 次小改 −12~−15 分鐘；output −75~−95%（約 −60~−75k token） | 🟡 |
| 5 | brief 只留 deck agent 做得了的項目：deck-12/13 的 22/35 項（assembly／mix／voice／mascot…）；deck-8/9 的 56/69 項是標題縮圖，改交 thumbnail_spec（deck-8 還在跑 ffmpeg 做縮圖底圖）。 | 估 −4~−8 分、約 −30~−60k token（思考約與項數成正比的粗估） | 🟡 |
| 6 | 把 `sources[]` 從 agent 要編輯的 deck.json 拆開（由 deck_to_script 讀 sources.json 合併）；整檔重寫時少 32% 內容。 | 只在還有整檔重寫時有效；順位 3 做了就沒必要 | 🟡 |
| 7 | 大改按章節並行 | −29~−32 分鐘牆鐘（5 次大改），但 token +14~+54%，要接縫 pass、id 與來源合併 | 🔴 |
| 8 | 直接限制思考預算或降 effort（思考占大改 53%、deck-12 達 69%） | 若思考減半約 −150k token／−25 分；但沒有品質對照，無法證明同品質 | 🔴 |

試算（保守，思考不變）：順位 1 + 3 + 4 合計約 690k → 約 330k（−52%），即過半；單做 1+2 約 −15%，不到一半。🟡

## 方法

- 讀取：`RUN/review/producers/{producers.jsonl, deck-N.prompt.md, deck-N.attempt1.json}`、`RUN/production.log.jsonl`、`RUN/sentence_ledger.json`、`RUN/deck*.json` 與 `review/{script_structure,script_facts}/**/snapshot/deck.json`、`RUN/review/*.fixes*.json`；程式 `src/content_farm/review/producers.py`（本 worktree 與 cf-yokai-tempo 兩份）。
- 呼叫對版本：`deck.round2.json` 含 s04a 且已刪 s18/s25a（deck-1 摘要所述），故為 deck-1 輸出；`deck.round3.before.json` 是 deck-4 自己 `cp` 的備份（denial 內可見），故為 deck-3 輸出；其餘依 mtime（UTC+8，對 production.log.jsonl 的 UTC）與內容大小對齊。deck-2、7、8、10/11、12、15 沒有各自輸出快照，用「合併群組」。🟡
- 句子切分與血統追蹤見 (c)；patch 估算見 (e)。逐筆被拒指令以規則式分類。
- 可重跑腳本（暫存，Python 為 `/Users/lileon/project/content-farm/.venv/bin/python`）在 `/Users/lileon/.claude/jobs/f924c39e/tmp/`：`a.py`（逐次表）、`h.py`（被拒分類、迴歸、彙總）、`c.py`／`f.py`（句子 diff 與血統）、`g.py`／`n.py`（patch 估算、清單 vs 實改）、`d.py`／`m.py`（清單解析）、`e.py`／`q.py`（deck 規模、來源共用）、`k.py`（並行模型）、`l.py`（結構化估算）。

## 限制

- 沒有 per-turn transcript：「整檔重寫」「被拒後改手寫」是由 token 量與結果推論，沒有逐 turn 證據。
- 版本對齊靠 mtime 與內容，中間輸出缺失；deck-2+3、6+7+8、12+13、15+16 只能合併看。
- 「實際被換掉」以句子集合差計算，句子搬移或只改標點會有偏差；血統追蹤的相似度門檻（0.30／0.45）為啟發式。
- token 以字元÷1.5～2 估，實際分詞器可能更低（見 18–23k 的另一種估法），因此「寫出 ÷ 成品」的倍數是保守下限。
- usage 只含主模型（opus／sonnet）；`models_used` 內的 haiku（多半是 WebFetch 摘要）另計，未納入。
- 並行與 patch 的耗時、費用都是模型推算，不是實測；思考預算的假設（每項 150–300 token）未驗證品質。
- 樣本只有一支片（九尾狐）、一個頻道規則集；deck-12 的頻道規則拒收是否常見，不能由 1/16 外推。
- 分析基於 `c50eb84`（10-22）之前的 brief，之後的「退回重做＝diff」版本沒有實測資料。
