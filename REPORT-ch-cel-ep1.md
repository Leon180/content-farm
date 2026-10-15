# REPORT — v4-cel：賽璐璐研究室第一支長片

## TL;DR

- 成片 `output/cel-ep1/assembly/draft.mp4`：8:17（496.7 s），1920×1080，39.9 MB，配音用 macOS say 暫代。QC 結果 0 error、0 warn。片中沒有動畫原片或截圖，畫面由 24 張 cel 品牌投影片、5 張新聞卡、6 支 Pexels stock 組成。題目是「動畫市場創新高，為什麼動畫公司還是窮？製作委員會的錢怎麼流」。🟢
- 流程停在 **gate_final，等 Leon 審**。審核頁是 `output/cel-ep1/review/final.html`。前面三個閘門（文章、deck、media）我依 v4 指示用 `claude-draft` 先過了。🟢
- 選題池 `channels/backlog/cel.yaml` 共 7 題，`produce.py plan` 讀得到。🟢
- orchestrator 追加的兩件交件已完成：新增 `produce.py manual-kit` 子指令，產出 `upload/manual/`，內容包括 Studio 逐步清單、純文字欄位、縮圖、srt/vtt 和離線 `preview.html`，並補了 9 支測試。pytest 結果 1 failed / 1038 passed，失敗的那支在基準就已經失敗。🟢
- 需要 Leon 決定的事見 §7。重點有三：6 個只看過搜尋摘要的來源、AI 揭露那句寫了「部分插圖」但本片沒有 AI 圖、縮圖目前是暫用的。

等級：🟢 本機實測、可重跑；🟡 只驗到存在或二手資料；🔴 推論。

## 1. 基準

- worktree 一開始在 `6c47dd1`。我依指示執行 `git checkout -b feat/ch-cel-ep1 d9749c1`（`d9749c1 chore: claims for production workflow`）。🟢
- 本分支共兩個 commit：`b0c5ef4`（backlog＋manual-kit），加上收尾的那一個（報告、範例、測試修正）。**沒有 push**，因為 v3 共同限制是不 push，而且分支名稱不在 `feat/LeonLi/*` 的放行範圍內。

## 2. 選題（調查 → backlog）

- 讀了 orch-mail `f9f79d763aa65c29` 的 TL;DR，以及調查報告的 §4。調查推薦的第一順位是做法①「動畫產業拆解」，不用原片，風險低。
- 開台題選「製作委員會的錢怎麼流」。理由是它最能用公開數據講清楚：動畫協會的市場規模、帝國資料銀行的製作業調查、上市公司決算。它也是後續題目（動畫師薪資、外包、串流）共用的骨架。
- `channels/backlog/cel.yaml` 的 7 題：
  - committee-money：in_production
  - committee-number：short
  - animator-pay：researching
  - outsourcing-chain
  - streaming-buyout
  - ln-season-one
  - studio-bankruptcy
- 執行 `produce.py plan --week 2026-W44` 會排到 cel 的 short。🟢

## 3. 內容

- **論點**：動畫賣得越好，錢越流向持有版權的人，而不是把它畫出來的人；製作公司領的是工錢，不是分紅。
- **研究**：由 subagent 查證，原始筆記在 job tmp 的 `cel_research.md`。文章最後採用 16 個來源。`check_article.py` 結果為 `2625 chars, 16 sources, 0 problem(s)`。🟢
- **關鍵數字**（文章 §a-numbers 有完整表格）：
  - 2024 年廣義市場 3 兆 8,407 億日圓，其中海外 2 兆 1,702 億（動畫協會速報）。
  - 製作公司營收合計 4,662 億日圓，約占 12%。這個比例是**我們自己相除得出的**，片中有明講兩者的統計範圍不同。
  - 元請製作公司虧損比例 34.5%，業績惡化合計 60.0%（帝國資料銀行，2024）。
  - 專門工作室虧損比例 41.3%（2025）。
  - 東映動畫的版權事業 505.8 億日圓，約占營收一半。
  - IG Port 營業利益率 5.4%。
  - 巴哈姆特動畫瘋付費會員比例 20.5%。
- **台灣段**：宏廣在 1978 年以代工起家（下游）；巴哈姆特動畫瘋的付費觀眾則屬於上游。
- **deck**：
  - 共 24 張，6 種版型都有用到。
  - `deck_to_script --strict` 沒有任何 lint。
  - 輕鬆段落 9 個，gossip 和 joke 交替出現。gossip 一律附來源，笑話是原創。
  - 主持人自稱「賽璐璐研究室」，不用晶片貓。
  - 我沒有先產 `deck_outline.json`，直接寫 deck。runner 不需要它，但這等於跳過了 /deck-outline 這一關，Leon 若要保留大綱閘門請告訴我。
- 輸入檔已複製到 `docs/examples/ch-cel-ep1/`：article.md、sources.json、deck.json。

## 4. 執行紀錄（`produce.py run --channel cel --mock-voice`，max-load 30）

| 步驟 | 結果 | 耗時 |
|---|---|---|
| article / gate_article | 0 problem；以 claude-draft 核可 | 0.2 s |
| deck / policy / slides | 24 張無溢出；全部符合 cel 素材政策 | 0.5 s／7.4 s |
| gate_deck | 以 claude-draft 核可（因 s05、s24 改版，核可了兩次） | — |
| voice（macos_say） | 第一輪 94.9 s；重跑時沿用既有音檔，24.8 s | — |
| media | 第一輪 360.1 s，重跑 305.8 s；6 支 stock，0 placeholder | — |
| gate_media | 我逐支抽幀看過再核可 | — |
| assembly | 字幕燒入 | 217.1 s |
| mascot | `rig_ready: false`，跳過 | — |
| qc | 0 error、0 warn：1920×1080、496.7 s、音畫差 1.51 s、無黑幀、credits 完整 | 9.7 s |
| **gate_final** | **等待 Leon** | — |

- **media 審核時抓到兩支不能用的 stock**：
  - s05 的攤位畫面裡有可讀的啤酒品牌海報。
  - s24 抓到比特幣放在美鈔上，既離題又帶標誌。
  - 兩張都改成 animated 投影片，重新過 deck 閘門。現在 stock 占 6/24 = 25%，仍符合 lint 要求的 ≥ 20%。🟢
- 剩下 6 支 stock（s01、s07、s11、s15、s20、s21）都抽幀看過，沒有 logo，也沒有動畫角色或畫面。🟢（只看了 1–2 幀，不是整支看完，算 🟡）
- 機器負載很高：開跑時 1 分鐘負載約 45–82。重步驟有等到負載降到 30 以下，也等過別人的渲染鎖。

### 成片與截圖

- 成片：`/Users/lileon/project/content-farm/.claude/worktrees/cf-ch-cel-ep1/output/cel-ep1/assembly/draft.mp4`。沒有角色疊加，所以沒有 final.mp4，QC 與 meta 都改指向 draft.mp4。
- 截圖放在 `docs/examples/ch-cel-ep1/`：
  - 成片截圖：`final_040s.jpg`、`final_200s.jpg`（s10「約 12%」）、`final_385s.jpg`（s20 宏廣、stock 下三分之一字卡）
  - `media_contact_sheet.jpg`
  - `thumbnail.png`

## 5. 上傳資料

- `output/cel-ep1/upload/youtube_meta.json` 的內容：`privacy_status: private`，6 個章節（0:00、1:07、2:36、4:58、6:11、6:54），`contains_synthetic_media: true`，`category_id: 27`，`credentials_env.refresh_token: CF_YT_CEL_REFRESH_TOKEN`。
  - 這份是我直接呼叫 `publish.build_meta` 先寫出來的。package 步驟要等 gate_final 核可後才會跑，屆時會用同一個函式覆寫。
  - **沒有上傳**。🟢
- **手動上傳包**：`output/cel-ep1/upload/manual/`（orch-mail `aac6218fca3defb5`）
  - `README.md`：
    - 第一行標註「暫用機器聲，待換 Fish Audio 後重出」。
    - 依 Studio 流程排列：選頻道、選檔、標題、說明、縮圖、播放清單、兒童內容選「否」、變造或合成內容、標籤、語言（中文（台灣））、類別（教育）、字幕、片尾畫面、資訊卡、版權檢查、可見度（私人）。
    - 附影片絕對路徑、片長 8:18（ffprobe 實測）、檔案 39.9 MB。
  - `title.txt`、`description.txt`、`tags.txt`、`subtitles.srt`、`subtitles.vtt`、`thumbnail.png`（1280×720）
- **本機預覽頁** `output/cel-ep1/upload/manual/preview.html`（orch-mail `911332f510cc0f27`）：
  - 單一檔案，不連 CDN，也沒有外部資源。
  - `<video>` 用相對路徑 `../../assembly/draft.mp4` 載入影片；`<track default>` 載入 vtt 字幕。
  - 頁面內容：章節可點擊跳轉、標籤、縮圖、上傳設定摘要；頂部狀態列顯示配音來源、QC 結果、片長、檔案大小。
  - 頻道是 9:16 時改用直式播放器。
  - 所有值都經過 HTML escape。
  - **我沒有開瀏覽器驗證**，依指示留給 orchestrator。file:// 能不能播放這點 🔴 未驗。
- **`produce.py manual-kit --run-dir <dir> [--voice auto|machine|fish]`**：
  - 新增 `src/content_farm/production/manual_kit.py`、`manual_readme.py`、`manual_preview.py`。
  - 有 `upload/youtube_meta.json` 時優先讀它，沒有就在記憶體裡現建，並在 README 註明成片閘門尚未核可。
  - 配音來源預設從 `logs/voice.log` 判斷。
  - 測試 `tests/unit/test_production_manual_kit.py` 共 9 支，涵蓋：
    - 全部檔案都產出、縮圖尺寸與 2 MB 上限
    - README 的機器聲標註與 Studio 欄位
    - `--voice fish` 時不顯示標註
    - 優先採用 package 產的 meta
    - preview 的相對路徑、escape（`<script>` 標題）、不含遠端資源、章節秒數、橫式／直式
    - srt → vtt 轉換
    - 缺縮圖來源、缺影片時報錯

## 6. QC 與 credits

- QC：`output/cel-ep1/qc/qc_report.json`，0 error、0 warn。🟢
- credits：6 筆，全部 Pexels License，pending 0。作者依序為 RDNE Stock project、Jakub Zerdzicki、Ron Lach、utopia 36、cottonbro studio、Mikhail Nilov，已自動附進說明欄。🟢
- 片中提到的作品（龍珠、航海王、GAINAX、MAPPA）只出現片名或公司名文字，**沒有任何官方畫面，也沒有 AI 圖**。🟢

## 7. 需要 Leon 決定

1. **成片審看**：開 `output/cel-ep1/review/final.html` 或 `upload/manual/preview.html`。核可指令：
   `python scripts/produce.py approve --run-dir output/cel-ep1 --gate final`
   之後再執行 `run`，產出正式版 youtube_meta。
2. **文章、deck、media 三個閘門是我代簽的**（`claude-draft`）。論點和用詞請你看過一次。
3. **6 個來源只看過搜尋摘要，沒讀到全文**，公開前建議人工補查：
   - `jftc-anime-inspection-2025-03`（45 名業者被指導）
   - `ig-port-kessan-fy2026`（5.4%）
   - `meti-anime-transaction-2026`（五到七成是自由工作者）
   - `netflix-mappa-2026`
   - `production-committee-nlab`（委員會怎麼分潤的說明）
   - `wang-film-mirrormedia-2016`（宏廣）

   🟡 文章裡的數字都有來源標註，但上面這幾個的原文我們沒有讀到。
4. **AI 揭露那句**：`publish.AI_DISCLOSURE_LINE` 寫的是「配音與部分插圖為合成內容」，但本片沒有 AI 插圖。要不要依頻道或依每支片改成實際情況？這是共用模組，我沒有動。
5. **Studio 的「變造或合成內容」**：README 建議勾「是」，與頻道設定 `ai_disclosure: true` 一致。YouTube 是否真的要求這類內容一定要揭露，我沒有對照官方條文。🟡
6. **縮圖**：目前暫用第 1 張標題投影片，要不要另做縮圖產生器（roadmap R2）？
7. 小瑕疵：s07 比較表的「平均年營收 27.49 億」沒寫單位「日圓」（講稿裡有）。修正它需要重開 deck 閘門並重新渲染，我先不動。
8. 換成 Fish Audio 之後：只要重跑 voice 以後的步驟（`--allow-paid`），再執行 `manual-kit --voice fish` 就能重出上傳包。

## 8. 副作用與清理

- `output/cel-ep1/`（gitignore）：整個 run-dir，內含 `assembly/_tmp/` 中間檔與 41.9 MB 的成片。上傳前要保留。
- job tmp `/Users/lileon/.claude/jobs/b358839a/tmp/`：研究筆記、`deck_core.json`、`build_deck.py`、抽幀圖。job 刪除時會一起清掉。
- `PROGRESS-ch-cel-ep1.md`：進度紀錄，**沒有 commit**，可以刪（`rm` 在 deny 清單）。
- 未追蹤的 `graft/` 在開工前就存在，不是我產生的。
- `.env` 沒有複製進 worktree（改用 `--env-file` 指向主 checkout），跑 pytest 時 worktree 裡沒有 `.env`。
- 呼叫了 Pexels 免費 API（兩輪 media）；沒有呼叫任何付費 API，沒有開瀏覽器，沒有用 AI 生圖。
- 修改了既有測試 `test_production_schedule.py::test_repo_backlog_loads`：原本斷言 cel 沒有 backlog，現在 cel 有了。我改成驗證 cel 的 backlog 內容，並用 tmp_path 驗證「缺檔時回傳空的 backlog」這個原本的語意。
