# REPORT — 選題雷達（topic radar）

分支 `worktree-cf-topic-radar`（從 `worktree-cf-revisual` 的 `ac0392c` 開出）。2026-10-24，Sonnet 5.5。

## TL;DR

- 做好了：`python scripts/produce.py radar --channel <c> | --all`，6 個頻道各自每天產出候選題＋需求證據（數字＋可點開的來源網址）＋同類影片前 5 名觀看數＋留言裡的提問＋建議格式（Shorts／長片）。
- **YouTube OAuth 可用**（`CF_YOUTUBE_*` 三個值能換到 access token，`videos.list` 回 200），不需要 API key。
- **Reddit 公開 JSON 對未登入請求回 403；B 站排行榜回 `code -352`（風控）**。兩者都照規則不繞過，已在每個輸出檔的 `sources` 記錄為不可用。其餘三個來源（YouTube、維基、HN）都正常。
- 已接進選題階段：選題 producer 的提示會帶入雷達候選與證據，評審團的 topic 題目說明加了「用 evidence 排序、不設門檻」。
- 實抓一次：6 頻道共 53 個候選，`output/radar/2026-10-24/SUMMARY.md` 是每頻道前 3 名的一頁摘要（`output/` 不進 git；路徑見下）。
- 首次全跑花 YouTube 配額約 4,850／10,000 單位（之後 7 天內大多走快取）。新增 41 個測試全過；全專案測試 1960 過、唯一失敗 `test_multi_provider.py::test_returns_first_provider_results[asyncio]` 在 base 分支（cf-revisual）一樣失敗，與本次無關。

## 來源與條款遵守

| 來源 | 端點 | 條款／做法 | 結果 |
|---|---|---|---|
| YouTube Data API v3 | `search.list`（100 單位）、`videos.list`、`commentThreads.list`（各 1 單位） | 只用官方 API；每次呼叫計配額，`--youtube-budget`（預設 6000）超過就停；輸出檔帶 `youtube_data_expires`（產生日＋30 天），超過 30 天的 `output/radar/<日期>/` 整個刪除（`store.purge_expired`，每次執行時跑）；YouTube 快取檔超過 8 天就刪；金鑰不進輸出、不進快取、錯誤訊息遮掉 `key=`／`access_token=` | 🟢 可用 |
| Wikimedia Pageviews API + MediaWiki API | `wikimedia.org/api/rest_v1/metrics/pageviews/per-article/...`；標題解析用 `w/api.php?action=query&redirects&converttitles` | 描述性 User-Agent（含 repo 網址）、每次間隔 0.2 秒（遠低於上限）、資料 CC0 | 🟢 可用 |
| Hacker News | 官方的 HN Search API `hn.algolia.com/api/v1/search`（關鍵字＋近 7 天＋30 分以上） | 公開、免金鑰、每次間隔 0.5 秒 | 🟢 可用 |
| Reddit | 公開 `r/<sub>/top.json` | 描述性 User-Agent、間隔 6.5 秒（未登入上限約 10 次／分）；只讀公開 subreddit、略過 NSFW | 🔴 全部 403。未登入存取被擋，**沒有繞過**（沒換 UA、沒登入、沒走代理）。要用需 Leon 去 reddit.com/prefs/apps 申請免費 script app 填 client id／secret（我沒寫任何密鑰） |
| B 站 | 公開排行榜 `x/web-interface/ranking/v2`（未登入） | 只用未登入端點、間隔 2 秒 | 🔴 `code -352`（風控）。另外手動試了一次公開 `popular` 端點也是 -352。沒有繞過 |
| Google Trends | — | 沒有官方 API，**不用**非官方爬取 | 列為待決定 |

遇到 403／429／-352 的來源，同一次執行不再重問（`build._trending_signals`）。

## YouTube 認證結果

先用程式試：以 `CF_YOUTUBE_CLIENT_ID`／`CLIENT_SECRET`／`REFRESH_TOKEN` 換 access token，再對 `videos.list` 發一個 1 單位的探測。結果：**token refresh 成功、`videos.list` 回 200**。程式只印出「oauth（可用：videos.list answered 200）」這類狀態，沒有印出或讀出任何值（只讀這四個名稱：OAuth 三個＋可選的 `CF_YOUTUBE_API_KEY`；不經過 `Settings`，因為 `.env` 裡別的名稱會讓它報錯並把值印進錯誤訊息）。

備援：OAuth 不可用（過期、scope 不足）時，程式自動改用 `CF_YOUTUBE_API_KEY`（由 Leon 到 Google Cloud 免費申請填入）；都不可用就略過 YouTube，其餘來源照跑。這兩條路徑都有單元測試。

注意：OAuth 這顆 token 的 scope 我沒有檢查（不讀值）；它能讀公開資料就夠用了。

## 每頻道前 3 候選與證據（2026-10-24 實抓）

「提示分」0–100 只是排序用，算式寫在 `scoring.py` 檔頭。證據欄的數字都附來源網址（完整連結在 SUMMARY.md 與各 JSON）。

| 頻道 | # | 標題草案 | 格式 | 分 | 主要證據 | 競爭影片前 5 名觀看數 |
|---|---|---|---|---|---|---|
| 晶片貓 | 1 | 半導體製造流程拆解 | 長片 | 64.3 | 英文維基近 30 日 8,090 | 109 萬／103 萬／68 萬／51 萬／42 萬 |
| | 2 | 輝達拆解 | 長片 | 63.7 | 英文維基 166,498；中文維基 11,050（近期 ×1.39） | 2,397 萬／492 萬／113 萬／105 萬／93 萬 |
| | 3 | 台積電拆解 | 長片 | 59.8 | 中文維基 16,550（×1.19）；英文 45,523 | 100 萬／64 萬／63 萬／51 萬／45 萬 |
| 賽璐璐研究室 | 1 | 京都動畫 | 長片 | 62.9 | 日文維基 14,615；中文維基 4,518 | 38 萬／22 萬／14 萬／7.6 萬／7.4 萬 |
| | 2 | 賽璐珞動畫 | 長片 | 44.9 | 英文維基 12,600 | 10 萬／4,593／3,270／1,348／1,347 |
| | 3 | 動畫師的薪水與工時 | 長片 | 40.5 | 日文維基 1,129；志祺七七同題影片 18 萬 | 18 萬／1.4 萬／86（只搜到 3 支） |
| 妖怪溯源所 | 1 | 九尾狐 | 長片 | 68.3 | 英文維基 Kitsune 38,763；日文 7,471 | 615 萬／241 萬／46 萬／20 萬／20 萬 |
| | 2 | 鵺 | 長片 | 68.2 | 日文維基 13,217 | 248 萬／200 萬／116 萬／107 萬／98 萬 |
| | 3 | 天狗 | 長片 | 66.6 | 日文維基 7,438；中文維基升溫 ×1.58 | 321 萬／265 萬／248 萬／166 萬／74 萬 |
| 科技新知 | 1 | Kimi K3.1 Pro and K3.1 Pro Highspeed（原題，待譯） | Shorts | 74.0 | HN 870 分 | — |
| | 2 | Every AI model has the same "controversial" take on humans（原題） | Shorts | 71.6 | HN 626 分 | — |
| | 3 | OpenShell – A safe, private runtime for fleets of autonomous AI agents（原題） | Shorts | 69.9 | HN 493 分 | — |
| 深潛日誌 | 1 | 馬里亞納海溝 | 長片 | 75.1 | 英文維基 81,561；YouTube 前兩名 2,260 萬／1,626 萬 | 2,260 萬／1,626 萬／340 萬／283 萬／263 萬 |
| | 2 | 大王烏賊 | 長片 | 66.8 | 英文維基 107,109（×1.42）；中文維基 ×3.14 | 506 萬／411 萬／34 萬／11 萬／7 萬 |
| | 3 | 海底熱泉 | 長片 | 61.8 | 英文維基 8,953 | 28 萬／24 萬／17 萬／5.7 萬／5 萬 |
| 寓言學堂 | 1 | 狼來了 | 長片 | 67.7 | 英文維基 13,474 | 258 萬／211 萬／172 萬／107 萬／79 萬 |
| | 2 | 伊索寓言 | 長片 | 66.5 | 英文維基 24,545 | 120 萬／48 萬／33 萬／27 萬／27 萬 |
| | 3 | 愚公移山 | 長片 | 52.0 | 中文維基 344；YouTube 中位數 16.6 萬 | 291 萬／52 萬／17 萬／16 萬／15 萬 |

觀察（🟡，只是這一天的快照）：
- 深潛日誌「大王烏賊」：維基近 7 日是前 23 日的 1.4～3.1 倍，且前兩名影片 400～500 萬但第三名掉到 34 萬——頭部集中、後面空，可能有切入點。
- 賽璐璐研究室「賽璐珞動畫」「動畫師的薪水」：同類影片少，觀看數也低（中位數 3,270／1.4 萬）——需求弱還是空缺，單靠這些數字分不出來。
- 科技新知的 HN 項目為英文原題，`title_draft` 標「（原題，待譯）」並附警告；選題 producer 的提示要求把它改成繁中標題（沒用 LLM 翻譯，避免額外花費）。

## 呼叫量與快取

首次全跑（含先單跑 deepsea 一次）合計：

| 主機 | 網路請求 |
|---|---|
| `www.googleapis.com`（YouTube） | 175（含 3 次 1 單位探測） |
| 維基（zh／en／ja＋`wikimedia.org`） | 約 172 |
| `hn.algolia.com` | 27 |
| `www.reddit.com` | 8（全 403，同一次執行內遇到即停） |
| `api.bilibili.com` | 3（全 -352） |

開發中又重跑 3 次（改標題、改留言過濾）：新增 HN 約 46、Reddit 18（同樣全 403）、YouTube 約 33 次請求／30 單位，其餘走快取。

YouTube 配額：首次約 4,850 單位（search 約 47 次 × 100 ＋ videos／comments 各 1 單位），約佔每日預設 10,000 的 48%。快取 TTL：搜尋 7 天、影片統計與留言 12 小時、維基 12 小時（標題解析 7 天）、HN／Reddit／B 站 3 小時。重跑同一天驗證：YouTube 只花 10 單位，維基 0 請求，HN 0 請求。

⚠️ 搜尋快取同一天過期：第 8 天會一次再花約 4,800 單位。若同時有上傳（每支 1,600 單位）會吃緊——排程那一派可以把頻道錯開日期，或調小 `--youtube-budget`。

## 實作

- `src/content_farm/topic_radar/`：`config`（每頻道設定）、`http`（快取＋間隔＋計數）、`wikipedia`／`trending`（HN、Reddit、B 站）／`youtube`（認證、搜尋、留言）各一個來源模組、`scoring`、`build`（組候選）、`store`（寫檔、30 天清除）、`summary`（一頁 Markdown）、`brief`（給選題階段）、`cli`。借 MediaCrawler 的架構想法（每來源拆開、設定集中、搜尋與留言分層、快取抽象化），沒用它的任何程式碼。
- 設定在 `channels/radar/<頻道>.yaml`（種子題目、各語言維基條目、YouTube 查詢詞、HN／subreddit／B 站分區與關鍵字）。**刻意不放進 `channels/<code>.yaml`**：那份 schema 是 `extra="forbid"`，而 deepsea、fable 的主檔在別的分支（fable 目前還沒有主檔），分開放才不會互相衝突。`produce.py channels` 不受影響。
- 重用評估：快取與間隔的想法來自 `production/news/fetch.py` 的 `PoliteHttp`，但雷達需要每次請求自帶 `Authorization`、每次呼叫不同 TTL、且快取不能存含 API key 的 URL，所以另寫了 `topic_radar/http.py`（約 130 行）。
- 接到選題階段：`review/producers.py` 在 topic 步驟第一次產出時，把 `output/radar/<近 7 天最新>/<頻道>.json` 複製成 `run_dir/topics/radar.json`（producer 讀不到 `output/`），並在提示裡列出候選＋證據，要求沿用 `radar_id` 並原樣複製 evidence／competitors／viewer_questions、不可自編。`review/prompts.py` 的 topic 評審說明加了 `RADAR_EVIDENCE`：有 evidence 的題目用它排序，沒有的不扣分、不設門檻。重做（有 fixes）時不再塞雷達。沒有雷達檔時行為與之前完全相同（有測試）。
- 測試：`tests/unit/test_topic_radar.py` 41 個（設定、各來源對固定回應、認證三種結果、配額上限、快取不花配額、30 天清除、評分、建檔、摘要、producer 提示）。`tests/conftest.py` 加 `CF_RADAR_DIR` 指到暫存目錄，讓測試不讀真實的 `output/radar`。

## 待 Leon 決定／已知限制

1. **Google Trends**：沒有官方 API，不做。要不要改成請 Leon 每週手動貼一次關鍵字比較？
2. **Reddit**：要的話申請免費 script app（client id／secret），我再接 OAuth。目前只是少一個來源。
3. **B 站**：公開排行榜被風控擋，沒有合規的替代；建議先放棄，把 `bilibili_rids` 留著不影響。
4. **寓言學堂**的種子是我依頻道名假設為「寓言／成語典故」寫的；頻道設定上線後請校正 `channels/radar/fable.yaml`。
5. **種子題目是我挑的**：每頻道 6～9 題。第一次實抓有 4 個維基條目不存在（CoWoS 英文條目、極紫外光舊標題、英文 Anime streaming、守株待兔），已改標題或移除；現在 6 個輸出檔的維基來源都沒有缺漏。之後某條目消失時，輸出檔 `sources` 會列出，作為「該換種子」的訊號。
6. **YouTube 衍生資料保留**：`output/radar/<日期>/` 30 天後由下一次 `radar` 執行刪除（含 SUMMARY.md）。orchestrator 若把 SUMMARY 做成 Artifact，**請在 2026-11-23 前下架**，否則 Artifact 內的 YouTube 數字超過 30 天。
7. **留言提問是啟發式**（🟡）：只留中文、以問號結尾或含「想看／請問／為什麼…」的留言，仍有雜訊（例如談時事的留言）。評審團只把它當輔助。
8. **競爭影片是全語言搜尋**：妖怪、深海的前幾名常是日文或英文頻道；它證明需求，但不等於華語競爭。
9. 提示分的權重（維基 35＋15、YouTube 30＋10、時效 50＋10）是我定的，沒有用歷史成效校準；科技新知另加 `trending_bonus: 15` 讓時效題浮上來。要調就改 `scoring.py`／yaml。
10. **排程另派**：目前是手動／被呼叫。`produce.py radar --all` 可直接掛每日排程；建議排在早上，並把 `--youtube-budget` 設成 3000 之類。

## 副作用與清理

- 建立：`output/radar/2026-10-24/*`（已被 `.gitignore` 的 `output/` 忽略）、`.cache/radar/`（快取，`.gitignore` 的 `.cache/` 忽略）。兩者都在本 worktree 內，沒有碰其他 worker 的 worktree、沒有寫共用路徑。
- 沒有 push、沒開瀏覽器、沒用付費服務、沒上傳；沒有讀出 `.env` 的值。
- 另外：`git merge --ff-only worktree-cf-revisual` 把本分支從舊 commit 快轉到 revisual 最新（`reset --hard` 被守門擋下，改用快轉，等價）。

## 重現

```
PYTHONPATH=src /Users/lileon/project/content-farm/.venv/bin/python scripts/produce.py radar --all --env-file /Users/lileon/project/content-farm/.env
PYTHONPATH=src /Users/lileon/project/content-farm/.venv/bin/python -m pytest tests/unit/test_topic_radar.py
```

一頁摘要：`.claude/worktrees/cf-topic-radar/output/radar/2026-10-24/SUMMARY.md`（絕對路徑 `/Users/lileon/project/content-farm/.claude/worktrees/cf-topic-radar/output/radar/2026-10-24/SUMMARY.md`）。
