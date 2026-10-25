---
name: fable-script
description: Write fable.json for one 寓言學堂 video — an original fable that teaches a graduate-level concept, named only at the reveal, then explained beat by beat. Use for /fable-script, "寫寓言腳本", or when `produce.py run --channel fable` stops at the fable_script step.
---

# /fable-script — 寓言學堂腳本

頻道承諾：**觀眾先經歷一則故事，故事快結束才發現它在講哪個概念**，然後我們把故事情節一一對回概念。目的是給觀眾「理解的過程」，不是直接給答案。

輸入：run-dir 的 `topic.json`（`chosen[0]`：`concept`、`domain`、`format`（short／mid）、`premise` 提示、`hints`）。輸出：run-dir 的 `fable.json`（格式見下）。寫完跑
`{python} scripts/fable.py lint --run-dir <run-dir>`，改到 0 problem(s)。不要停下來等人審。

## 結構（程式會檢查）
1. **hook**（1 個 beat，一句）：好奇鉤子。可以說「這個故事在講一個○○學的概念，你猜得到嗎？」，**不能**透露概念名或同義詞。
2. **story**（寓言本體）：原創角色——動物、器物、村莊、季節，**不用真人**（圖片提示詞也不能有人物字眼）。要有：一個**選擇**與它的**代價**；2–3 條**伏筆**（hooks：故事裡埋下一個讓人想知道答案的小疑問）。故事不解釋、不說教，用情節讓概念自己長出來。
3. **reveal**（1 個 beat）：第一個說出概念名的地方，旁白要含概念名，`card.title`＝概念名（畫面會從繪本轉成概念圖解）。伏筆在這裡或之後收掉。
4. **explain**（2–4 個 beat；mid 4–8 個）：用故事情節逐一對應概念的要素。每個 beat 有 `card.rows`（左＝故事裡發生什麼，≤ 24 字；右＝它對應的概念要素，≤ 28 字）與 `maps`（對應的 element id）。每個 element 至少被一個 explain beat 對應。要精確：是研究所教科書上的說法，不誇大、不把比喻當定理；比喻的極限（哪裡不像）可以用一句話說。
5. **apply**（最後 1 個 beat）：一句現實應用——這個概念出現在哪個真實情境。

揭曉規則：概念名、同義詞、英文名（`concept.aliases`、`concept.english` 都要列全）在揭曉前不得出現在標題、hook、story 的旁白、圖片提示詞、card。程式會逐字比對。連這些近義說法也避開：換個譯名、縮寫、經典案例名（例如案例名本身就是答案）。

## 每個 beat 先寫 must_keep／must_avoid
- `must_keep`：這個 beat 一定要留下什麼（一條情節事實、一個伏筆、一個要素對應）。
- `must_avoid`：這個 beat 不能做什麼（例如「不能提早點出代價的名字」「不能說教」「不要出現概念名」）。
兩者都要有內容（各 1–2 條短句），寫完照它們檢查旁白。

## 長度
- `short`（直式 Shorts）：全片估計 55–88 秒（每秒約 5.5 字）；寓言（hook＋story）約 36–62 秒，揭曉＋解釋＋應用約 16–38 秒；story 3–6 個 beat、explain 2–4 個，總共 ≤ 12 個 beat。每個 beat 旁白 ≤ 15 秒（約 80 字）。
- `mid`（橫式中片）：全片 230–370 秒；寓言 130–270 秒；解釋 70–140 秒；story 8–18 個 beat、explain 4–8 個。每個 beat ≤ 26 秒。
- 每個 beat 的 `shots` 是它的畫面：旁白每 8 秒左右換一張圖（`ceil(秒數/8)` 張，最多 3 張）。揭曉與解釋 beat 可以用 `reuse` 指到更早的 shot（如 `"b3.1"`），畫面會顯示那張圖＋概念對照卡。

## 圖片提示詞（image_prompt）
英文、只寫內容（頻道的繪本風格前綴由系統加上）：角色（動物／器物）、場景、構圖、光線、情緒，一張圖一個清楚的主體。不要人物、人臉、人群（市集、街道、村莊不要寫 crowd／customers／street 這類會畫出路人的字，改寫成空的攤位、遠處的小動物剪影）、文字、招牌、標誌；角色用具體外形描述（例如 slim red-brown fox-like animal with a ringed tail），不要寫 tanuki／raccoon dog／round／chubby（模型會畫成既有的電影角色）；不要寫畫家名字或「照片」。**動物保持動物身體，不畫人手**（Leon 2026-10-24：貓頭鷹長出人手很怪）：不要寫 holding／writing／hands／arms／fingers／carrying／reading 這類讓動物用手的動詞；道具（書、本子、燈）寫成放在旁邊的樹枝／地上／桌上，動物翅膀收起或前爪著地；要「寫字」「翻書」的劇情改成書本特寫（翻開、寫滿字）加動物在背景。系統會自動加身體規則與預設 negative prompt，`scripts/fable.py lint` 會擋上述動詞。直式 9:16（short）與橫式 16:9（mid）由系統決定，不用寫。

## 縮圖選項（thumb，1–3 個，選填但要寫）
縮圖有自己的鉤子，不是把標題再貼一次：
- `hook`：**4–8 字**（含標點）的短句，製造「想知道答案」的缺口，與標題互補（標題講什麼事，鉤子丟衝突或問題，例：「誰會贏？」「打還是讓？」「為什麼沒人贏」）。不得含概念名／同義詞；前 60 秒的故事要兌現它。
- `image_prompt`：英文，**專為縮圖構圖**——特寫、主體佔畫面 60% 以上、背景簡化、高對比、情緒清楚（例：兩隻對峙的小鳥，一隻張翅撲上、一隻退一步）；同樣不得有人物、文字，不寫畫家名。風格前綴與「特寫構圖」句由系統加上。
- `layout`：`left`／`right`／`bottom`，字放哪一側（主體在另一側）。
三個選項要有差異（不同鉤子＋不同構圖），會放進 YouTube「測試與比較」。lint 會檢查字數、洩漏、重複標題。

## 語氣
台灣中文口語、說書的溫暖感，不說教。句子短，逗號處要能自然換氣（字幕只在標點斷行）。少用「欸」等語氣詞（整支最多 1 次）；不用「狂」「絕了」這類過期流行語；可以用耐久的口語（嘴砲、帶風向、潛水）。數字少用，出現就帶單位；專有名詞第一次出現給一句白話。

## fable.json 格式（範例用沉沒成本，**不要照抄內容**）
```json
{
  "version": 1,
  "format": "short",
  "title": "松鼠為什麼不肯放下那顆壞掉的種子",
  "concept": {"name": "沉沒成本謬誤", "aliases": ["沉沒成本", "沈沒成本", "覆水難收謬誤"], "english": ["sunk cost fallacy", "sunk cost"],
              "domain": "行為經濟學", "references": ["Arkes & Blumer (1985), The Psychology of Sunk Cost"]},
  "elements": [
    {"id": "e1", "concept_part": "已經付出、無法回收的成本", "story_ref": "松鼠花了三個冬天照顧那棵枯樹"},
    {"id": "e2", "concept_part": "決策應只看未來的成本與收益", "story_ref": "鄰居問它：今天起再澆水值得嗎"}
  ],
  "hooks": [{"id": "h1", "text": "松鼠為什麼天天對著枯樹說「再一天就好」"}],
  "thumb": [{"hook": "誰會贏？", "image_prompt": "close-up of two small songbirds facing off on a branch, one with spread wings lunging, the other stepping back", "layout": "bottom"}],
  "pronunciation_map": {},
  "beats": [
    {"id": "b1", "act": "hook", "narration": "這個故事在講一個行為經濟學的概念，你猜得到嗎？",
     "must_keep": ["不透露概念名"], "must_avoid": ["沉沒成本", "任何同義詞"],
     "shots": [{"image_prompt": "a small squirrel under a bare tree at dusk, a watering can on the ground beside it, warm lantern light"}]},
    {"id": "b2", "act": "story", "narration": "…（情節，埋下 h1）…", "plants": ["h1"],
     "must_keep": ["松鼠的選擇：繼續澆水"], "must_avoid": ["說教", "概念名"],
     "shots": [{"image_prompt": "..."}, {"image_prompt": "..."}]},
    {"id": "b6", "act": "reveal", "narration": "…這個故事講的，就是沉沒成本謬誤。", "resolves": ["h1"],
     "card": {"title": "沉沒成本謬誤"}, "must_keep": ["說出概念名"], "must_avoid": ["提前解釋要素"],
     "shots": [{"reuse": "b2.1"}]},
    {"id": "b7", "act": "explain", "narration": "…", "maps": ["e1"],
     "card": {"title": "對照", "rows": [{"story": "三個冬天的照顧", "concept": "已付出、收不回的成本"}]},
     "must_keep": ["e1 的對應"], "must_avoid": ["新概念"], "shots": [{"reuse": "b3.1"}]},
    {"id": "b9", "act": "apply", "narration": "…（一句現實應用）…", "must_keep": ["一個真實情境"], "must_avoid": ["投資建議"],
     "shots": [{"reuse": "b1.1"}]}
  ]
}
```
`concept.references` 寫你解釋時依據的教科書／論文（事實查核員會對照）。`title` 是 YouTube 標題：不含概念名，用故事的懸念。

## 退回重做
修改清單點名的句子（id 形如 `c3.2`＝第 3 個 beat 的第 2 句）才改，其他 beat 一字不動；改完照樣跑 lint。事實查核點名的句子（概念解釋的錯誤）只准刪改或加限定詞，不新增句子。
