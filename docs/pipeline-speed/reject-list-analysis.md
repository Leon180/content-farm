# 退回清單點名過廣：逐層量測與修改草稿

資料：九尾狐 run `cf-yokai-tempo/output/yokai-kyubi-v2/review/`（舊路由、尚無 touch guard）。程式：`cf-pipeline-speed/src/content_farm/review/`。

## TL;DR

1. 沒有「聚合 agent」這一層：`schemas.AGGREGATE` 與 `config.aggregator` 只有定義、全 repo 無呼叫點；退回清單是 `routing.plan()` 對每個通過查證的 issue 1:1 轉成一條 fix。
2. 灌水分兩層。評審席次原始輸出就點名 65–73% 的句子（三個專業席各 21–42%，每席 12–18 個問題、無上限）；`claim_change=true` 的 3–7 個問題再把整章展開，scope 升到 79–95%（多出 118 句，只有 8 句真的被改，7%）。
3. 實際被改的比例 35–54%（deck-1..5）。只看評審直接 `ref`（不連動）的點名是 60–68%，涵蓋了 95–98% 被改的句子；連動多加的句子幾乎全是白讀。
4. 觀眾離開點 `left_at_sentence` 直接就是句子 id，不會被展開；整章展開來自同一位觀眾 `top_fixes` 裡設了 `claim_change`（12 位離開的觀眾中 3 位）。成片階段的離開點只有 m:ss，程式沒有任何 時間→句子 對應。
5. 建議三件事：prompt/schema 要求每個問題 ≤4 句且 script 類一定有句子 id、`claim_change` 只展開到投影片、程式端依嚴重度與席次共識裁到 ≤30%（超過 25% 要附理由）。離線重算只能驗證程式端，prompt/schema 要新跑評審才量得到。

## 1. 退回清單怎麼組出來（資料流）

| 步驟 | 程式 | 欄位／行為 |
|---|---|---|
| 各席輸出 | `schemas.py` `PRO`/`FACT`/`SCRIPT_VIEWER`/`FINAL_VIEWER` | `issues[]`（專業、查核）或 `top_fixes[]`（觀眾，prompt 說最多 3 條，schema 沒有 maxItems）；每個 issue 的 `ref = {target, sentence_ids?, t?, item?}`、`severity`、`evidence`、`caused_by`、`claim_change`。`sentence_ids` 可省略也可為空陣列；`target:"script"` 不帶 id 也合法 |
| 觀眾離開點 | `SCRIPT_VIEWER.left_at_sentence`（句子 id）；`FINAL_VIEWER.left_at`（m:ss） | 只進 `verdicts._leave()` 算離開比例，**不進修改清單**；`_collect()` 只收 `issues`、`top_fixes`、`claims`(wrong/unsourced) |
| 收集 | `verdicts._collect()` | 非 holdout 席的 issues + top_fixes + 錯誤 claims 全部攤平，無去重、無嚴重度過濾、與「這輪為什麼沒過」無關 |
| 查證 | `verdicts.split_issues()` | 只丟掉「id 不存在」「evidence 不在素材裡」的；不判斷必要性 |
| 路由 | `gate._rework()` → `routing.plan()` | 每個 issue 一條 fix，`slot.sentence_ids = ∪ scope.sentence_ids`；沒 issue 時才合成一條無 id 的 `target:script`（open 計畫） |
| 連動 scope | `routing.simple_scope()`（`explainer.fix_scope` 沒有 `issue_scope`，一律走這個後備版） | scope = 點名 id ∪ evidence 裡的數字／英文詞／「」詞出現的所有句子 ∪（`claim_change` 時）點名句所在**整個章節（section）** |
| 簡報 | `producers._fixes_text()` | 每條 fix 把 `ref` 與 scope 的句子 id 全文寫進 brief（還附 problem/fix 文字，裡面常再提到別的 id） |

我用 `simple_scope` 的邏輯對各輪 scorecard 重算連動範圍，與 brief 內 scope 逐輪完全一致（deck-1,2,3,4,5,6,7,14,15 九輪聯集相同），所以下面的拆解是可信的。

### 逐層量測（deck-1..5：講稿結構退回；分母＝被評審那一版的句子總數）

| 退回 | 來源輪次 | 總句數 | ① 各席原始點名聯集 | ② 通過查證 `ref` | ③ 連動 scope | ④ brief 不同 id（cost-replay 算法） | 實際被改 |
|---|---|---|---|---|---|---|---|
| deck-1 | script/round-1 | 99 | 64 (65%) | 59 (60%) | 81 (82%) | 88 (89%) | 49 (49%) |
| deck-2 | script/round-2 | 99 | 67 (68%) | 66 (67%) | 94 (95%) | 95 (96%) | 41 (41%) |
| deck-3 | structure/cycle-1/r1 | 108 | 78 (72%) | 69 (64%) | 99 (92%) | 101 (94%) | 58 (54%) |
| deck-4 | structure/cycle-1/r2 | 108 | 79 (73%) | 72 (67%) | 97 (90%) | 101 (94%) | 46 (43%) |
| deck-5 | structure/cycle-2/r1 | 119 | 83 (70%) | 81 (68%) | 94 (79%) | 103 (87%) | 42 (35%) |

cost-replay 的「79–92%」我對不上：③ 是 79–95%、④ 是 87–96%（可能分母或取值版本不同）。

**哪一層灌的：**

| 層 | 增量 | 證據 |
|---|---|---|
| 評審席次原始輸出 | 起點就 65–73% | 專業席各 21–42%（導演 27/38/39/42/39%、編劇-資訊密度 37/29/38/37/29%、編劇-故事 30/21/40/25/32%）；每席 12–18 個問題；8 席 id 提及總和 132–180 次對 64–83 個不同句子（deck-1 為 151 次對 59，2.5 倍重複） |
| ①→②查證 | −0～−9 | 只擋「id 不存在／引文對不上」，不是必要性過濾 |
| ②→③ `claim_change` 整章展開 | +13～+30 | 每輪只有 3–7 個問題設 `claim_change`，每個展開成 9–49 句（deck-3 viewer-scholar 4 句→49 句）。數字／詞語連動幾乎為零：5 輪合計只有 deck-3 的「履歷」多連到 3 句 |
| ③→④ brief | +2～+9 | fix 文字裡提到的其他 id（例：「把 s11.9 換成……」） |
| 「全片性問題展開成每句」 | 0 | 5 輪中沒有 script 類無 id 問題（deck-4/5 的 3 條無 id 都是 `target:article` 的查核）；無 id 計畫只在「純分數不過且沒有任何 issue」時由 `gate` 合成 |

連動多加的句子（③ 減 ②）5 輪共 118 句，其中只有 8 句最後真的被改（7%）；而被改的句子 95–98% 本來就在 ② 裡。即連動沒有補到漏網之魚，只是把 brief 和 guard 的放行範圍變大。

另兩個放大因素：失敗原因只是「編劇分數 < 門檻」，路由卻把**所有席次的所有 issue**（含 low、其他席）全送；severity 在路由裡完全沒用到（5 輪 328 條 issue：high 75／med 143／low 110）。

## 2. 每次退回：點名 vs 實際改動

「實際被改」＝退回前版本的句子，其正規化文字不在退回後版本裡（刪、改、拆都算）。前後版本取自各輪 `script.txt`（deck-1..7、14..16）或 deck.json 快照（deck-8、9、12+13）。分母為退回前版本句數。

| 退回 | 性質 | 總句數 | ref | 連動 scope | brief id | 實際被改 | brief／總 | 被改／總 | 落差 |
|---|---|---|---|---|---|---|---|---|---|
| deck-1 | 講稿結構 | 99 | 59 | 81 | 88 | 49 | 89% | 49% | +40pp |
| deck-2 | 講稿結構 | 99 | 66 | 94 | 95 | 41 | 96% | 41% | +55pp |
| deck-3 | 講稿結構 | 108 | 69 | 99 | 101 | 58 | 94% | 54% | +40pp |
| deck-4 | 講稿結構 | 108 | 72 | 97 | 101 | 46 | 94% | 43% | +51pp |
| deck-5 | 講稿結構 | 119 | 81 | 94 | 103 | 42 | 87% | 35% | +52pp |
| deck-6 | 事實段 r1 | 126 | 8 | 8 | 8 | 5 | 6% | 4% | +2pp |
| deck-7 | 事實段 r2 | 126 | 3 | 21 | 22 | 3 | 17% | 2% | +15pp |
| deck-8 | 標題退回 | 125 | 13 | 13 | 17 | 1 | 14% | 1% | +13pp |
| deck-9 | 標題退回 | 125 | 16 | 33 | 39 | 17 | 31% | 14% | +17pp |
| deck-10,11 | 素材 prompt | — | 0 | 0 | 0 | （只改 media.prompt，不是句子） | — | — | — |
| deck-12+13 | 成片退回 | 125 | 0 | 0 | 0 | 36（另新增 25 句，125→114） | 0% | 29% | 見下 |
| deck-14 | 事實段 | 114 | 7 | 7 | 9 | 7 | 8% | 6% | +2pp |
| deck-15+16 | 事實段 | 114 | 9 | 9 | 11 | 5 | 10% | 4% | +6pp |

- deck-7 的 3 條 fix 只點名 3 句，其中一條 `claim_change` 把 scope 擴到 20 句；這是事實段（只准刪改）卻被展開 7 倍。
- deck-15 與 deck-16 前後版本相同（同一輪的重試），合併計。deck-12／13 為同一輪重試，合併計。
- deck-12/13（成片）：fix 只有 `ref.t`，brief 裡 0 個句子 id，但 deck 被改了 36 句、新增 25 句。以現行 `touch_guard.named_in()` 判讀：`target:"video"` 又沒有 id 時 `open=False`、`sentence_ids` 為空，任何旁白改動都會被拒收。這是讀程式推出來的，我沒有執行驗證。

### 被改的比例是「結果」不是「必要」

producer 對被點名的問題照單全收：5 輪 328 個 issue 中 91–96% 至少改了其中一句（high 95%、med 96%、low 91%）。所以「被改比例」會隨點名縮小而縮小，不能單獨拿來當標準答案；它只證明連動多出來的 118 句 producer 自己判斷不用動。

各席點名後被改的比例（句子層，5 輪合計）：

| 席次 | issue 數 | 點名 id（含重複） | 被改 | 命中率 |
|---|---|---|---|---|
| 觀眾 | 55 | 160 | 146 | 91% |
| 查核（只列不擋） | 76 | 93 | 85 | 91% |
| 編劇-資訊密度 | 69 | 167 | 132 | 79% |
| 編劇-故事 | 68 | 166 | 126 | 76% |
| 導演 | 60 | 168 | 102 | **61%** |

導演點名最多、命中最低。

## 3. 評審提示詞與 schema：有沒有要求「只列需修的」

現況（`prompts.py`、`review_panels.yaml`）：

- 沒有任何一句要求只列真正需修的句子。`RULES` 的方向相反：「不要客氣，不要比真人更有耐心」「找出觀眾會流失或被誤導的地方」。
- 專業席（writer_story、writer_density、director）的任務文字是「依 rubric 評講稿與分鏡，各項 0–10……問題用句子 id 指認」。rubric 是清單式（5 項／4 項），沒有「分數達標的面向不用列問題」，也沒有問題數上限；實測每席 12–18 個。
- 觀眾「top_fixes 最多 3 條」只在 prompt 與 viewer 任務文字裡，schema 沒有 `maxItems`；每條 fix 可以列任意多個 id（單條最多 9 個，deck-1 viewer-student 3 條共 17 個 id）。
- schema：`ref.sentence_ids` 非必填、無 `minItems`／`maxItems`；`target:"script"` 不帶 id 合法；`severity` 有 `low` 且不影響路由；`claim_change` 只有一句「true when the fix changes a chapter's argument」，沒說程式會展開整章。
- `schemas.validate()` 只支援 type／enum／minimum／maximum／items／required，不認 `minItems`／`maxItems`，要先補。

### 修改草稿（diff 草稿，未改 src）

```diff
--- a/src/content_farm/review/prompts.py
+++ b/src/content_farm/review/prompts.py
@@ RULES
 - 修改建議要具體（要改成什麼），不准要求灌水內容、不准建議誇大標題或縮圖；改動會牽動章節主張時把 claim_change 設為 true。
+- 只列「不改就會讓觀眾流失、被誤導或事實錯」的問題。偏好、可改可不改的潤飾不要列；寧可少列，不要湊數。
+- 每位評審最多 8 個問題（觀眾 top_fixes 最多 3 個），依嚴重度由重到輕取。分數 ≥ 8 的評分項目不要列問題。
+- sentence_ids 只放「必須改寫或刪除的句子」，每個問題最多 4 句。同一類毛病出現在很多處時，放最嚴重的 4 句，
+  其餘寫在 problem 的「同型：」文字裡，不要放進 sentence_ids。
+- 講稿類問題一定要有 sentence_ids。真的是全片性問題、縮不到具體句子時，才設 ref.scope="global"，並用 why_global 寫一句為什麼縮不下來。
+- severity=low 的小毛病不要當問題，寫進 notes（不會送給修改的人）。
+- claim_change=true 只在這個修改會推翻整章結論時才設，並把受影響的投影片 id 填進 affected_slides（最多 3 張）；程式只展開到那幾張。
@@ STAGE_TASK["script"]["viewer"]
-... 照你的人設，標出你會離開的那一句（left_at_sentence，看完就 null）。top_fixes 最多 3 條。
+... 照你的人設，標出你會離開的那一句（left_at_sentence，看完就 null）。top_fixes 最多 3 條；有離開時第一條的
+sentence_ids 第一個必須是 left_at_sentence，後面最多再放 3 句造成離開的原因，不要列整頁或整章。
```

```diff
--- a/src/content_farm/review/schemas.py
+++ b/src/content_farm/review/schemas.py
@@ ISSUE.ref.properties
-                "sentence_ids": {"type": "array", "items": _STR},
+                "sentence_ids": {"type": "array", "items": _STR, "maxItems": 4},
+                "scope": {"enum": ["sentences", "global"]},
+                "why_global": {"type": ["string", "null"]},
@@ ISSUE.properties
-        "severity": {"enum": ["high", "med", "low"]},
+        "severity": {"enum": ["high", "med"]},      # low → notes
         "claim_change": {"type": "boolean", ...},
+        "affected_slides": {"type": "array", "items": _STR, "maxItems": 3},
@@
-_ISSUES = {"type": "array", "items": ISSUE}
+_ISSUES = {"type": "array", "items": ISSUE, "maxItems": 8}
@@ PRO / FACT / SCRIPT_VIEWER / FINAL_VIEWER
+ notes={"type": "array", "items": _STR, "maxItems": 10}      # 不送給修改的人
@@ SCRIPT_VIEWER
-    top_fixes=_ISSUES)
+    top_fixes={"type": "array", "items": ISSUE, "maxItems": 3})
@@ def validate()
+    if isinstance(value, list):
+        if "maxItems" in schema and len(value) > schema["maxItems"]:
+            errors.append(f"{path}: {len(value)} items > {schema['maxItems']}")
+        if "minItems" in schema and len(value) < schema["minItems"]:
+            errors.append(f"{path}: {len(value)} items < {schema['minItems']}")
```

```diff
--- a/src/content_farm/review/verdicts.py
+++ b/src/content_farm/review/verdicts.py
@@ verify_issue
+    if target == "script" and not ids and ref.get("scope") != "global":
+        return "script issue names no sentence (set ref.scope=global with why_global)"
```

```diff
--- a/src/content_farm/review/routing.py
+++ b/src/content_farm/review/routing.py
@@ simple_scope
-    linked = [s.id for s in texts.sentences if s.id in named or any(t in s.text for t in terms)]
+    hits = {t: [s.id for s in texts.sentences if t in s.text] for t in terms}
+    common = {t for t, ids in hits.items() if len(ids) > 6}      # 太常見的詞不連動
+    linked = [s.id for s in texts.sentences if s.id in named or any(t in s.text for t in terms if t not in common)]
@@
     if issue.get("claim_change"):
         sections = {s.section for s in texts.sentences if s.id in named}
-        chapters = tuple(sorted(sections))
-        linked += [s.id for s in texts.sentences if s.section in sections and s.id not in linked]
+        chapters = tuple(sorted(sections))        # 仍整章送回評審複審，但不整章要求重寫
+        slides = set(issue.get("affected_slides") or []) | {s.slide_id for s in texts.sentences if s.id in named}
+        linked += [s.id for s in texts.sentences if s.slide_id in slides and s.id not in linked]
```

### 程式端守門（建議要加）

提示詞和 schema 靠評審自律，`claude -p` 的 schema 重試會多花錢（`schema_retries: 1`），所以 maxItems 違規優先改成程式裁切而不是退件。建議在 `gate._rework()` 呼叫 `routing.plan()` 之前加一個確定性的 `review/narrow.py`（不呼叫 LLM）：

```python
MAX_SHARE = 0.25          # 超過就要求理由
HARD_SHARE = 0.30         # 超過就裁切

def narrow(issues, sentences, *, hard=HARD_SHARE):
    """依 (fact 先於其他, severity, 席次共識數, id 數少者優先) 排序，累加到點名 id 聯集 ≤ hard×總句數為止。
    global 且附 why_global 的 issue 不受限。被擠掉的進 deferred：寫進修改清單的 advisory，下一輪評審若仍點名就會再進來。"""
```

- 先去重：共用 id 的 issue 合併成一條（votes＝提到這些 id 的席次數）；`AGGREGATE` schema 現成，但先不要接 LLM 聚合，確定性合併就夠。我沒量合併後的條數。
- 路由時帶出 `named_share`／`scope_share`／`deferred` 三個數字寫進 `*.fixes.json`，之後直接量前後差。
- 離線重放（只動程式端，用現成 scorecard，沒有跑任何評審）：

| 方案 | deck-1 | deck-2 | deck-3 | deck-4 | deck-5 | 被改句子的涵蓋率（五輪範圍） |
|---|---|---|---|---|---|---|
| 現況 scope／總句數 | 82% | 95% | 92% | 90% | 79% | 100% |
| 只改 `claim_change`→投影片級 | 69% | 74% | 71% | 70% | 71% | 97–100% |
| 只取 `ref`（不連動） | 60% | 67% | 64% | 67% | 68% | 95–98% |
| `ref` 且只取 high+med | 53% | 58% | 45% | 55% | 53% | 72–92% |
| `ref` 且每席取最重 5 條 | 35% | 41% | 44% | 39% | 44% | 63–79% |
| `ref` 且每席取最重 3 條 | 34% | 32% | 38% | 25% | 33% | 48–64% |
| 每個問題 id 截到 3 句 | 57% | 63% | 59% | 56% | 54% | 87–95% |

要壓到 25% 以下只有「每席 top-3」做得到，代價是涵蓋率掉到 48–64%。我的建議：25% 當警示線（超過必須有 `why_global` 或程式裁切後在 scorecard 標示），硬上限 30%、並依賴多輪重審補回被擠掉的項目。涵蓋率不等於品質損失（producer 會順手全改，見第 2 節末），真正要驗的是「輪數與離開比例有沒有變差」，需要新跑評審。

### 前後差怎麼量

指標：`brief_share`（cost-replay 算法）、`scope_share`、`ref_share`、`changed_share`，加 `precision = 被改∩點名 / 點名`。基準線就是第 1、2 節的表。程式端改動可用現有 scorecard 離線重放（上表）；prompt／schema 改動要重跑評審席次（雲端車道，有預算），所以建議先上程式端、再用 `CF_REVIEW_CACHE=0` 跑一輪新 prompt 對照，不要兩個一起改。

## 4. 觀眾離開點如何對應句子 id

- **講稿階段**（`script_structure`）：觀眾看到的是 `script.txt`，每句 `[id] ~m:ss 文字`（`sentences.listing()`，時間是 0.22 秒／字的估計）。`left_at_sentence` 直接填句子 id，不需要換算。`verdicts._leave()` 用 `position_share()`（字數累計比例）算離開位置；id 不存在就當 1.0（看完）。離開點本身**不會**進修改清單。
- **離開點與修改清單的關係**：12 位離開的觀眾（deck-1,3,4,5 的各輪）全部把離開的那一句放在自己的 `top_fixes` ids 裡（距離 0）。但他們的 3 條 top_fix 平均帶 5–17 個 id，多數是別處的同型毛病（deck-1 viewer-student：離開在 s11.1，3 條共 17 個 id，離開點只是其中 1 個）。
- **是否整章展開**：離開點本身不會，但那條 top_fix 若設了 `claim_change`，就整章展開。11 條觀眾 `claim_change` 中有 3 條含離開句：deck-3 viewer-scholar（離開 s25.6，4 句→24 句）、deck-5 viewer-folklore_fan（離開 s14.17，4 句→30 句）、deck-5 viewer-scholar（離開 s17.13，3 句→14 句，剛好是整個「第四站」）。其餘 8 條是觀眾對別處的主張問題，最大展開到 deck-2 的 46 句、deck-3 的 49 句。
- **成片階段**（`final`）：觀眾輸出 `left_at`（m:ss）與 `top_fixes[].ref.t`。`verdicts.final()` 呼叫時 `sentences=[]`，沒有任何 時間→句子 的對應；`verify_issue` 對 video／audio 只檢查 `t ≤ 片長`。實測 final/round-1 觀眾填的 `sentence_ids` 是 `['5','6','9']`、`['70','71']`、`['106'…'111']` 這種純數字（不是 `sXX.n`），因 `sentences` 為空，`unknown` 檢查被跳過而放行。結果 deck-12/13 的 brief 裡 0 個句子 id，但 producer 實際改了 36 句。
- 建議補一個 `sentences_at(timeline, t, radius=1)`：用 voice 步驟寫回的實際句長（`sentence_ledger.json`／`script.json`）建立時間軸，把 `ref.t` 換成「該秒所在句 ± 1 句」寫進 `ref.sentence_ids`，並禁止觀眾在 video 類 issue 自填 `sentence_ids`；`claim_change` 對觀眾離開類 issue 不展開整章。

## 方法

1. 讀 `rounds.py`、`gate.py`、`verdicts.py`、`routing.py`、`producers.py`、`touch_guard.py`、`schemas.py`、`prompts.py`、`review_panels.yaml`；`grep AGGREGATE|aggregator` 只命中定義。
2. 把 `producers/deck-N.prompt.md` 對到來源輪次：靠「第 N 輪評審未過」標頭、fix 條數（例如 deck-1＝88 條＝script/round-1 的 88 個 issue）和 `producers.jsonl` 時間戳。對應：deck-1,2→script/r1,r2；deck-3,4→structure/cycle-1 r1,r2；deck-5→cycle-2/r1；deck-6,7→script_facts/cycle-2 r1,r2；deck-8→title cycle-1/r2；deck-9→title cycle-2/r1；deck-14,15,16→script_facts r1,r2。
3. ① 讀 `results/*.json`（排除 holdout 與失敗席），取 issues、top_fixes、claims(wrong/unsourced) 的 sentence_ids，與被評審版本的 id 取交集；② 取 scorecard `verdict.issues` 的 `ref.sentence_ids`；③ 解析 brief 內每條 fix 的「指認」JSON 與「連動要一起改」；④ brief 內「這是退回重做」之後 `s\d+[a-z]?\.\d+` 的不同值。
4. 實際被改：退回前後 `script.txt`（或 deck.json 以句號切句）正規化文字比對（`verdicts.normalize` 同款）；早期 id 不穩定所以用文字而非 id。
5. 重放：複製 `simple_scope` 對 scorecard 重算 scope，與 brief 的 scope 聯集逐輪相等後，才拿來模擬各方案。
6. 🟢 可重跑：暫存腳本在 `/Users/lileon/.claude/jobs/f924c39e/tmp/analyze.py`、`analyze2.py`～`analyze7.py`，用 `/Users/lileon/project/content-farm/.venv/bin/python -I <script>` 執行（暫存目錄，會被清掉）。

## 限制

- 單一 run（九尾狐）、舊路由、尚無 touch guard 與「退回是 diff」的 brief；`routing.py` 與 cf-yokai-tempo 逐字相同，`prompts.py` 只差 `visible_to` 一行，所以流程結論適用現行碼，但數字不代表現行 prompt 的 brief。
- 「實際被改」是 producer 對現有清單的反應，不是「真正需要改」的標準答案（採納率 91–96%）。涵蓋率與命中率只能說明連動範圍是白讀，不能證明縮小後品質不變。
- deck-2 的 99 句與 deck-1 同數；deck-1 之前的初稿版本不在資料夾，deck-1 的「前版」採 script/round-1 的 `script.txt`。deck-8、9、12+13 用 deck.json 快照，切句規則與 `script.txt` 略有不同。
- cost-replay 的 79–92% 無法精確還原；deck-15/16、12/13 合併計。
- 第 3 節方案的離線數字只涵蓋程式端；prompt／schema 的效果沒有測，也沒有跑任何評審（不花錢）。「合併共用 id 的 issue」沒有量。
- 觀眾離開點樣本：講稿階段 12 位離開、11 條 claim_change；成片階段只有 4 位觀眾（1 輪）。
