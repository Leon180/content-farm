# REPORT — 深海生物頻道（深潛日誌）＋第一支長片＋1 支 Shorts

分支 `worktree-cf-deepsea`（自 `worktree-cf-visual-v4` a082593 fast-forward）。未 push、未付費服務、未開瀏覽器、未上傳。

## TL;DR
- 🟢 頻道 `deepsea`（暫名「深潛日誌」）建好：品牌、abyss 深海合成配樂、評審人設、選題池、Wan 規則（無臉鏡頭＋negative）。相關測試全過。
- 🟢 長片「大王烏賊：人類為什麼花了一百多年，才拍到牠活著的樣子？」成片 **597.8 s（9:58）**，1920×1080，21 張 AI 圖、3 段 Wan（皆無臉）；540p 兩段 12.6／12.6 MB；Shorts 33.4 s。
- 🟢 雲端名目費用長片 **$5.27**（預算 $20）；Shorts 無雲端費用。
- 🟡 QC 1 error（dead zones：15 段 >10 s，與 cel 相同類別、未處理）、3 warn。評審：腳本評審觀眾「離開中位 10.6%」未達 0.35 門檻，依 v4 規則只自動改稿一次、不擋。
- 🔴 沒有人耳聽過聲音與配樂，也沒有人看過整支片；只抽了 3 格長片＋1 格 Shorts。
- 產物：`artifacts/deepsea/deepsea-part1.mp4`、`deepsea-part2.mp4`、`deepsea-short.mp4`（皆未 commit，mp4 只放本機）。run-dir：`output/deepsea-1`（長片）、`output/deepsea-short2`（Shorts；`output/deepsea-short` 是字幕錯位的舊版）。

等級：🟢 本機實測 ／ 🟡 只驗到存在或有保留 ／ 🔴 未驗。

## 1. 頻道設定
- code `deepsea`；名稱候選：深潛日誌（暫用）／深海圖鑑／往下一千公尺。
- 品牌 `deepsea`（`themes/brands/deepsea.css`＋`brands/deepsea/assets.html.j2`＋剪影 svg）：近黑深藍底、生物發光青強調、左側深度標尺、無角色（`rig_ready: false`）。
- AI 插圖：`z-image-turbo`（本機；klein 權重不在離線快取），深海科學圖鑑風，禁擬真照片、禁指定畫家，每張標「AI 示意圖」。
- 配樂 `abyss`（`audio_mix/synth_bgm.py`）：D 小調超低頻持續音＋緩慢和聲＋稀疏聲納鈴音；確定性、可無縫循環（比照 studio／pulse 的測試）。人聲維持原響度（-23.4 LUFS）。
- 評審：visual-v4 規則（腳本評審一次＋改稿一次、正確性信心度 ≥0.5、其餘關停用）；`channels.deepsea` 覆寫 article／script_facts／media 不放行；人設 6 位（含 holdout 國中生物老師）。
- Wan 規則（Leon 2026-10-24 追加，orch-personal 轉達）：`channels/deepsea.yaml` 的 `wan: {motion_only: true, negative_prompt: "face distortion, morphing"}`；新增 `WanPolicy`，Wan prompt 只用該張的 `motion_prompt`（環境＋鏡頭），指令帶 `--negative-prompt`；無設定的頻道指令與快取鍵不變（有測試）。
- 選題池 `channels/backlog/deepsea.yaml`（市調三題＋Shorts）。

## 2. 聲音（seed 5002，Qwen3-TTS VoiceDesign → VoxCPM2 複製）
instruct：男性、四十歲左右、低沉溫厚男中低音、微沙啞磁性、台灣國語、自然紀錄片旁白、平靜好奇帶敬畏、語速中等偏慢。median F0 88.2 Hz。
ECAPA 相似度（同人約 0.8+；晶片貓 vs cel＝0.44 當對照）：

| take（參考聲） | chipcat | cel | technews | yokai | ent |
|---|---|---|---|---|---|
| 5000 | 0.262 | 0.149 | 0.180 | 0.627 | 0.270 |
| 5001 | 0.289 | 0.192 | 0.247 | 0.800 | 0.316 |
| **5002（選）** | 0.164 | 0.072 | 0.125 | 0.542 | 0.243 |
| 5003 | 0.327 | 0.182 | 0.267 | 0.630 | 0.396 |
| 5004 | 0.281 | 0.178 | 0.276 | 0.717 | 0.368 |
| 5005 | 0.183 | 0.196 | 0.160 | 0.620 | 0.283 |

成片的複製聲（scene_001／014／020）：對自己的參考聲 0.84–0.87；對 chipcat 0.16–0.19、cel 0.11–0.13、technews 0.16、ent 0.25–0.29、**yokai 0.47–0.49**。🟡 與妖怪溯源所（同為男聲）最近，比女聲間的 0.44 還高一點，其餘都遠；沒有人耳聽過。配音 speech check：2 場仍有誤讀（scene_004 CER 0.14、scene_025 CER 0.32，已自動重生 6 次）。

## 3. 內容與評審（🟢 取自 `review/score_ledger.json`、`auto_fix.jsonl`）
- 選題：評審團從 10 題挑出 t03 大王烏賊（觀眾 6.67、專業 9.0、綜合 7.83）（候選與完整排名見 `output/deepsea-1/review/score_ledger.json`）。
- 文章 2706 字、5 個實際打開過的來源、9 個轉折（story_spine）；查核第 1 輪通過（兩位各標 1 條，仲裁後 0 確認錯誤）。
- 腳本評審（第 1 輪）：編劇（故事）6.0、編劇（密度）6.0（達 6.0 門檻）；合成觀眾離開時間中位 10.6%（四位 10.5／10.8／0.4／57.3%，holdout 100%），**未達 0.35 門檻**。v4 規則＝記分、自動改稿一次、不擋、不重評，所以照改稿放行。🟡 觀眾離開得這麼早，代表開場或前段留人點偏弱；沒有重評，不知道改稿有沒有改善。
- 講稿事實查核：第 1 輪確認 1 個錯誤或無來源說法（仲裁維持），依 `auto_fix_then_pass` 自動修後放行、不重查。
- deck：27 張（成片 26 場）、7 章；21 張 AI 圖（QC 與 illustrate 計數）、動畫頁 4、title card 1。Wan 鏡頭 3：s01（相機組＋海洋雪）、s08（掛餌釣線）、s27（上升的相機艙），皆無臉。
- 事實出處：Kubodera & Mori 2005（Proc. R. Soc. B）、Schmidt Ocean Institute 官方稿、Scientific American 等；MBARI／NOAA 影片與照片未使用。

## 4. 成片數字
| 項目 | 數值 |
|---|---|
| 生圖 | 21 張 z-image-turbo，958.5 s（首次 illustrate 因 s13 prompt 含 "no readable text" 被規則擋下，改寫該圖描述後重跑；講稿未動） |
| Wan I2V | 3 段，748.7／729.2／730.0 s（共 2208 s，經 `scripts/heavy` 佇列，無等待） |
| 配音 | 1294.7 s（VoxCPM2，tempo 1.0） |
| media | 391.7 s（初）＋204.4 s（Wan 烘完後重跑） |
| assembly／mix | 120.9 s／27.4 s |
| 540p 兩段 | 43 s（2-pass 280k＋aac 48k 單聲道，分段於 299 s）：12.60／12.61 MB |
| 本機指令步驟牆鐘合計 | 約 50 分（`produce.py usage`）＋Wan 37 分＋聲音設計 6 take（每 take 約 20 s） |
| 雲端名目費用（`claude -p`） | **$5.27**（評審 $2.09、產出 $3.18；topic $1.58、article $0.98、script_structure $1.92、script_facts $0.49、title_thumb $0.30） |
| 排隊／等待 | 聲音設計等記憶體（需 22.5 GB 空閒，實際 21–22 GB）累計約 2 小時；兩張自己的票互相「保留名額」死結 2 次（各約 30 分鐘，取消聲音設計票解開）；illustrate／media／assembly 前各等 swap ≥ 90% 數個輪詢週期（未量秒數） |
| 牆鐘（執行 vs 排隊） | 執行合計約 2 小時（上列各步驟加總）；排隊／等待約 3 小時以上（🟡 沒有逐筆計秒） |

## 5. QC 與已知問題（🟢 `qc/qc_report.json`）
- error：dead_zones 15 段 >10 s（67–83、99–111、116–128、152–171、177–192、196–207 s…）；cel run2-v4 同類（dead_zone）未處理。
- warn：speech_check 2 場誤讀；beat_gap 最長 72 s、24 個節拍問題；still_frames 最長靜止 35 s（超 8 s 者 10 處）。
- 其餘 ok：開場「往下一千公尺」、片尾「浮出水面」、授權 22 項無 pending、AI 圖 21 張標示與 model／prompt／seed、解析度、片長 597.8 s（目標 420–600；剛好貼著上限）。
- 🟡 畫面上來源列（REF ›）被截斷在字元上限（「Kubodera & Mori 20」）；長片與 Shorts 都有，屬模板行為，未改。
- 🟡 `final`／`title_thumb`／`media` 評審依 v4 設定停用，成片關直接放行；沒有第二雙眼睛看過成片。

## 6. Shorts（`artifacts/deepsea/deepsea-short.mp4`，33.4 s）
- 做法：`produce.py short-from-long` 切 s14（「4 小時 13 分」拉鋸戰）；旁白與字幕完全沿用長片，沒有新事實、沒有重配音。
- 🟡 畫面是現有「一個數字」數字面板，**沒有 AI 插圖**：此切片程式不支援 AI 圖（visual-v4 的 Shorts AI 圖只做在 HN 快報 Shorts）。數字拆成「4」＋單位「小時 13 分」避免溢出，但版面偏空。
- 🟡 無配樂（Shorts 流程沒有 mix 步驟）。
- QC 0 error／0 warn；已 package（`output/deepsea-short2/upload/youtube_meta.json`，`publish.shorts` 窗口為本次補進頻道設定）。

## 7. 順手修掉的 bug（皆有 commit）
1. `retention/audio_report.py`：配樂音軌比人聲音軌短（595.9 vs 598.8 s）時，視窗內布林遮罩與陣列長度不符 → `IndexError`，QC 步驟崩潰；改為取共同長度。🟡 沒補單元測試（需要真實音檔）；以本片 QC 通過實測。
2. `production/shorts_cut.py`：切 Short 時 `script.json` 的場景秒數可能是 deck 估值（本片 sum 450.9 s，實測音檔 597.8 s），導致切出錯的字幕視窗；改為優先量測 `audio/scene_NNN.mp3`（有測試）。🔴 **根因未查**：本片 voice 步驟沒有把實測秒數寫回 `script.json`（其他頻道的 run 是否同樣？未驗）；時間軸其他消費者（timing、QC）是否讀到同樣的舊值，也未驗。
3. 新頻道需 `publish.shorts` 才能 package Shorts——已補。
- 踩坑記錄：長片 run 進行中不要改頻道 yaml 的 schema（`wan:` 新欄位讓執行中的程序在下一次讀頻道時失敗，續跑即可）；同一 worker 不要同時排兩張重票（互相保留名額死結）。

## 8. 清理與限制
- 沒有 push、沒有付費 API、沒有開瀏覽器、沒有上傳。
- 留在本機的（rm 不在白名單，交 orchestrator）：`output/deepsea-1`（含 Wan clip 與中間檔）、`output/deepsea-short`（字幕錯位的舊 Shorts，可刪）、`output/deepsea-short2`、`artifacts/deepsea/*.mp4`；暫存在 `~/.claude/jobs/467ac1bb/tmp`（聲音 6 個 take、相似度 json、截圖，隨 job 清）。
- 聲音參考檔 `~/.local/share/content-farm-voices/deepsea-ref.wav/.txt` 在 repo 外（頻道 yaml 引用）。
- `src/content_farm/production/__pycache__/shorts_cut.cpython-310.pyc` 是 repo 內已被追蹤的檔案（非我加入），已被修改但**未 commit**。
- 🟡 未做：馬里亞納海溝／發光兩題；成片第二位審看；Shorts 的 AI 圖版本；時間軸 script.json 秒數根因。

## 9. 需要 Leon 決定／確認
1. 聲音與配樂請人耳試聽 `artifacts/deepsea/*.mp4`（特別是男聲與妖怪溯源所是否太像）。
2. 腳本評審顯示觀眾早離開（10.6%）：要不要為長片加一輪重評，或調整開場結構。
3. 片長 597.8 s 貼著 600 s 上限，下一支建議目標 540 s 左右。
4. dead zones error 要不要在 media／assembly 階段處理（多段視差長停留）。

## 進度紀錄
- 2026-10-24：頻道、聲音、長片全流程、540p、Shorts 完成；對話遠低於 30 萬 token。
