# REPORT — 科技新知（technews）頻道（2026-10-23）

分支 `worktree-cf-technews`（從 `worktree-cf-story-calibrate` fe97c23 fast-forward；`feat/hn-daily` 早已是祖先，merge 為 no-op）。未 push、未開瀏覽器、未上傳、無付費服務。
證據：🟢 本機實測／🟡 只驗到存在／🔴 未驗。

## TL;DR
- **程式與設定做完，沒有成片**：本機 swap 在 91–92%（≥90% 的入場門檻），`lanes.queue` 讓所有工作排隊，連 0.6 GB 的雲端腳本 agent 都不放行，約 1.5 小時沒有任何一支能起跑（佇列裡 cel 的 illustrate、九尾狐的 mix 也同樣卡住）。我沒有繞過閘門，已停掉自己的排隊程序。🟢（`produce.py queue` 輸出見下）
- 已完成並測過：offwork 停用、technews 頻道、4 個免費來源（含 GitHub Trending）＋回應快取、評審團自動選題＋Shorts/長片判定、無角色的 Shorts 畫面（自製來源卡）、腳本評審關、事實硬停。全套 pytest：**1804 passed、1 failed（`test_multi_provider`，既有）**。🟢
- **選題與格式判定已實跑一次**（今天的真實資料，花費名目 $0.43）：評審團挑了 3 則，3 則都判長片 → 我加了「每日長片上限 1 支」，其餘降為 Shorts。
- 沒做到：聲音設計（Qwen3 VoiceDesign 排隊中被停）、相似度、任何 Shorts 腳本／配音／渲染、長片。下方「接手」有逐步指令。

## 1. 頻道設定
- `channels/offwork.yaml`：新增 `enabled: false`（`Channel.enabled`，預設 true）。`load_all()` 預設略過停用頻道，所以 `plan`／`channels`／check.sh 不再給它排程或額度；`load_channel("offwork")` 仍可載入（舊 run-dir 可開）；`produce.py run` 對停用頻道**新建** run-dir 會拒絕。素材、brand、backlog、程式全留。
- `channels/technews.yaml`（code `technews`，暫名「科技新知」）：pipeline explainer；`mascot.rig_ready: false`（無角色，比照 yokai 拿掉青蛙：mascot 步驟、縮圖角色規則、deck 吉祥物占比全不適用）；voice 本機 voxcpm2，參考聲指向 `~/.local/share/content-farm-voices/technews-ref.wav`（**檔案尚未產生**，見 §5）；長片 6–10 分；brand `technews`（新增：CSS、assets、剪影＝訊號塔而非角色、示範 deck；`test_explainer_brands` 4→5）；`series.news` 區塊（來源 hn/lobsters/arxiv/github、每日 2–5 支、`dir_prefix: technews` 不與晶片貓的 `hn-<day>` 混、`min_per_source: 2`、`chars_per_second: 4.6` 暫估）。
- `channels/shared/review_panels.yaml`：技術新知觀眾 persona（上班族／工程師／大一生／主管／長輩＋holdout 老師）；`channels.technews`：`article`、`script_facts`、`media` 的 `waive_on_last_round: false`（事實與授權第 3 輪沒過仍硬停；已驗：`load_review('technews')` 顯示這三關 False、其餘 True、max_rounds 皆 ≤3）；`shorts_script.rework: news_script`。🟢

### 頻道名稱候選
1. **科技新知**（暫名，直白、好搜尋）　2. **科技早報**　3. **今日科技白話**　（建議 1 或 3；「早報」會綁定發片時段）

## 2. 來源與抓取（皆公開免費端點）
| 來源 | 方式 | 限制 | 今日實測 |
|---|---|---|---|
| Hacker News | 官方 Firebase API（top 60＋best 30） | 0.1 s 間隔 | 74 🟢 |
| Lobsters | `lobste.rs/rss` 一次請求 | 1 s | 25 🟢 |
| arXiv | API，cs.AR/AI/CL/LG/CR/ET 最新 40 篇，只取摘要不下載 PDF | 3 s/次 | 40 🟢 |
| GitHub Trending | `github.com/trending?since=daily` HTML，regex 解析（`parse_github_trending`，有測試） | 2 s；先查 robots.txt（不允許就略過並記錄）；Trending 無時間戳，記為「現在」 | 9 🟢 |
- **快取**：`PoliteHttp(cache_dir=.cache/news)`，只快取 200，TTL 30 分鐘，`--refetch` 忽略；損壞的快取當 miss。測試：`test_response_cache_answers_a_rerun_without_a_request`。
- 去重（URL 正規化＋標題 Jaccard）後 125 則，讀原文 20 則（19 可讀）。候選頁新增「每個非 HN 來源至少露出 2 則」（`with_source_floor`），否則 HN 分數會把 arXiv／GitHub 擠出前 20（實測前 20 只有 1 則 GitHub、0 則 arXiv）。
- X／Twitter 一律不抓（沿用）。

## 3. 選題與格式判定規則（`news/select.py`，決策 3d9f5448dbbc）
- 不開 inbox：`produce.py news daily --channel technews --auto N` → 評審團（technews persona 前 3 位觀眾＋製作人，4 席，各一次 `claude -p` sonnet·low、無工具）讀每則的原文摘錄，逐則給 1–10 分與「Shorts／長片」票與理由。
- 聚合（確定性）：平均分 ≥ 6.0 才有資格，取前 N；格式＝多數席判長片 **且** 原文可讀字數 ≥ 5000 才是長片，否則 Shorts（票多但素材不夠時會註明）；**每日長片上限 1 支**，其餘降為 Shorts 並寫進理由。
- 紀錄：`output/technews-<day>/selection.json`（每席分數、理由、票數、費用）；每個挑中的 run-dir 有 `format_decision.json`（格式、理由、各席票）。
- 長片＝一個 `technews-long-<day>-<id>` run-dir，`topics/candidates.json` 已有該則；之後走既有 explainer（選題評審→文章→…）。多則彙整長片仍走原本的 weekly 路徑（`news weekly`，目前只認 `hn-` 前綴，**technews 的 weekly 未接**🔴）。
- **今日實跑結果** 🟢（`output/technews-2026-10-23/selection.json`，名目 $0.4269）：
  | 分 | 題目 | 票 | 原文字數 | 決定 |
  |---|---|---|---|---|
  | 8.25 | Jailbreaking the Switch 2 | 4/4 長 | 14,941 | 長片 |
  | 7.25 | LLMs are making formal software verification feasible… | 4/4 長 | 25,146 | 降 Shorts（長片上限 1） |
  | 7.25 | Quad9 to exit France | 4/4 長 | 22,209 | 降 Shorts（長片上限 1） |
  其餘 16 則 ≤7.25 或 <6。🟡 觀察：評審團對長片偏鬆（Top 3 全票長片），所以才加每日上限；是否要把 `MIN_LONG_CHARS` 或票數門檻調嚴，要看更多天的資料。
- 第一次實跑犯的錯：沒加上限就啟動了 3 支長片 run-dir；我在它們跑到任何 agent 前殺掉程序，其中 2 個移到 `output/_discarded/`（`rm` 被拒）。

## 4. 無角色畫面與腳本流程
- `news_short.html.j2`：`has_mascot=false` 時下方三分之一改為**自製來源卡**（來源網域、原文標題、日期；不截整頁、不搬運），上方卡片與重點逐條出現不變；系列名、片尾橫幅、第五段標籤（`編輯觀點`）、說明欄、標籤改由 `series.news` 供應（晶片貓 `series.hn` 預設不變，`Branding()` 測試鎖住）。
- `news_script` 成為 producer 步驟（`review/producers.py`，brief 指向 news-short skill，無角色、`news.py lint` 驗證）；退回路由 `news_script` 已加進 `REWORK_STEPS`／routing／gate／usage。
- `NEWS_SHORT_STEPS` 在有 `series.news` 的頻道多一個 `gate_script`（評審團 `shorts_script`，在配音之前）；晶片貓 `series.hn` 流程不變。`panel_flow._short` 讓新聞 Short 走 `shorts_final`（原本會被當長片）。
- lint 秒數改用頻道的 `chars_per_second`（本機女聲遠慢於 Fish 的 6.3：晶片貓女聲 tempo 1.15 約 4.5 字/秒）；technews 暫設 4.6，**聲音定案後要實測改值**🔴。
- 測試：`test_news_technews.py`（10）等，涵蓋選題聚合、長片上限、無角色頁面、branding、前綴隔離、來源保底。

## 5. 聲音（**未完成**）
- 準備好的：`scripts/design_voice.py`（Qwen3-TTS VoiceDesign，多 seed）、`scripts/voice_clone_trial.py`（VoxCPM2 複製 3 句試聽）、`scripts/speaker_sim.py`（ECAPA 相似度，需 `~/.local/share/spk-embed/.venv`）。instruct：「女性、三十歲出頭、中偏低音域、乾淨明亮沉穩、台灣國語、電視台晚間科技新聞女主播、節奏穩定、不甜膩不撒嬌、語速中等偏快」（`~/.claude/jobs/1f597d1c/tmp/instruct.txt`，隨 job 清除；全文見本段）。原文即 `channels/technews.yaml` 的 `voice.reference.text`。
- 卡住的原因：`scripts/heavy` 排隊等不到（swap 91–92%、cel／九尾狐也在排）。**沒有任何 take、沒有 `technews-ref.wav`、沒有試聽、沒有相似度數字**。相似度要和 `chipcat-female-ref.wav`、`cel-take0.wav` 比（先前晶片貓 vs cel＝0.44，同人 take 約 0.82–0.84，作為對照）。

## 6. 各關輪數／放行項／費用／牆鐘
- 沒有任何一關跑過輪次（Shorts 卡在 `news_script` 的入場）。放行設定如 §1。
- 費用：選題評審 $0.4269（名目，訂閱額度，未用付費 API key）。預算參數 `--budget-usd 20` 已接進 `news daily`。
- 牆鐘：抓取＋讀 20 篇原文＋候選頁約 1 分鐘（快取命中更短）；選題評審約 7 分鐘；之後約 1.5 小時全在等閘門。

## 7. 成片
無（`artifacts/technews/` 未建）。

## 8. 接手（swap 降到 <90% 後）
```
python scripts/heavy --step voice --label technews:voice-design -- ~/.local/share/qwen3-tts/.venv/bin/python scripts/design_voice.py --out <dir> --seeds 3000 3001 3002 3003 3004 3005 --instruct-file <instruct.txt> --text-file <ref.txt>
```
挑 take（性別／F0／ASR 無誤／對 chipcat、cel 的 ECAPA 最低）→ 存 `~/.local/share/content-farm-voices/technews-ref.wav`＋同名 `.txt` → `voice_clone_trial.py` 試聽到 `~/Downloads/voice-trial/technews/` → `speaker_sim.py`。再：
```
PYTHONPATH=src python scripts/produce.py news daily --channel technews --auto 3 --auto-agents --budget-usd 20 --until gate_final --long-until gate_topic
```
（selection.json 已存在，會沿用不重付；Shorts 兩支會寫稿→腳本評審→配音→渲染→成片評審。長片 run-dir `output/technews-long-2026-10-23-hn-50192536` 已建，先停在選題評審。）配音後實測字/秒、回填 `chars_per_second`。成片：Shorts 放 `artifacts/technews/`；長片轉 540p 兩段 ≤13 MB。

## 9. 風險與限制
- 🟡 評審團長片偏鬆；🔴 GitHub Trending HTML 結構改版會讓解析靜默變 0 則（會出現在 fetch 的 counts，但不會報錯）；🔴 technews weekly 未接；🔴 脚本 producer、`gate_script`、無角色渲染都只有單元測試，**未經真實一次端到端**（含 headless Chromium 渲染來源卡）。
- 副作用：`output/technews-*`（gitignored）；`output/_discarded/` 內 2 個誤建的長片 run-dir 待 orchestrator 清（`rm` 被拒）；`.cache/news/`（gitignored）。

## 進度紀錄
- 2026-10-23：程式／設定／測試完成並 commit；因 swap 閘門停在聲音與腳本之前，回報建議：swap 降下來後換新 session 接手 §8。
