# REPORT — HN 快報：每日 Shorts＋週長片（晶片貓系列）

分支 `feat/hn-daily`（從 `feat/ai-motion` 的 `9e7de1d` 開）。2026-10-16 23:40 至 10-17 凌晨實作與試做。
證據等級：🟢 本機實測可重跑／🟡 只驗到存在／🔴 未驗。

## TL;DR

- `produce.py news daily` 一條指令跑完：抓 HN、Lobsters、arXiv → 去重排名 → **逐則讀原文** → 產生手機版候選頁。`--pick 1,3` 之後，每支 Short 走「寫稿（/news-short）→ lint → Fish 配音 → 9:16 頁面＋晶片貓 → QC → 成片閘門 → manual-kit/preview.html」。`news weekly` 會自動挑當週最重要的 3–5 則，交給既有的 explainer 流程，每則一章。🟢
- 試做用今天 HN 的實際熱門：3 支 Short 都渲染到成片閘門。其中 2 支是要求的試做（高通 vs Arm、RPKI 70%）；第 3 支（Meta Muse Spark Open）是為了湊滿週長片的 3 則而加做。週長片已產出 deck（23 張、5 章，strict lint 通過），停在 deck 閘門。🟢
- 實測耗時：抓取 21 秒，讀 15 篇原文 21 秒。挑題到第一支成片約 **5.5 分鐘**（寫稿 2.5 分、配音 20 秒、渲染 104 秒）。**真正的瓶頸是共用 render lock**：另一支 worker 同時在渲染長片，所以 3 支 Short 從挑題到全部進成片閘門花了 89 分鐘，其中約 75 分鐘在排隊。🟢
- 需要 Leon 決定（詳見文末）：Short 與長片是否分開排隊、週長片只有 3 則時長度不夠、候選頁怎麼送到手機、聲音和其他頻道共用。
- 測試：新增 41 個，全部通過。整套測試 1163 通過、1 失敗，那 1 個（`test_multi_provider`）在 base `9e7de1d` 上同樣失敗，不是這次造成的。🟢

## 架構

```
scripts/produce.py news daily|weekly     ← 一鍵入口（scripts/produce.py 只接線）
src/content_farm/production/news/
  fetch.py    HN API / Lobsters RSS / arXiv API；PoliteHttp（各網域分開計間隔、3 MB 上限、X 一律擋掉）
  rank.py     去重（正規化 URL＋標題 Jaccard ≥0.6）、48 小時內、台灣相關度、分數
  verify.py   讀原文（先查 robots.txt；HTML 抽正文；arXiv 只走 API 摘要）→ 記下 read_at 和快取路徑
  review.py + templates/candidates.html.j2   手機候選頁（勾選後自動組出 --pick 指令）
  script.py   news_script.json schema（五段）＋ lint ＋ 轉成 script.json ＋ voice_text.json
  render.py + templates/news_short.html.j2   9:16 頁面、晶片貓 rig 靜態圖（嘴巴開合）、ASS 字幕燒入
  weekly.py   選當週 Shorts → weekly_plan.md / news_weekly.json；檢查 deck 每則一章、有引用原文
  daily.py / cli.py / series.py / glossary.yaml（名詞表）
scripts/news.py                 runner 的 cmd 步驟（lint / prepare / render / weekly-check）
.claude/skills/news-short/      寫 Short 稿的 skill
.claude/skills/news-weekly/     寫週長片 deck 的 skill
```

- **runner 怎麼分派**：比照 `short_from_long`，run-dir 裡有 `news_short.json` 就走 `NEWS_SHORT_STEPS`，有 `news_weekly.json` 就走 `news_weekly_steps()`（`production/steps.py`）。QC 會把新聞 Short 當 9:16 Short 檢查（`qc.qc_channel`）。
- **頻道設定**：`channels/chipcat.yaml` 只新增 `series.hn` 區塊；`channels.py` 只加了 1 個欄位（`series: dict`），驗證放在 `news/series.py`，避免和另一支正在改 `channels/` 的 worker 衝突。
- **Short 的步驟**：`news_script`（agent，verify＝lint）→ `news_prepare` → `voice`（付費）→ `news_render`（heavy，拿 render lock）→ `qc` → `gate_final` → `package`。
- **voice 只看旁白**：voice 步驟的 input 是 `voice_text.json`（只有旁白和念法）。只改畫面字、標題或來源時不會重新配音（付費），而且會保留實測秒數。這是試做時抓到的問題：把「5 年」改成「5年」差點觸發重新配音。🟢（測試 `test_screen_only_edits_keep_measured_durations_and_voice_text`）
- **週長片的步驟**：`deck`（/news-weekly）→ `weekly_check` → 既有 explainer 的 policy → slides → gate_deck → voice → illustrate → media → gate_media → assembly → mascot → qc → gate_final → package。不跑 article 階段，因為每則都已經以 Short 的身分讀過原文、審過。

## 來源與速率

| 來源 | 取什麼 | 速率／限制 | 本次實測 |
|---|---|---|---|
| HN 官方 API | topstories 前 60＋beststories 前 30 的 item | 官方說沒有速率限制；仍每次間隔 0.1 秒、循序 | 79 則有外部連結 🟢 |
| Lobsters | `https://lobste.rs/rss`（熱門），只取標題、連結、時間、tag | 每次跑只發 1 個請求 | 25 則 🟢（`/hottest.rss` 是 404，已改） |
| arXiv | API `search_query`（cs.AR/AI/CL/LG/CR/ET 最新 40 篇），只取標題、作者、摘要 | **每 3 秒 1 次**、單一連線；**不下載也不存 PDF**；HN 連到 arXiv 時也改走 `id_list` API | 40 篇 🟢 |
| 原文網站 | 單頁 HTML（3 MB 上限），先查 robots.txt | 同一網域每次間隔 1 秒 | 15 篇中 13 篇可讀；1 篇被 robots 擋（lore.kernel.org）、1 篇 403（tesla.com）🟢 |
| X／Twitter | 不抓 | `BLOCKED_DOMAINS`，PoliteHttp 直接拒絕 | 測試 `test_x_links_are_never_fetched` 🟢 |

排名公式寫在 `rank.py` 開頭，權重放在 `series.hn.rank_weights`：

> score = (0.55·熱度 + 0.45·台灣相關度) × 時效（0 小時 = 1.0，48 小時 = 0.5）

加密貨幣、美國選舉類的題目直接排除。這組權重是我先抓的起始值 🟡，要累積幾週 Leon 實際挑了哪些再調。

## 查證流程

1. `verify.read_original` 會打開每則候選的原文：
   - 讀不到的（付費牆、403、robots 禁止、只有 JS 外殼、少於 600 字、不是 HTML）在候選頁上**不能勾選**，`pick` 也會拒絕。
   - 每篇記下 `read_at`（每頁自己的讀取時刻）、`final_url`，原文抽出的文字快取在 `output/hn-<day>/reads/`。這個資料夾不 commit，也不轉貼。
2. `/news-short` 只能用快取的原文當事實來源。HN／Lobsters 的留言只當線索；說明欄裡會標成「討論串，只當線索」。
3. lint（`news/script.py`）擋下這些情況：
   - 沒有讀過的原文當主要來源，或主要來源不是實際讀取的那個 URL
   - 主要來源沒有 `read_at`
   - 只有討論串當來源
   - 觀點段看不出是觀點
   - 比喻段用的名詞不在名詞表
   - 出現流行語或投資建議用語
   - 「欸」超過 1 次
   - 秒數超出範圍
   
   試做時 lint 實際擋下兩份超長的稿。🟢
4. 稿件和說明欄都記錄來源 URL 與讀取時間。說明欄固定寫「本片是晶片貓對原文的摘要與評論，不是翻譯」。🟢（見 `upload/manual/description.txt`）
5. 原文沒有台灣資料時，就照實說（例如 RPKI 那支講「原文沒列台灣的數字」），不自己補一個台灣數字。原文是二手報導時，會標出轉述（「據 TechPowerUp 轉述路透」）。

**已知限制** 🟡：HTML 抽取會把有些網站的側欄和讀者留言一起帶進快取（例如 TechPowerUp）。skill 有寫明只能用正文，但抽取器本身沒有濾掉。

## 試做結果（2026-10-16 的 HN 熱門）

候選頁：`output/hn-2026-10-16/candidates.html`（手機 390 寬截圖檢查過，勾選後底部會出現可複製的 `--pick` 指令）。🟢

| # | 題目 | 原文 | 狀態 | preview |
|---|---|---|---|---|
| 1 | 高通告贏 Arm，賠償金只有兩美元？ | TechPowerUp（轉述 Reuters） | 成片閘門待審 | `output/hn-2026-10-16-hn-50117451/upload/manual/preview.html` |
| 3 | 網路路線被冒名？RPKI 一年從 54% 升到 70% | IPinfo | 成片閘門待審 | `output/hn-2026-10-16-hn-50112330/upload/manual/preview.html` |
| 2 | Meta 開放 8160 億參數模型，兩台 Mac 就能跑？（加做，給週長片） | Meta 官方部落格 | 成片閘門待審 | `output/hn-2026-10-16-hn-50107379/upload/manual/preview.html` |

- 每支約 37–40 秒，1080×1920，QC 0 error／0 warn，五段各有一頁，晶片貓在下半部，字幕燒在中段。
- 每頁的重點會在 2–3 秒內陸續出現，下半部不留白；版面調整前後的對照截圖見下方「版面」。
- 週長片：`output/hn-weekly-2026-W42/`，內容有 `weekly_plan.md`、`deck.json`（23 張，章節＝本週重點／高通 vs Arm／Meta／RPKI／下週看什麼）、`slides/contact_sheet.png`，審核頁是 `review/deck.html`。沒有渲染影片。🟢
- 所有 `output/` 檔案只在本機，不 commit（repo 是 public）。

**版面**（共 3 輪，每輪都抽格看過）：
- 第一版：卡片下半部空白，貓太小又蓋到來源字，片尾卡斷行後留下孤立的逗號。
- 第二版：卡片內容垂直置中並放大，貓放大到 900px 寬的 rig 畫布，來源字移到右欄。
- 第三版：8–9 字的標題自動縮到 96px，避免像「網路路線七成蓋章」那樣只剩最後一個「章」掉到下一行；片尾文字也縮短。🟢

## 實測耗時

| 階段 | 秒數 | 備註 |
|---|---|---|
| 抓取（3 個來源） | 21.3 | `timing.jsonl` 🟢 |
| 讀 15 篇原文（含 robots.txt） | 20.9 | 🟢 |
| 挑題 → 稿通過 lint（第 1 支） | 約 150 | 23:47:32 → 23:49:59；這次是我（Claude）寫稿。Leon 自己看稿的時間另計 🟢 |
| Fish 配音＋字幕對齊 | 19.2–23.8 | 每支 🟢 |
| 渲染 | 103.5–111.0 | 每支，負載 12–24 時 🟢 |
| **挑題 → 第一支到成片閘門** | **約 330（5.5 分）** | 機器閒時 🟢 |
| 等 render lock＋負載（第 2、3、4 次渲染） | **約 1,770／1,080／1,670（29／18／28 分）** | 另一支 worker 正在渲染 yokai／cowos／cel 長片，負載 18–37 🟢 |

結論：機器閒時，「挑題 → 成片 ≤ 1–2 小時」很輕鬆就能達成：2 支加 Leon 審稿約 20–30 分鐘 🟡（Leon 審片時間沒有實測）。和長片渲染撞在一起時，**3 支 Short 從挑題到全部進成片閘門花了 89 分鐘（23:47 → 01:16）**，其中約 75 分鐘在排隊。仍在 2 小時內，但很勉強。🟢

排隊久有兩個原因：
- render lock 不分輕重，flock 也不保證先到先得。
- `render_lock` 是先拿到鎖、再在鎖裡等負載降下來（`runner.py:73–82`）。我自己這支也照樣如此：log 先出現「render lock held」，拿到鎖之後又出現「load 37.2 > 18.0; waiting」。🟢 讀碼＋log

## Leon 每日審片步驟

1. 早上（或任何時候）在 Mac 上跑：
   ```bash
   python scripts/produce.py news daily
   ```
   約 45 秒後印出 `output/hn-<今天>/candidates.html`。
2. 用手機打開候選頁（怎麼送到手機見「要 Leon 決定」第 3 點）。看標題、熱度、台灣相關度、「✓ 已讀原文」和摘要，勾 1–2 則，按「複製指令」。
3. 在 Mac 上跑剛才複製的指令，加上配音參數：
   ```bash
   python scripts/produce.py news daily --date <今天> --pick 1,3 --allow-paid
   ```
   每支會停在「缺 news_script.json」。
4. 對每支 run-dir 跑 `/news-short --run-dir output/hn-<今天>-<id>`（Claude 讀原文快取寫稿，lint 過了才算完成）。
5. 再跑一次 `python scripts/produce.py news daily --date <今天> --allow-paid`，會做配音、渲染、QC，最後停在成片閘門，並印出每支的 `preview.html`。
6. 看 preview（約 40 秒的片＋說明欄＋來源），沒問題就：
   ```bash
   python scripts/produce.py approve --run-dir output/hn-<今天>-<id> --gate final
   python scripts/produce.py run --run-dir output/hn-<今天>-<id>   # 跑 package
   python scripts/produce.py manual-kit --run-dir output/hn-<今天>-<id>
   ```
   然後照 `upload/manual/README.md` 在 Studio 手動上傳。
7. 週六跑 `python scripts/produce.py news weekly`：
   - 會產生 `weekly_plan.md`，然後跑 `/news-weekly` 寫 deck
   - 再跑一次 `news weekly`，停在 deck 閘門
   - 之後和一般長片一樣：approve deck → 配音 → 媒體閘門 → 成片閘門

## 測試結果

- 新增 `tests/unit/test_news_sources.py`（17）、`test_news_script.py`（15）、`test_news_flow.py`（9），共 41 個，全部通過。🟢
- 整套 `pytest tests --ignore=tests/integration`：1163 通過、1 跳過、1 失敗。失敗的是 `test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results`。我在 base `9e7de1d` 的臨時 worktree 跑同一個測試也失敗，所以不是這次造成的；那個臨時 worktree 已經移除。🟢
- 測試抓到 1 個真 bug：RSS 時間是 `-0000` 時會被當成本機時區，差 8 小時。已修。🟢
- 試做時抓到 2 個 bug，都已修：`read_at` 原本記的是整批開始的時間，現在改成每頁自己的讀取時刻；畫面字修改會觸發重新配音（付費），改成 voice 只看 `voice_text.json`。試做那 3 份稿的 `read_at` 都是 23:46:16（整批開始時間），比實際讀頁早最多約 40 秒。🟢

## 要 Leon 決定

1. **Short 和長片分開排 render lock？** 目前共用同一把鎖，長片優先權一樣，而且拿著鎖等負載。選項：
   - (a) Short 另開一把「短鎖」，只限制同時 1 支
   - (b) 鎖改成先等負載、再拿鎖（要改 `runner.py`，會影響其他 worker）
   - (c) 維持現狀，Short 安排在長片的空檔跑
   
   我建議 (b)，但它碰到共用的 runner，所以沒有自己改。
2. **週長片長度**：3 則的 deck，用 deck 估算是 9.0 分；但換成實測的 Fish 語速（每秒 6.3 字，2 支 Short 實測）大約只有 **6.4 分** 🟡（推算，沒有配音實測）。要達到 ≥ 8:00，需要一週 4–5 則，或每章多 1–2 張。正常一週會有 7–14 支 Short，可以選到 5 則，只有試做因為只有一天的題目才不夠。
3. **候選頁怎麼到手機**：它是一個自含的 HTML 檔（不連外部資源）。選項：
   - (a) 用 AirDrop 或 iCloud Drive 傳
   - (b) 用 Claude 的 SendUserFile 傳
   - (c) 發成私人 Artifact
   
   (c) 等於對外送出內容，所以我沒有自己做。另外勾完的指令還是要回到 Mac 上跑。
4. **聲音**：Short 用的是晶片貓的 Fish「江湖」聲音，和 cel 頻道共用，而且模型頁標示是 Clone Model（policy review D2）。HN 系列屬於晶片貓，所以沿用；換不換由 Leon 決定。
5. **每日上限**：系列設定是每天 1–2 支，超過只會警告、不會擋（試做時挑了 3 支）。要不要改成硬擋？policy review D6 建議品質優先於數量。
6. **排名權重和台灣關鍵字**（`rank.py`）是我先定的起始值。建議試跑 2 週後，依 Leon 實際挑的題目調整。
7. **lint 秒數上限 55 秒**，是用實測的每秒 6.3 字換算。換聲音後要重量。

## 副作用與清理

- 臨時 base worktree `~/.claude/jobs/62cd6852/tmp/base`：已用 `git worktree remove` 移除。
- `output/hn-2026-10-16*`、`output/hn-weekly-2026-W42`：試做產物，留在本機給 Leon 看。`output/` 在 gitignore 裡，不會 commit。
- Fish Audio 用量：3 支 Short，每支 234–247 字。其中 2 支各配了 2 次（第 2 次是 voice input 改成 `voice_text.json` 後指紋改變，預期內），合計約 1,200 字。🟢 依 voice.log
- 沒有開瀏覽器 UI，沒有上傳。截圖用的是 headless Chromium（Playwright），它也是既有渲染流程在用的引擎。
