# REPORT — 寓言學堂（暫名；channel id `fable`）：3 支 Shorts＋1 支中片，做到 gate_final 前

分支 `worktree-cf-fable`（自 `worktree-cf-revisual` ac0392c 快進，merge `worktree-cf-stock-footage`）。未 push、未付費服務、未開瀏覽器、未上傳。等級：🟢 本機實測 ／ 🟡 有保留 ／ 🔴 未驗。

## TL;DR
- 🟢 四支都做到 qc（0 error）：Shorts 83.3／91.7／83.5 s（直式 1080×1920），中片 288.6 s（橫式 1920×1080）。成片在 `artifacts/fable/`（Shorts 直接放；中片 540p 兩段 6.3／6.3 MB）。
- 🟢 新頻道 `fable`：自己的 pipeline（`Pipeline.FABLE`）、腳本 skill `/fable-script`、程式檢查揭曉規則（`scripts/fable.py lint`）、繪本＋視差＋概念圖解版型、兩種評審（腳本評審評一次＋自動改一次；概念正確性查核 ≥0.5 才算錯、自動修一次）。
- 🔴→🟡 **最大的品質問題：故事太早被猜到**。12 位合成觀眾裡 11 位在揭曉前就猜對（見 §3），最早 ~8 s。程式只能保證「名字不在揭曉前出現」，擋不住「情節本身就是經典案例」。選概念時偏經典案例（檸檬市場、確認偏誤、梯度下降）是主因；這是下一輪要改的重點。
- 🟡 沒有人耳聽過任何成片（旁白、配樂）、沒有人看完整支成片；只抽格看過。
- 費用：雲端（`claude -p`，名目）合計 **$4.37**（預算 4×$5＝$20 未觸及）；本機 $0。

## 1. 頻道設定與名稱候選
`channels/fable.yaml`。名稱候選：**寓言學堂**（暫用）／原來如此／先聽個故事。台灣中文、一般觀眾；領域跨經濟、資工、心理、生物（演化賽局），之後可加物理、數學、哲學。格式：Shorts 9:16 60–90 s（寓言約 40–50 s＋揭曉與解釋約 25–35 s）；中片 16:9 4–6 分。`format` 預設是 Shorts，中片由 `fable.json` 的 `format: mid` 覆寫（QC 改查 16:9、230–380 s）。brand 新增 `fable`（品牌登記用，不渲染投影片）。

## 2. 腳本 skill 與揭曉檢查
- `.claude/skills/fable-script/SKILL.md`：結構 hook → story（原創動物／器物角色、一個選擇與代價、2–3 條伏筆）→ reveal → explain（情節逐一對應概念要素）→ apply（一句現實應用）；**每個 beat 先寫 must_keep／must_avoid**（InkOS 借鏡，只借設計、未用其程式碼——AGPL）。
- `src/content_farm/production/fable/check.py`（`scripts/fable.py lint`，25 項單元測試在 `tests/unit/test_fable.py`）：
  - **揭曉規則**：概念名、同義詞、英文名在揭曉前不得出現在標題、hook、寓言旁白、圖片提示詞、card（逐字比對，去空白、不分大小寫）。
  - **伏筆帳本**：每條 hook 在揭曉前埋下（`plants`）、在揭曉（含）之後收掉（`resolves`）；每個概念要素（elements）至少被一個 explain beat 對應（`maps`）。
  - 結構（act 順序、hook 一句且是問句／邀請猜）、長度估計（Short 全片 55–88 s、寓言 36–62 s、解釋 16–38 s；中片 230–370 s）、每個 beat 的畫面至少每 8 秒換一張、圖片提示詞禁人物字眼與會被畫成既有電影角色的描述（見 §6）、語氣（不用「狂」「絕了」，「欸」≤1）。
- 🟡 程式測得的是估計秒數；實測見 §5。

## 3. 每支的概念、評審與觀眾「猜到時間點」
觀眾（3 位合成觀眾：上班族、碩士生、大一文組）被要求先只讀揭曉前的 part1、寫下猜測與「第一次猜到的那一句」，再讀 part2 給揭曉驚喜分（0–10；`scripts/fable.py guesses`，秒數＝猜到那句之前的旁白字數÷5.5 字／秒，🟡 是估計不是實測時間）。

| 片 | 概念（領域） | 長度 | 猜到的時間點（上班族／碩士生／大一生） | 揭曉驚喜（0–10） |
|---|---|---|---|---|
| fable-asymmetry-short | 資訊不對稱（經濟學） | 83.3 s | ~15 s 對／~15 s 對／~32 s **猜成劣幣驅逐良幣（錯）** | 2／2／4 |
| fable-gradient-short | 梯度下降（資訊科學） | 91.7 s | ~17 s 對／~17 s 對／~17 s 對 | 2／1／3 |
| fable-confirmation-short | 確認偏誤（心理學） | 83.5 s | ~8 s 對／~8 s 對／~20 s 對 | 1／2／3 |
| fable-ess-mid | 演化穩定策略（演化生物學） | 288.6 s | ~93 s 對／~34 s 對／~77 s 對（267 s 稿） | 3／2／3 |

- 🟢 結論：**揭曉的驚喜低（平均 2.3/10）**，故事本身太透明。揭曉前的伏筆有被收（程式檢查）、揭曉規則沒有被違反，但「不說名字」不等於「猜不到」。建議：下一輪選概念時避開「經典案例就是故事本身」的（檸檬市場、確認偏誤），改寫成較遠的比喻場景，或讓 hook 問句帶誤導方向；腳本評審的 writer_story 只給 5–6/10（門檻 6.5，score_only 不擋），修改清單正指向這點。
- 腳本評審（一次＋自動改一次，不重評、不擋）：四支都走了一次自動改稿（`fable_script` producer agent，sonnet · medium）。writer_story 分數 asymmetry 6／gradient 5／confirmation 5.5（均 < 6.5 但依政策放行）；中片分數見 `output/fable-ess-mid/review/`。
- 概念正確性查核（2 位查核員＋仲裁，WebSearch，信心度 ≥0.5 算錯、自動修一次）：asymmetry 確認 2 處（「檸檬市場與資訊不對稱說成同義」「保固歸屬」）→ 已改；gradient、confirmation 第 1 輪通過；ess-mid 確認 1 處 → 已改。🟡 未做第二輪重查（政策如此）。

## 4. 視覺
- 風格統一：**溫暖繪本**（水粉＋鉛筆線，z-image-turbo 本機，`channels/fable.yaml` style_prefix）。四支共 AI 圖：asymmetry 8（其中 7 張重畫過，見 §6）、gradient 8、confirmation 9、ess-mid 32 張，**每個 beat 至少 1 張，全部深度視差**（Depth Anything V2 Small），沒有靜止圖；缺深度工具會直接報錯而不是悄悄用靜止圖。
- **揭曉轉場**：繪本畫面 → `xfade circleopen` 0.7 s → 概念圖解（上／左為同一張圖的視差視窗，下／右為紙色面板：領域＋大字概念名；explain beat 用「故事 → 概念」對照列逐列出現，每 2–3 秒變一次）。
- Wan：**本批沒用**（全部視差；避臉規則留給之後只拍無臉場景鏡頭）。無角色主持人。
- 🟡 版面：中片橫式右側面板偏空、對照列字偏小；Shorts 的對照列已放大（58 px）但未再檢視新版（最後一次檢視為舊字級）。

## 5. 聲音
- 設計：Qwen3-TTS VoiceDesign（`design_voice.py`，seeds 4101–4103）：五十多歲溫暖低柔、略沙啞的女性說書人，台灣口音；挑 **take4103**（`~/.local/share/content-farm-voices/fable-ref.wav`）→ VoxCPM2 複製。
- **和其他頻道的相似度（ECAPA 餘弦，`speaker_sim.py`）**：take4103 對 technews 0.57、chipcat 0.70、cel 0.39、yokai 0.30、ent 0.26、deepsea 0.17。🔴 **對 chipcat 0.70 偏高**（兩個女聲頻道之間原本約 0.44）；三個 take 的最高值 0.80／0.72／0.70，4103 最低。我另排了男聲重設計（seeds 4201–4203）但它在佇列裡被自己的指令列誤判成「外部重程序」而和圖片任務互鎖，停掉後未重排——若要更有區別，需要再做一輪（建議男聲或更年輕的女聲）。
- 語速：參考聲約 3.4 字／秒，原速的 Short 達 142 s；`voice.tempo: 1.55`（不變調）→ 約 5.3 字／秒。🟡 沒人耳聽過加速後的自然度；QC 的讀回檢查有 1 個場景 CER 0.13–0.14（gradient scene_010、ess-mid scene_016，已重生 3 次）。
- 配樂（後期步驟，可關）：新的 `hearth` 預設（F 大調五聲音階、八音盒音色、柔和和聲，本機 numpy 合成、無第三方素材；`audio.synth_bgm: hearth`）。🔴 沒聽過。

## 6. 過程中踩到的問題（已修）
1. 第一批圖：「夜市」提示詞畫出人群與小孩，「狸貓」被畫成吉卜力《龍貓》外形（既有電影角色，IP 風險）。→ style_prefix 加「Only original animal characters: no humans…」、lint 新增人群字眼與 tanuki／round 類字眼檢查、SKILL 說明；asymmetry 6 張＋1 張重畫（舊圖移到 job tmp）。其餘三支用新 prefix 生成，抽格檢視無人物／無仿角色；🟡 中片 32 張中我只逐張看了前 18 張。
2. 事實查核的仲裁在沒有 deck 時讀 `deck.json` 崩潰（`review/rounds.py`）→ 改讀 script 句子。
3. `script.json` 的 visual_hint 原本寫圖片提示詞，重畫圖會讓腳本評審的指紋變動 → 改為只寫 beat 摘要。
4. QC：Short 上限 60 s、16:9 字幕「撞角色欄」檢查不適用本頻道 → 針對 fable 分別放寬為 55–95 s／略過角色欄。
5. 合併衝突：`wan.py` 負向提示詞（revisual 恆開臉部負向、stock-footage 改成頻道政策）取聯集：政策覆寫預設；`test_wan_policy` 期望同步更新。

## 7. 費用與牆鐘
- 雲端（`claude -p` 名目）：asymmetry $1.12、gradient $0.93、confirmation $0.68、ess-mid $1.64＝**$4.37**（評審約 $1.74、產出 agent 約 $2.65；`produce.py usage`）。本機 $0（voice design、TTS、圖、視差、渲染皆本機）。
- 執行（機器，指令步驟牆鐘）：asymmetry 21.2 分、gradient 14.2、confirmation 16.0、ess-mid 48.4（圖 28.0 分、配音 15.7 分、渲染 4.1 分）。voice design 一輪 3 takes 約 2 分執行。
- 排隊：機器被深海 Wan worker 長時間獨佔 GPU。voice design 從排入到完成約 18 分（≈16 分排隊）；圖片任務各等 ~29 分；confirmation／ess-mid 的配音各等 ~27／~34 分；Shorts 因為補 tempo 與重畫又各多一輪排隊（約 10–15 分）。整件工作的牆鐘約 3.5 小時，其中**大部分是排隊**，不是執行。🟡 排隊秒數取自佇列狀態與 log 的估計，沒有逐筆精確計秒。

## 8. 產物
- 成片：`artifacts/fable/fable-asymmetry-short.mp4`、`fable-gradient-short.mp4`、`fable-confirmation-short.mp4`（各 ~23 MB，直式 1080×1920，含配樂）；中片 `fable-ess-mid-part1.mp4`／`part2.mp4`（540p，6.3 MB 各）。（`artifacts/`、`output/` 不 commit。）
- 各 run-dir：`output/fable-{asymmetry-short,gradient-short,confirmation-short,ess-mid}/`（含 `fable.json`、`script.json`、`review/`、`assembly/release.mp4`）。
- 程式：`src/content_farm/production/fable/`、`scripts/fable.py`（lint／prepare／images／render／guesses）、`channels/fable.yaml`、`.claude/skills/fable-script/`。
- 測試：`tests/unit/test_fable.py` 25 項；全套結果見 §9。

## 9. 測試與未做
- 🟢 全套 pytest：**1992 passed, 1 skipped**（最終程式狀態）。排除既有失敗的 `test_multi_provider`（與本工作無關，merge 前就失敗）。
- 🔴 未做：人耳聽感（旁白、配樂）、完整觀看；gate_final 與 package 未跑（停在 qc）；沒上傳、沒 push；男聲重設計；選題階段（題目是我手選的 4 個，沒走選題評審）；Wan。
- 需要 Leon 決定：(a) 聲音是否接受 chipcat 相似度 0.70，或要再做一輪區別更大的；(b) 「太早猜到」要不要改選題策略（避開經典案例）；(c) 名稱。

## 進度紀錄
- 2026-10-24：四支做到 qc 完成、報告寄出。🟡 對話 token 用量沒有量測；未走到需要交接的程度。
