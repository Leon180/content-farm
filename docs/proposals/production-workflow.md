# 提案：四頻道影片生產流程（production workflow）

> 2026-10-15，分支 `feat/production-workflow`（基準 `8907817`，並 merge `design/channel-brands` `ab84f74`）。
> 證據等級：🟢 本機實測可重跑／🟡 只驗到存在或來自他人報告的實測／🔴 推論或估計。
> 已實作部分見文末「已做」，其餘列在 roadmap。

## 0. 一句話

**一支片 = 一個 run-dir + 一個頻道設定檔。** `scripts/produce.py run` 從選題一路跑到 `upload/youtube_meta.json`，
只會停在四種地方：人工閘門、Claude 要寫的東西還沒寫、付費步驟沒授權、某一步失敗。每次停下都會印出下一條指令，並產生一頁審核 HTML。
再跑一次同一條指令就從停下的地方接續，已完成且輸入沒變的步驟會跳過。

---

## 1. 現況盤點：CoWoS v2 一支片從選題到上傳

來源：`REPORT-explainer-v2.md` 第 4、7 節的實跑紀錄（10 核 Mac，負載 18–36），加上本分支用 runner 重跑的數字（第 5 節）。

| # | 步驟 | 誰做 | 指令／skill | 耗時（實測） | 付費 | 常見失敗 | 人工閘門 |
|---|---|---|---|---|---|---|---|
| 1 | 選題 | Leon＋Claude | `/topics`（短片用），長片靠人挑 | 無紀錄 | 否 | 沒有 backlog，題目散在對話裡 | 是（人決定） |
| 2 | 研究成文章 | Claude | `/article` → `article.md`、`sources.json`；`check_article.py` | 未計時（Claude session） | Claude 用量 | 來源只有二手報導；八卦沒出處 | **閘門 0：文章審稿** |
| 3 | 簡報大綱 | Claude | `/deck-outline` → `deck_outline.json` | 未計時 | Claude 用量 | media 配比不足 | 閘門 1：大綱 |
| 4 | 講稿＋deck | Claude | `/deck` → `deck.json`；`deck_to_script.py --strict` | 0.3 s（轉換） | Claude 用量 | lint 擋 title card 來源欄位 | 閘門 2：講稿 |
| 5 | 投影片渲染 | 自動 | `render_slides.py` | 5.6 s 🟢 | 否 | 文字溢出（會 exit 1） | 閘門 3：contact sheet |
| 6 | 配音＋字幕對齊 | 自動 | `run_stage.py --stage voice`（需手動帶 `CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE=20`） | 33 s（mock）🟢 | **Fish Audio 付費** | 忘了帶字幕寬度環境變數 → 字幕壓到貓 | skill 規定付費前要 Leon 放行 |
| 7 | B-roll／動態／AI 圖 | 自動＋人 | `media_to_visual.py`；AI 圖要人開 Chrome＋Gemini 手動生 | 330 s（首跑）／199 s（快取）🟢 | Pexels 免費 | stock 離題（機車、藥廠）、**有品牌 logo**；AI 圖缺→佔位 | 無正式閘門，靠 contact sheet 橘框 |
| 8 | 合成 | 自動 | `run_stage.py --stage assembly_timeline` | 121 s 🟢 | 否 | 時間軸檔名錯→黑幀（已自動補） | 無 |
| 9 | 晶片貓疊加 | 自動 | `mascot_overlay.py --workers 2` | 409 s 🟢 | 否 | 字幕太寬→拒絕疊加 | 無 |
| 10 | 品質檢查 | 人工臨時做 | ffprobe、blackdetect 手動下指令 | 數秒 | 否 | 沒做就上 | 無 |
| 11 | 縮圖、上傳資料 | 自動＋人 | `/thumbnail`、`/prepareupload` | 數秒 | 否 | **video_path 指向 draft.mp4 不是 final.mp4**；credits 要手貼；章節用估算時間 | 手改 `youtube_meta.json` |
| 12 | 上傳 | 自動 | `/upload` | 依網速 | YouTube 配額 | 沒有排程發佈、沒有 AI 揭露欄位、只支援一個頻道的 token | 上傳前確認 |
| 13 | 歸檔 | 自動 | `/drive`（會刪本地 run-dir） | 依網速 | 否 | 不可逆 | 需要人確認 |

**自動化部分的合計**：首跑 ≈ 900 s ≈ 15 分（不含 Claude 寫作與人工）。因為 B-roll 換片，實際 media→assembly→mascot 跑了 3／2／2 輪，牆鐘約 40 分。🟢

**盤點出的五個斷點**（本提案主要要解的）：
1. 步驟之間靠人記指令與環境變數（第 6 步的 `=20`、mock 的 dummy key）。
2. 沒有狀態：哪一步做過、用的是哪一版 deck，只能看檔案時間猜。
3. 閘門只是 skill 文件裡的一句話，沒有紀錄，也不知道「核可之後檔案有沒有被改」。
4. 上傳資料要手補（final.mp4、credits、章節時間、AI 揭露、排程）。
5. 所有東西都假設只有一個頻道（品牌、YouTube token、選題）。

---

## 2. 頻道設定檔 `channels/<code>.yaml`（已做 🟢）

每個頻道一份，`content_farm.production.channels.Channel` 用 pydantic 嚴格驗證（多一個欄位就報錯）。

| 欄位 | 內容 | 例：晶片貓 |
|---|---|---|
| `code`／`name`／`line` | 代碼、頻道名、類型 | chipcat／晶片貓／台灣科技產業拆解 |
| `pipeline` | `explainer`（文章→deck→…）或 `shorts_skit`（劇本→配音→小劇場） | explainer |
| `brand` | `explainer/brands.py` 註冊的品牌，決定投影片／卡片 CSS | chipcat |
| `deck_category` | deck 的 category（explainer 必填） | tech |
| `mascot` | 名稱、`ref`（角色 id，交給 mascot 模組）、`rig_ready`（false＝跳過疊加） | 晶片貓（本尊）／chipcat／true |
| `voice` | TTS 供應商＋**存 voice id 的環境變數名** | fish_audio／`CF_CHIPCAT_VOICE_ID` |
| `topic_categories` | 題材類別 | 半導體、電子供應鏈… |
| `format` | 長／短、16:9／9:16、目標秒數區間（QC 用） | long／16:9／420–660 |
| `cadence` | 每週長片數、Shorts 數（可小數）、發片星期、時間、時區、`lead_days` | 1／2／thu／19:00／Asia/Taipei／7 |
| `shorts_strategy` | 文字描述 | 「一個數字」：從長片切 45 秒 |
| `media` | stock／ai_image／artwork 是否允許、artwork 是否要授權、`source_footage`（**驗證器強制為 false**） | stock、ai_image |
| `gates` | 要停的人工閘門；`final` 不可移除，不屬於該 pipeline 的閘門會被拒絕 | article, deck, media, final |
| `youtube` | **只放環境變數名**：共用 OAuth client（`CF_YOUTUBE_CLIENT_ID/SECRET`，沿用現有設定）＋每頻道 refresh token（`CF_YT_<CODE>_REFRESH_TOKEN`）＋頻道 id；`ai_disclosure`；預設隱私 | |
| `notes` | 頻道規則備忘 | 不給投資建議 |

驗證器會擋的錯（都有測試）：把 token 值當成變數名、未知品牌、移除 final 閘門、閘門不屬於 pipeline、開啟 `source_footage`、檔名和 code 不一致、未知欄位。

### 四個頻道的差異如何表達

| 差異 | 晶片貓 | 妖怪溯源所 | 晶片貓下班了 | 賽璐璐研究室 |
|---|---|---|---|---|
| pipeline | explainer | explainer | **shorts_skit**（沒有文章、沒有 deck） | explainer |
| 閘門 | 文章、deck、素材、成片 | 同左 | **劇本、成片** | 文章、deck、素材、成片 |
| 素材 | stock＋AI 圖 | **artwork（必須 CC0／PD＋授權網址）**＋AI 水墨；**不用 stock** | 只用角色與自製素材 | stock（通用畫面）＋AI 圖；**不用原片** |
| 角色 | 晶片貓（rig 已有） | 說書貓（換裝未做 → 跳過疊加） | 下班貓＋PM 狗（未做） | 格仔（新角色未做） |
| 片長 | 7–11 分 | 8–12 分 | 20–50 秒直式 | 8–12 分 |
| 發片 | 每週 1 長＋2 短 | 隔週 1 長＋每週 1 短 | 每週 3 短 | 隔週 1 長＋每週 1 短 |

- 搞笑 Shorts 沒有文章：`shorts_skit` 的步驟表根本沒有 `article`／`deck`，不是「跳過」。
- 神話 artwork 授權：`qc.credits_findings` 對 `kind: artwork` 的 credit 要求 `license_url`，授權字串含 NC／non-commercial 一律 error（大英博物館 CC BY-NC-SA 會被擋）。`media` 種類 `artwork` 本身還沒進 deck schema（roadmap R3）。
- 動漫不用原片：`source_footage` 在 schema 層就不能設 true；deck 若要 stock 以外的影片來源，政策檢查（`policy` 步驟）會在 deck 審稿前就擋下。

---

## 3. 選題池與排程（已做基本版 🟢）

- **選題池**：`channels/backlog/<code>.yaml`，每個題目有 `id`、`title`、`kind`（long／short）、`status`（idea → researching → ready → in_production → published／dropped）、`priority`（1–5）、可選 `deadline`（新聞題）。目前只放了晶片貓的範例。
- **發片日曆**：`schedule.slots_for_week(channel, year, week)`。小數頻率用 `floor((w+1)·rate) − floor(w·rate)`，0.5 就是隔週，長期平均精確且可重算（有測試）。
- **「這週做哪幾支」**：`produce.py plan --week 2026-W43` 對每個時段挑題：
  1. 只挑對應 kind 的題目，已發佈／製作中／放棄的不挑；
  2. 有 deadline 且在發片日前過期的不挑；
  3. 排序：`ready` > `researching` > `idea`，再看 deadline 早晚，再看 priority；
  4. 開工日（發片日 − `lead_days`）已過的時段，只接受 `ready` 的題目，否則標「來不及」。
- 實際輸出（2026-10-15 跑 W43）：晶片貓三個時段都有題（長片挑到 `hbm`，⚠ 只到 researching）；其他三個頻道的 backlog 是空的，全部標「（空）」。🟢

**每週例行**（建議週日晚上 15 分鐘）：跑 `plan` → 把被挑中的題目改成 `in_production` → 對每支 `produce.py run --channel … --run-dir output/<題目> --publish-at <時段>`。

---

## 4. 一鍵執行與人工閘門（已做 🟢）

### 步驟表（explainer）

| 步驟 | 種類 | 做什麼 | 跳過條件 |
|---|---|---|---|
| `article` | agent | 檢查 `article.md`＋`sources.json` 存在，跑 `check_article.py` | 檔案指紋沒變 |
| `gate_article` | 閘門 | 文章審稿 | 已核可且指紋相同 |
| `deck` | agent | 檢查 `deck.json`，跑 `deck_to_script.py --strict` | deck 指紋沒變（**不會**覆寫 voice 寫回的時長） |
| `policy` | internal | deck 要的 media 是否在頻道允許範圍內 | 每次都跑（毫秒級） |
| `slides` | cmd | `render_slides.py --brand <頻道品牌>` | deck 沒變 |
| `gate_deck` | 閘門 | deck＋contact sheet 審稿 | |
| `voice` | cmd，**付費** | `run_stage voice`，自動帶字幕寬度 20；`--mock-voice` 改用 macOS say | 沒有 `--allow-paid` 也沒有 `--mock-voice` 就停 |
| `media` | cmd，重 | `media_to_visual.py --brand … --replace --require-measured` | 投影片／音檔／AI 圖都沒變 |
| `gate_media` | 閘門 | B-roll、AI 圖、授權 | |
| `assembly` | cmd，重 | `run_stage assembly_timeline` | |
| `mascot` | cmd，重 | `mascot_overlay.py`；頻道 `rig_ready: false` 就不在步驟表裡 | |
| `qc` | internal | 自動品質檢查（第 7 節），寫 `qc/qc_report.json` | |
| `gate_final` | 閘門 | 成片審看；QC 有 error 時 approve 必須 `--override "理由"` | |
| `package` | internal | 寫 `upload/youtube_meta.json`（第 6 節） | |

`shorts_skit`：`skit_script`（agent）→ `gate_script` → `voice` → `skit_render`（agent，渲染器未做）→ `qc` → `gate_final` → `package`。

### 閘門怎麼運作

- runner 停在閘門時寫兩個檔：
  - `review/<gate>.html`：一頁自足的審核頁（亮暗色、手機可讀），上方是「要判斷的事」清單與可一鍵複製的 approve／reject 指令，下方是這個閘門要看的東西（文章全文與來源表；contact sheet 與逐張講稿；media contact sheet、每張實際用了什麼、credits 與 pending；成片播放器與 QC 表）。所有來自 run 的文字都經過 HTML escape（有測試）。
  - `review/<gate>.decision.json`：給面板決策 inbox 用的機器可讀項目：`{kind: "production_gate", channel, run_dir, gate, title, fingerprint, status, review_page, approve_cmd, reject_cmd, checklist}`。`produce.py inbox --root output` 會列出所有 `status: pending` 的項目。
- **核可綁指紋**：`approve` 時把這個閘門涵蓋的檔案（例如 deck 閘門 = `deck.json`＋`slides/contact_sheet.png`）做 sha256 指紋存進 `production.json`。之後任何一個檔案變了，runner 會再停在這個閘門，訊息是「核可後檔案已變更」。退回（reject）後沒改檔就再跑，會一直停住並顯示退回理由；改了才重新進 inbox。
- 誰核可的寫在 `by`（預設 leon）。本次驗證跑的核可都標 `by: claude-validation`。

### 面板決策 inbox 介面（只寫設計，沒改面板）

面板只需要：
1. 掃 `output/*/review/*.decision.json`，列 `status == "pending"`，依 `channel`、`gate` 分組。
2. 每一項顯示 `title`、`checklist`，用 iframe 或新分頁開 `review_page`。
3. 「核可」「退回」兩個按鈕執行 `approve_cmd`／`reject_cmd`（退回時讓人填 `--note`）。成片閘門 QC 有 error 時，核可要求填 `--override` 理由。
4. 執行後檔案的 `status` 會變成 `approved`／`rejected`，面板重新整理即可；之後要繼續跑就執行 `produce.py run --run-dir …`（可設成核可後自動觸發）。

不需要面板直接讀寫 `production.json`。

---

## 5. 批次與並行：算力與記憶體

### 量到的數字

- 機器：10 核、32 GB RAM；本 session 開始時 swap 7.0 GB 用了 5.4 GB（≈ 76%）🟢。
- 每支長片的本機算力（REPORT-explainer-v2 首跑，負載 18–36）🟢：slides 6 s、voice 33 s（mock）、media 199–330 s、assembly 117–173 s、mascot 400–409 s（2 workers）→ **約 12–15 分鐘牆鐘**。
- 本分支用 runner 重跑（2026-10-15，負載約 12）🟢：slides 4.4 s、voice 28.3 s、media 424.7 s（stock 全走快取）、assembly 109.5 s、mascot 397.5 s、QC 8.0 s → **合計約 16 分鐘**。
- 重的三步（media 開 Chromium 擷取動畫、assembly 用 ffmpeg 編碼、mascot 渲染 15k 幀）都是吃 CPU＋記憶體的，任兩個同時跑會一起拖慢並推高 swap。🔴（推論；沒有做並行對照實驗）

### 排程策略（已做前兩條）

1. **全機一把渲染鎖**（`~/.cache/content-farm/render.lock`，`fcntl.flock`）：media／assembly／mascot 一次只會有一支片在跑；其他 run 在鎖上等。輕的步驟（文章檢查、投影片、配音、QC、閘門）不受限，所以多支片可以同時推進到各自的閘門。🟢
2. **負載閥門**：`--max-load N`，重步驟開始前若 1 分鐘負載 > N 就每 30 秒等一次。建議 N = 12（≈ 核心數 1.2 倍）。mascot workers 預設 2（v2 實測負載高時從 4 降到 2）。🟢（機制）／🔴（數值）
3. **夜間批次**（roadmap R6）：白天只跑到 `gate_deck`（人要看的東西），配音之後的重步驟排到半夜，用 `launchd` 或 cron 對每個等待中的 run 跑 `produce.py run`。
4. **磁碟**：每支片中間檔（`mascot.mov` ProRes 2.2 GB、media clips）要在成片核可後清掉（roadmap R7）。

### 容量估算 🔴

渲染鎖下一支長片佔用約 12–15 分；四個頻道照提案頻率每週 2 支長片＋7 支 Shorts（Shorts 渲染估 1–2 分），**每週算力 < 1 小時**。瓶頸在人，不在機器。

---

## 6. 上傳與發佈（已做 🟢）

`package` 步驟寫 `upload/youtube_meta.json`，鍵與 `/prepareupload` 相同，`/upload` 不用改流程，另外補上：

| 項目 | 以前 | 現在 |
|---|---|---|
| 影片 | `assembly_artifact.json` 指的 `draft.mp4`（沒有晶片貓） | `assembly/final.mp4`（沒有就退回 draft） |
| 章節 | 用 deck_to_script 的估算時長 | 用 voice 寫回的實測時長重算；少於 3 章、首章不在 0:00、任一章 < 10 秒就不輸出 |
| 授權 | 手動把 `credits.json` 的 `description_text` 貼進說明欄 | 自動附在說明欄 |
| AI 揭露 | 說明欄一行字 | 說明欄一行＋`contains_synthetic_media: true`，上傳時送 `status.containsSyntheticMedia` |
| 排程 | 沒有 | `--publish-at` 或排程表 → `publish_at`，上傳時送 `status.publishAt` 並強制 private |
| 多頻道 | 只有一組 `CF_YOUTUBE_REFRESH_TOKEN` | meta 帶 `credentials_env.refresh_token`（變數名），`run_stage --stage youtube` 從環境或 `.env` 讀該頻道的 token |
| 分類 | 22（People & Blogs） | explainer 27（Education）、skit 23（Comedy） |

注意 🟡：YouTube Data API 每個 GCP 專案每天預設 10,000 配額單位，上傳一支約 1,600 → **四個頻道共用一個 OAuth client 時，全部加起來一天約 6 支**。照提案頻率（每天 1–2 支）夠用，要每天每頻道都發就得申請加額度或分專案。（數字來自 YouTube API 文件的既有認知，本次沒有重新查證。）

`/upload` 與 `/drive` **不放進 runner**：一個對外公開、一個會刪本地檔，都維持人按。

---

## 7. 品質守門：什麼時候檢查什麼

| 檢查 | 時機 | 怎麼做 | 等級 |
|---|---|---|---|
| 來源與文章結構 | `article` 步驟 | `check_article.py`（既有） | 擋 |
| 事實與八卦出處 | 文章閘門 | 人看；審核頁並列文章與來源表 | 人 |
| deck lint（字數、來源、media 配比） | `deck` 步驟 | `deck_to_script.py --strict`（既有） | 擋 |
| 頻道素材政策 | `policy` 步驟，**在 deck 審稿前** | `qc.policy_findings`：deck 要的 media 種類不在頻道允許清單 → 失敗 | 擋 |
| 投影片溢出 | `slides` | `render_slides.py`（既有） | 擋 |
| 只有估算時長 | `media` | `--require-measured`（新）：沒有實測時長就 exit 3 | 擋 |
| B-roll 品牌／相關性 | 素材閘門 | 人看（關鍵字篩選擋不住 logo，v2 報告已證實） | 人 |
| 授權紀錄完整 | `qc` | credits 每筆要有 license；stock 要有 source_url；pending 不為空 → error | 擋成片核可 |
| artwork 可營利 | `qc` | NC／缺授權網址 → error | 擋成片核可 |
| 字幕安全區 | `mascot`（既有守門）＋`qc` | 每行右緣 < x=1600（16:9） | 擋成片核可 |
| 解析度、片長、音畫差 | `qc` | ffprobe；解析度不符 error，片長超出頻道區間、音畫差 > 2 s 為 warn | |
| 黑幀 | `qc` | blackdetect ≥ 0.5 s → error（有對照組測試：1.5 s 純黑會被抓到） | 擋成片核可 |

「擋成片核可」的意思：QC 不會讓 runner 失敗（成片還是要給人看），但 `approve --gate final` 會拒絕，除非給 `--override "理由"`，理由會寫進 `production.json`。

---

## 8. 人力估算 🔴（全部是估計，沒有計時資料）

### 每支片 Leon 要花的時間

| 工作 | 長片（explainer） | 衍生 Shorts | 冷笑話 Shorts |
|---|---|---|---|
| 開工（確認題目、叫 Claude 跑 /article） | 10 分 | 3 分 | 3 分 |
| 文章審稿（約 3,000 字＋來源抽查） | 25 分 | — | — |
| deck 審稿（contact sheet＋講稿） | 15 分 | 5 分 | 5 分（劇本） |
| AI 圖生成（Chrome＋Gemini 手動，約 3 張） | 20 分 | — | — |
| 素材審核（B-roll 整段看、授權） | 15 分（神話 artwork 再 +15） | — | — |
| 成片審看（8 分片 1.25 倍速＋QC 表） | 12 分 | 3 分 | 3 分 |
| 上傳前確認 | 5 分 | 2 分 | 2 分 |
| **合計** | **≈ 1.7 小時**（神話 ≈ 2 小時） | **≈ 15 分** | **≈ 15 分** |

### 每週總量

| 方案 | 內容 | Leon 每週 |
|---|---|---|
| **A. 提案頻率**（本設定檔的預設） | 晶片貓 1 長＋2 短；妖怪 隔週 1 長＋1 短；下班了 3 短；賽璐璐 隔週 1 長＋1 短；週日排程 15 分 | 1.7 ＋ 1.0 ＋ 0.85 ＋ 2×0.25 ＋ 0.75 ＋ 0.25 ≈ **5–6 小時** |
| B. 每頻道每週 1 長片＋3 短 | 四頻道 4 長（其中下班了的長片是迷因考古）＋12 短 | ≈ 7 ＋ 3 ≈ **10 小時** |
| C. 每頻道每天 1 支 | 28 支／週，約半數長片 | **> 30 小時**，不可行 |

**建議**：先用 A 跑 4 週，記錄實際審核時間（`production.log.jsonl` 有每個閘門的停下與核可時間，可以直接算），再決定加量。

### 如果時間超過，可以這樣減（由小到大的取捨）

1. 合併「文章」與「deck」兩個閘門：Claude 一次產出文章＋deck，Leon 只看 deck 頁（文章當附錄）→ 每支省約 10 分。代價：論點問題要到 deck 才發現，重做成本變高。
2. 衍生 Shorts 的 deck 閘門改為抽查（10 支看 3 支）。
3. 素材閘門只看 `review: true`（stock）與 artwork，純動態投影片不看。
4. 降頻：妖怪溯源所與賽璐璐研究室改每月 1 長片（每週省約 1 小時）。
5. **不建議**拿掉成片閘門（schema 已禁止）。

---

## 9. 成本估算

| 項目 | 每支長片 | 依據 | 等級 |
|---|---|---|---|
| TTS（Fish Audio） | 講稿約 3,000 字。費率我沒有查證，量級估每支 < US$1 | 需要 Leon 帳單或官方價目確認 | 🔴 |
| Claude（/article、/deck） | Leon 若用訂閱方案，邊際成本約 0；若走 API，研究型 session 每支估數美元 | 沒有本機量測；可用 `~/.claude/skills/dispatch/token_audit.py` 量 | 🔴 |
| Pexels／Pixabay | 免費（需標示作者，已自動附在說明欄） | v2 報告 | 🟡 |
| AI 圖（Gemini 網頁） | 0（免費額度）；營利使用條款沒查（v2 報告已標） | | 🔴 |
| 博物館 artwork（CC0） | 0 | 神話調查 | 🟡 |
| 本機算力 | 每支約 15 分，電費可忽略 | 第 5 節 | 🟢（時間） |
| YouTube API | 0（配額限制見第 6 節） | | 🟡 |

結論：**金錢成本不是瓶頸，人的審核時間才是。** 🔴

---

## 10. 已做（本分支）

| 項目 | 位置 | 驗證 |
|---|---|---|
| 頻道設定檔＋驗證 | `channels/*.yaml`、`src/content_farm/production/channels.py` | `test_production_channels.py` 10 項 |
| 選題池＋排程 | `channels/backlog/`、`production/schedule.py`、`produce.py plan` | `test_production_schedule.py` 7 項 |
| 一鍵 runner、狀態、指紋、渲染鎖 | `production/runner.py`、`state.py`、`steps.py`、`scripts/produce.py` | `test_production_runner.py` 9 項（假執行器） |
| 審核頁＋decision json＋inbox | `production/review.py` | 同上（含 HTML escape） |
| QC | `production/qc.py` | `test_production_qc.py`（含 blackdetect 對照組） |
| 上傳資料、排程、AI 揭露、多頻道 token | `production/publish.py`、`youtube/schemas.py`、`google_provider.py`、`run_stage.py` | `test_production_qc.py`、`test_youtube_google.py` |
| `--brand` 接進投影片與 media（overlay、title card、佔位圖、動態頁） | `render_slides.py`、`media_to_visual.py`、`explainer/cards.py`、`media.py`、`media_run.py` | `test_explainer_brand_plumbing.py` |
| CoWoS（mock 配音、chipcat 品牌）用 runner 重跑 | `output/cowos-chipcat/`（不 commit） | 見 REPORT |

## 11. Roadmap（沒做的）

| # | 項目 | 為什麼重要 | 估計 |
|---|---|---|---|
| R1 | `/article`、`/deck` skill 讀 `channels/<code>.yaml`（語氣、題材、口頭禪、notes），deck 加 `channel` 欄位 | 現在 agent 步驟不知道頻道 | 小 |
| R2 | 縮圖接品牌模板（`templates/brands/<code>/assets.html.j2` → `thumbnails/`） | 現在 package 只找既有縮圖 | 中 |
| R3 | deck schema 加 `artwork` media 種類（含授權欄位）＋博物館 API 抓圖、`myth` category | 妖怪溯源所的主要素材 | 中 |
| R4 | `shorts_skit` 渲染器（直式角色小劇場：鋪陳→停 0.6 s→笑點→叮）＋skit skill | 晶片貓下班了目前跑不出片 | 大 |
| R5 | 從長片切「一個數字」Shorts（挑 big_number 投影片 → 直式 45 s） | 晶片貓、賽璐璐的 Shorts 策略 | 中 |
| R6 | 夜間批次（launchd）＋核可後自動續跑 | 白天只做人工 | 小 |
| R7 | 成片核可後清中間檔（mascot.mov、media clips） | 磁碟 | 小 |
| R8 | 片尾（`templates/brands/endcard.html.j2`）接進 assembly | 工作室線只在片尾出現 | 中 |
| R9 | 面板 inbox 實作（照第 4 節介面） | 審核在手機上也能做 | 中（面板 repo） |
| R10 | AI 圖生成自動化（目前手動 Chrome＋Gemini） | 每支省約 20 分人力 | 中，需確認條款 |
| R11 | 說書貓、下班貓、格仔的 rig（mascot 模組，另一支 worker 負責） | 三個頻道目前沒有角色疊加 | 大 |
| R12 | 真配音（Fish Audio）跑一支完整片，量實際費用與時長 | 成本估算目前是 🔴 | 小，需 Leon 放行付費 |
| R13 | 每頻道 refresh token（以各頻道身分跑 `get_youtube_token.py`） | 多頻道上傳 | 小，需 Leon 操作瀏覽器 |
