# 開台片政策審查修正（feat/launch-fixes）

## TL;DR
- 🟢 四支新成片都跑完，停在 **gate_final 等 Leon 核可**；QC 全部 **0 error／0 warn**。
  - CoWoS 8:12（原 6:51）
  - cel 8:03（原 6:42）
  - 九尾狐 8:39
  - 7,722 Short 0:24（重寫為自有講稿 5 拍）
  - manual-kit 與 preview.html 都已產出，縮圖顯示在 preview 上，另附一張手機尺寸縮圖。
- 🟢 審查列的 6 項必修全部處理：
  - 中介層用詞；
  - 縮圖產生器 R2；
  - Short 重剪；
  - cel 口徑註記與「六成業績變差」；
  - 「媒體轉述」移出鉤子，新聞卡分開「媒體原標題」與「本頻道摘要」；
  - 九尾狐 s06：7 個 seed 都畫不出 9 條尾巴，改成在畫面上加註。
- 🟢 頻道差異化寫進頻道設定（`channels/*.yaml` 的 `identity`）、QC 和 deck skill。原創觀點段和角色出現率也會自動檢查。
- 🟢 換聲音只要改設定：改 `.env` 的 `CF_<CH>_VOICE_ID` 或 `CF_FISH_AUDIO_MODEL`（預設 s2.1-pro），再執行 `produce.py run … --allow-paid`，整片就會重配。本輪為了跟舊音檔一致，固定用 `speech-1.5`（見 §5）。
- 🟢 pytest：1 failed（基準就失敗的 `test_multi_provider…returns_first_provider_results`）／1166 passed／1 skipped。

## 1. 產物

| 片 | run-dir（worktree 下的 `output/`，gitignored） | 片長 前→後 | QC | 預覽頁 |
|---|---|---|---|---|
| CoWoS（晶片貓） | `output/cowos-chipcat` | 411 s → **492.3 s** | 0/0 | `output/cowos-chipcat/upload/manual/preview.html` |
| 動畫產業（賽璐璐） | `output/cel-ep1` | 402 s → **482.6 s** | 0/0 | `output/cel-ep1/upload/manual/preview.html` |
| 九尾狐（妖怪溯源所） | `output/yokai-kyubi-launch`（以 feat/ai-motion 的 run-dir 為底） | 519.1 s（不變） | 0/0 | `output/yokai-kyubi-launch/upload/manual/preview.html` |
| 7,722 Short（晶片貓） | `output/chipcat-7722-launch` | 21.1 s → **24.3 s** | 0/0 | `output/chipcat-7722-launch/upload/manual/preview.html` |

- 每支片的 gate_final 都**沒有代核**。核可指令：`python scripts/produce.py approve --run-dir <run-dir> --gate final`
- 前面幾道閘門由我以 `claude-launch-fixes` 身分核可，每一筆都附理由。依前例處理：
  - article：只有 CoWoS 改了一行；
  - deck：四支都核了；
  - media：每支都抽格看過；
  - script：Short 新增的閘門。
- 九尾狐和 cel 沒有角色 rig，成片檔名仍是 `assembly/draft.mp4`（manual-kit 用的就是這個檔）。審查 C3／C4 要求的「final.mp4」，實際上等的是 final gate 核可，不是檔名。

## 2. 每條修正的前後對照（圖在 `docs/design/launch-fixes/`）

| # | 修正 | 做法 | 對照圖 |
|---|---|---|---|
| 1 | CoWoS s09 與 Short 的「超級載板」 | 改為「9 倍光罩中介層，面積 7,722 mm²，約 8.8 公分見方」，並同步改 heading、caption、旁白和 article。子代理查證：IFTLE 615 原文是 interposer，基板是「超過 120×120 mm」🟢。s18 的「載板」仍指 ABF 基板，全片 deck 已沒有「超級載板」🟢 | `cowos_s09_interposer.jpg` |
| 2 | 縮圖 | 新增 `thumbnail.json` → `scripts/make_thumbnail.py`。晶片貓頻道用 Route A 第一輪的驚訝貓加「CoWoS 卡住 AI？」；妖怪頻道用北齋〈九尾狐〉（CC0）加「九尾狐原本會吃人」；cel 用品牌主視覺（24 格底片）加「動畫賣爆 公司還虧？」和「6成 業績變差」。大字都在 10 字以內，promise 都在前 60 秒的講稿裡兌現（QC 檢查）。Short 的封面是 beat 1 首頁，貓在畫面裡 | `thumb_cowos.jpg`、`thumb_cel.jpg`、`thumb_yokai.jpg` |
| 3 | 7,722 Short | 改成**自有講稿**，共 5 拍（見 §4）：鉤子 →「1 張光罩 → 3.3 → 5.5 → 9 倍」方塊長大 → 旁白說出「8.8 乘 8.8 公分」，並放悠遊卡等比對照 → 12 吋晶圓排 5 片（本頻道幾何粗估）→ 導流。貓在每一拍都出現在畫面下半部；畫面靜止最長 2.6 秒（QC `short_motion`） | `short_7722.jpg` |
| 4 | cel s10 | caption 改為「業界市場 ÷ 廣義市場，2024 年（本頻道依兩項不同口徑資料估算）」，s10 標為 take。s03 的旁白和 heading 改成「六成業績變差」 | `cel_s10_note.jpg` |
| 5 | CoWoS 開頭的「這是媒體轉述」 | 拿掉 s02 旁白裡那句，改說「據日經報導…」，媒體轉述的說明放在卡片小字：「媒體轉述，非逐字引言」。新聞卡分兩層：「媒體原標題」是原文，標題已抓回（例：*TSMC warns AI chip crunch will last another 18 months*）；「本頻道摘要」是我們自己寫的。cel 的 6 張新聞卡也一樣處理 | `cowos_s02_card.jpg`、`cel_c1_mappa.jpg` |
| 6 | 九尾狐 s06 的尾巴數 | Z-Image 重生 7 次（seed 1/2/3/7/11/23/42），數到的尾巴是 5–7 條，**沒有一張是 9 條**，候選圖在 job tmp `s06/`。所以保留原圖，沿用 ai-motion 已 bake 好的 Wan 片段，在徽章旁加註「AI 示意圖｜尾數為示意，原典記載九尾」（新欄位 `media.ai_note`） | `yokai_s06_note.jpg` |

另外修了兩處（審查沒有列）：
- CoWoS k4 原本抓到的 Pexels 854765，畫面是一篇**可讀的西文新聞**，也就是別人的內容，上面還有一個無關的 60%。依 deck skill 的 stock 規則剔除，改用抽象倒數計時（Pexels 31968425）🟢（看圖確認）。
- 舊 Short 的「這是多大？」字很小，原因找到了：Short 模板用了品牌 CSS 沒有定義的 `var(--font-body)`，字體退回瀏覽器預設的小字。新模板已改用 `--font-heading` 🟢。

## 3. 片長：補了什麼（不灌水）

- **CoWoS**：新增「晶片貓的算盤」段，共 3 張 take，加上結論前 1 張。
  - k1 一片晶圓排得下幾片：自算一片 12 吋晶圓扣邊 3 mm，以正方形中介層排，約 70→17→10→5 片（P100 時代約 830 mm² → 3.3× → 5.5× → 9×）。腳本是 `docs/launch-fixes/interposer_per_wafer.py`，畫面和旁白都標「本頻道幾何粗估」🟢。
  - k2 產能翻倍，晶片不一定翻倍。
  - k3 晶片貓的三個判斷。
  - k4 看新聞時盯這三個數字。
  - 結果 492.3 s（8:12）。
- **cel**：新增「一個實驗：製作公司自己出資」段。
  - c1 MAPPA《鏈鋸人》不組委員會、100% 自己出資（ANN 2022-07-11）。
  - c2 自己出資的帳：東洋經濟訪談「收支完全成功」，藍光首週約 1,700 多套（ANN 引 Oricon）。
  - c2b 劇場版上映 103 天票房破 100 億日圓。旁白明講：電影的版權標示是 MAPPA／CHAINSAW MAN PROJECT，**電影是否 100% 由 MAPPA 出資查不到**，所以票房不能算成 MAPPA 一家的收入。
  - c3 研究室的看法。
  - 結果 482.6 s（8:03）。距 8:00 只多 2.6 秒，之後若剪短任何一處就會掉到 8 分以下 🟡。
- 頻道目標改成 `target_seconds [420,600]`、`goal_seconds 480`，三個長片頻道相同。低於 8:00 時 QC 給 warn。

## 4. 頻道差異化，以及新增的規則和 QC

**頻道設定**（`channels/{chipcat,cel,yokai}.yaml` 的 `identity`）：

| | 晶片貓 | 賽璐璐研究室 | 妖怪溯源所 |
|---|---|---|---|
| 開場（前 3 張必須唸出） | 「我是晶片貓」 | 「這裡是賽璐璐研究室」＋ CUT 01 兩則新聞 | 「最早的原典」（你以為 vs 原典） |
| 觀點段名稱 | 晶片貓的判斷 | 研究室的看法 | 溯源所的解讀 |
| 片尾（最後一張必須唸出） | 「我們下一關見」 | 「這卷帳本先對到這裡」 | 「妖怪溯源所」 |
| 說明欄 header | 【晶片貓拆解報告】 | 【賽璐璐研究室・產業帳本】 | 【妖怪溯源所・原典追蹤】 |
| 來源標籤 | 這集查過的資料（媒體報導、法說會、技術文件） | 帳本出處（協會報告、財報、官方調查） | 原典與參考文獻 |
| footer | 只拆產業、不報明牌… | 不使用動畫原片、PV 或截圖… | 原典引自公共領域版本… |

**自動檢查**（`production/channel_rules.py`；policy 步驟遇到 error 會擋，QC 會再跑一次）：
- `identity_opening`／`identity_outro`：開場與片尾簽名必須出現。
- `template_phrase`：「用 N 張圖」「我先把結論放在這裡」「所有數字附來源」等句子，不論出現在旁白或說明欄都會報錯。
- `foreign_phrase`：不能出現別的頻道的開場或片尾簽名。
- `commentary`：至少 1 張 `take: true`，且 take 旁白合計 ≥ 80 字。
- `mascot_presence`：有 rig 的頻道，角色要出現在 ≥ 80% 的投影片。
- `thumbnail`／`thumbnail_promise`：見 §2-2。
- `short_motion`：Short 每拍畫面靜止 ≤ 3 秒。
- `duration_goal`：片長低於 8:00 給 warn。
- 跨頻道撞句的測試：`identity.collisions` 檢查四個頻道設定之間有沒有重複句（加了對照組）。

**偵測器對照組（反例）**：
- 舊 cel deck 跑出 3 個 error：模板句 ×4、缺片尾、缺 take。
- 縮圖 promise 在 cel 重配前是 error，因為講稿當時還沒有「六成業績變差」，重配後轉為 ok 🟢。

**deck skill**（`.claude/skills/deck/SKILL.md`）新增：
- 「Channel identity, own view, news cards」6 條；
- 「Thumbnail」一節；
- AI 圖規則第 4 條（`ai_note`）；
- 片長規則改為 7–10 分、目標 ≥8:00，字速改用 Fish 實測值（lint 估算由 4.5 改為 5.5 字/秒）。

**還不能自動判斷、留給人看的**：
- 觀點段「有沒有道理」；
- 縮圖在手機上清不清楚（產生器另出 320×180 版，放在 preview 上）；
- stock 畫面有沒有可讀文字或品牌。k4 就是我人工抽格才抓到的 🟡。

## 5. 配音

- 改動的場景都用**現行頻道聲音**重配：chipcat 和 cel 是 `bbfff76f…`（江湖），模型固定 `speech-1.5`，也就是舊音檔用的 SDK 預設模型。沒有改動的場景直接重用舊音檔。
- 用量：Fish 共 30 次呼叫、3,120 字（從各 run 的 `logs/voice.log` 統計 🟢）。
  - CoWoS 10 次：s01、s02、s03、s09、s24、k1–k4，以及因為場次號往後移而重配的 s23。
  - cel 15 次：分兩輪，第二輪是為了補到 8 分鐘。
  - Short 5 次；九尾狐 0 次。
- 舊紀錄沒有記錄 model。程式現在把它們視為 `speech-1.5`，所以固定 `CF_FISH_AUDIO_MODEL=speech-1.5` 時會重用舊音檔，改成 `s2.1-pro` 時會整片重配（有測試）。
- **Leon 選好新聲音後**，在主 checkout 的 `.env` 設定 `CF_CHIPCAT_VOICE_ID`／`CF_CEL_VOICE_ID`／`CF_YOKAI_VOICE_ID`（必要時加 `CF_FISH_AUDIO_MODEL=s2.1-pro`），然後依序執行：

  ```
  python scripts/produce.py run --run-dir output/cowos-chipcat --allow-paid --max-load 8
  python scripts/produce.py run --run-dir output/cel-ep1 --allow-paid --max-load 8
  python scripts/produce.py run --run-dir output/yokai-kyubi-launch --allow-paid --max-load 8
  python scripts/produce.py run --run-dir output/chipcat-7722-launch --allow-paid --max-load 8
  ```

  - voice 指紋包含 provider、model、voice_id，換了任何一項都會整片重配。
  - 時長改變後 media 會重跑，所以 gate_media 要重新核可，gate_final 也要。
  - 換聲音之後片長會變。cel 只比 8:00 多 2.6 秒，換聲音後要再看一次片長。

## 6. 程式改動（commits）

| commit | 內容 |
|---|---|
| `1dce6b3` | Fish 模型可設定（`CF_FISH_AUDIO_MODEL`、頻道 yaml 的 `voice.model`），模型納入 voice 指紋，舊紀錄視為 speech-1.5 |
| `a12b68b` | cherry-pick Route A 第一輪 rig（`301bd21`），成片的貓和縮圖的貓是同一隻 |
| `1f38777` | 頻道 identity、channel_rules、`Slide.take`、`goal_seconds`、新聞卡原標題、縮圖產生器（含 runner 步驟 `thumbnail_spec`／`thumbnail`、preview 手機尺寸縮圖） |
| merge `feat/ai-motion`（9e7de1d） | 依 orchestrator 指示在渲染前合併。只有 CLAIMS.jsonl 衝突，保留本分支的版本 |
| `shorts` commit | scripted Short：spec 的 `beats`／`answer`、`short_script` → `gate_script` → voice → cut、每拍一頁動畫、`short_motion` QC、`produce.py short-from-long --beats`；`media.ai_note`；deck skill 規則；三支 deck 的修改腳本 |
| 本 commit | 前後對照圖、`interposer_per_wafer.py`、`before_after.py`、本報告 |

新增測試：
- `test_launch_rules.py` 19 支
- `test_production_shorts_scripted.py` 12 支（含參數化共 12 個案例）
- voice／runner 7 支
- 既有 QC 測試的斷言依新規則更新

## 7. 還沒做的，以及要 Leon 決定的

1. **gate_final ×4**：請看 preview.html 後再核可。
2. **頻道片尾畫面**：目前只有口播簽名和 yaml 的 `endcard` 句子，沒有真的在成片尾端接一張片尾卡。YouTube 結束畫面需要 5–20 秒的空間，要另外做 🟡。
3. **cel 只比 8:00 多 2.6 秒**（見 §3）。
4. **CoWoS 的 s23 也被重配**：插入新投影片後場次號往後移，s23 的文字沒變但被重唸一次。之後可以把音檔重用改成以 slide id 對應，現在是以場次號對應。
5. stock 片段有沒有可讀文字和品牌，仍然只能靠人看。這次的 k4 就是例子；可以考慮加 OCR 檢查。
6. 換聲音的試聽和決定在另一個流程。本輪沒有換聲音。
7. 審查 D 部分的營運建議（發片節奏、錯開開台、互推）都不在本任務範圍內。

## 8. 清理與副作用

- `output/` 下的 run-dir 都 gitignored，是交付物，保留：
  - 新的有 `chipcat-7722-launch`、`yokai-kyubi-launch`；
  - 舊的有 `yokai-kyubi`（較早的副本，只用來產縮圖草稿）和 `chipcat-7722`（舊版 Short）。這兩個可以刪，但 `rm` 在 deny 清單裡，留給 orchestrator。
- job tmp（`~/.claude/jobs/dcda373f/tmp/`）裡有 patch 腳本、s06 候選圖 7 張、beat 預覽，會隨 job 一起清除。
- 背景程序：我停掉兩個自己的 runner。一個是 Short 用舊 spec 等待中的 run，另一個是 CoWoS 發現 k4 問題時的 run。兩者都在 render lock 之前或 assembly 中途停下，之後已經用新 spec 和新 deck 重跑完成。
- 外部存取：
  - 子代理用 WebFetch 抓新聞原標題，並用 WebSearch 查證中介層、MAPPA 相關事實；
  - 我用 python urllib 抓了 phileweb 一頁（Shift_JIS）取得 Gainax 標題；
  - Pexels 免費 API；
  - Fish TTS 共 30 次。
- 沒有 push、沒有開瀏覽器、沒有上傳。
