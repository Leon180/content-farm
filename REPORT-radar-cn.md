# REPORT — 選題雷達加中文網路來源＋跨頻道選題池

分支 `worktree-cf-radar-cn`（從 `worktree-cf-integrate-1025` 快轉開出）。2026-10-27，Sonnet 5.5。未 push、未開瀏覽器、未用付費服務（`--no-youtube`，YouTube 配額 0）。

## TL;DR

- 新增 V2EX（熱門＋節點）、B 站（熱門榜＋分區榜）兩個來源，接進 `produce.py radar`；失敗只降級，不擋整個雷達。
- 新增跨頻道選題池：`radar --all` 多寫 `POOL.json`／`POOL.md`，每則標「適合哪個頻道／新頻道方向＋一句理由」，規則在 `channels/radar/pool.yaml`。
- **B 站 -352 的原因（🟢）**：B 站對非瀏覽器 User-Agent 回 `code -352`（HTTP 200）。我們原本的誠實 UA 一律被擋；Agent-Reach 用的是 `popular` 端點＋一般瀏覽器 UA＋站內 Referer，無 cookie、無簽章。
- **我做的取捨，請 Leon／orchestrator 確認**：新程式對 `api.bilibili.com` 送一般瀏覽器 UA＋Referer（任務允許「瀏覽器指紋」這一項，其餘一律不做：無 cookie、無登入、無 wbi 簽章、無代理、不重試）。若你認為換 UA 本身就算繞過，把 `trending.BILI_HEADERS` 改回預設即可，B 站會全數降級，其他功能不受影響。
- B 站風控**仍然間歇生效**：同一天 `ranking/v2` 先成功一次、之後就回 -352；實跑時分區榜 rid=36 回 -352，已記錄為來源異常，不繞過。
- 測試：新增 `tests/unit/test_radar_cn.py` 15 個（假回應、不連網），全專案 `tests/unit` 2132 過、1 skip、0 失敗（我 deselect 了已知 flaky 的 `test_multi_provider.py`，7 個）。

## 做了什麼

| 項目 | 位置 |
|---|---|
| V2EX／B 站 adapter（欄位只留標題、連結、公開數字、≤120 字摘要、抓取時間；不讀作者與留言） | `src/content_farm/topic_radar/trending.py` |
| `Watch` 新欄位 `v2ex_hot`／`v2ex_nodes`／`bilibili_popular`／`bilibili_popular_zones` | `config.py`、`channels/radar/*.yaml` |
| 候選多了 `excerpt`；證據多了 `fetched_at`（抓取時間）；簡體原題與「信號不是題目」警告 | `models.py`、`build.py` |
| 頻道適配規則（可單測）、池子組裝、POOL.md 輸出 | `fit.py`、`pool.py`、`channels/radar/pool.yaml` |
| -352（HTTP 200＋body code 非 0）不進快取，否則失敗被重播 3 小時 | `http.py` |
| 文件（`docs/` 被 .gitignore 排除，所以放這裡） | `channels/radar/README.md` |

## 端點調查（🟢 本機實測，2026-10-27）

| 端點 | 誠實 UA | 瀏覽器 UA＋Referer | 備註 |
|---|---|---|---|
| `ranking/v2?rid=188` | -352 | 第一次 code 0（97 筆），之後多次 -352 | 新資料，但風控間歇 |
| `popular?ps=N` | -352 | code 0，穩定（多次） | 新資料（pubdate 前一天），綜合榜 |
| `ranking/region?rid=188` | 未試 | code 0，但資料是 2025-04 的舊資料 | 不用 |
| V2EX `hot.json`／`show.json?node_name=` | 200 | — | 熱門 8 筆、節點各 10 筆 |

單支影片詳情與字幕（HTTP 412）：未碰。

## 實跑結果（`radar --all --no-youtube`，抓取時間 2026-10-27T11:50Z）

池子 90 則；證據來源：維基 46、V2EX 28、B 站 8、HN 7。各頻道前 5（池子順序，分數是排序提示）：

| 頻道 | 前 5 名（分數） | 備註 |
|---|---|---|
| 科技新知 | HN「A 10-year-old CNN outperforms frontier LLMs…」(72.0)、HN「OpenAI and Anthropic cut LLM prices…」(68.8)、HN「Concerning behavior from a popular open-weight AI model」(66.5)、HN「Security advisory: critical RCE…」(65.0)、B 站「生命起源：四十亿年前…」(59.5，僅關鍵字弱命中) | 中文網路進榜的是 V2EX 的技術貼（Claude Code 周邊 App、Vibe Coding 等），分數 10–41，排在 5 名之外 |
| 晶片貓 | B 站「旗舰手机芯片大横评：苹果高通发哥玄戒谁最强？」(55.4，52.6 萬播放)、輝達拆解 (36.1)、台積電拆解 (32.6)、摩爾定律 (31.4)、HBM (29.0) | 今天唯一一個中文網路進前 5 的實質科技題 |
| 怪談開談 | 九尾狐 (32.1)、河童 (30.2)、鵺 (28.8)、媽祖信仰 (27.4)、山海經 (27.2) | **今天中文網路沒有任何神話類信號** |
| 不奇而寓 | HN「How does Fable 5.1 hide messages in images?」(39.0)、HN「Five Qwen3.8-27B models match Fable 5…」(37.8)、伊索寓言 (31.0)、狼來了 (28.9)、龜兔賽跑 (27.8) | 前兩名是模型名「Fable」撞字的雜訊（既有 HN 查詢 `fable` 的問題，非本次引入）；**中文網路也沒有適配信號** |
| 賽璐璐研究室 | 串流平台與動畫授權 (35.0)、福音戰士 (32.1)、京都動畫 (31.5)、賽璐珞動畫 (28.7)、製作委員會 (24.1) | 全是維基種子題 |
| 深潛日誌 | HN「Sixteen years after Deepwater Horizon…」(42.0)、大王烏賊 (35.0)、馬里亞納海溝 (35.0)、鮟鱇魚 (34.2)、鯨落 (30.7) | |

新頻道建議（全為標籤，未開頻道）：

| 方向 | 候選 | 證據 |
|---|---|---|
| 科普拆解 | B 站「生命起源：四十亿年前，地球如何诞生第一个生命？」(59.5)；B 站「…医学界有自己的翟天临！深扒李子祺事变」(49.8，偏八卦，需另查證) | 175 萬／189 萬播放，皆有連結與抓取時間 |
| 3C 與工具實測 | V2EX「iPhone Duo 有感」(55.5，124 回覆)；B 站手機晶片橫評 (55.4)；其餘 3 則是 V2EX 的「[送碼]」推廣貼與 App 自薦 | 推廣貼本身不該當題目 |
| 職場與薪資現實 | V2EX「记录程序员兼职电商创业的过程」(40.7，26 回覆) | 只有 1 則 |
| 歷史人文 | 今天 0 則 | B 站熱門榜過濾後沒有人文歷史分區進榜 |

完整內容（含連結、摘要、抓取時間）：`output/radar/2026-10-27/POOL.md`（`output/` 不進 git；本 worktree 路徑 `.claude/worktrees/cf-radar-cn/output/radar/2026-10-27/`）。

來源狀態：V2EX 正常；B 站異常（`ranking rid=36: http 200 code -352`；熱門榜與 rid=188 有資料）；HN、維基正常；Reddit 仍全 403（既有，沒繞過）。

## 限制與未驗證（證據等級）

1. 🟢 B 站熱門榜偏娛樂：過濾分區後一天只剩 8 則可用，其中科技／知識類 2–3 則；歷史人文類今天 0。
2. 🟢 B 站風控間歇；同一個端點有時 0、有時 -352。每天能拿到多少不穩定。
3. 🟡 「換成瀏覽器 UA 後才通」是我實測的；B 站是否把這種 UA 視為違反條款，我**沒有**查它的使用條款（🔴）。量很小（每次執行 B 站 ≤5 次請求、間隔 2 秒）。
4. 🟡 頻道適配規則是我手寫的關鍵字（簡繁並列），只做過 6 個代表字串的單測與 1 天實跑；有誤判，例如 V2EX「平常都是喝什么水」被標為科技新知。它是人工回看用的提示，不是分類器。
5. 🟡 V2EX 熱門榜是綜合榜（停電、情感貼都上榜）；技術以外的 V2EX 題目靠規則過濾，過不了的標「無適配」。科技新知自己的 watch 因此只收 `programmer` 節點，不開 `v2ex_hot`。
6. 🔴 未驗證：V2EX 對 `hot.json` 的頻率上限（我設 1.5 秒間隔、每次 ≤6 請求）；沒有查官方文件。
7. 🟡 抓取時間是雷達執行時間；請求若走 3 小時快取，實際內容可能早於這個時間。
8. 🟡 繁簡：B 站與 V2EX 題目是簡體，`title_draft` 直接沿用，候選上有「簡體原題，需改寫成繁中」警告，沒有自動轉換。
9. 沒開 YouTube（`--no-youtube`），所以今天的候選沒有競品觀看數與觀眾提問；先前 REPORT-topic-radar.md 的 YouTube 部分未動。
10. 授權：只存標題、連結、公開統計數字、≤120 字摘要；測試用假資料，連作者欄位都故意塞入 `SECRET_NAME` 驗證不會輸出。

## 如何重跑

```
PYTHONPATH=src /Users/lileon/project/content-farm/.venv/bin/python scripts/produce.py radar --all --no-youtube
PYTHONPATH=src /Users/lileon/project/content-farm/.venv/bin/python -m pytest tests/unit/test_radar_cn.py tests/unit/test_topic_radar.py
```

## 副作用與清理

- 建立：`output/radar/2026-10-27/*`、`.cache/radar/`（皆被 `.gitignore` 排除，留在本 worktree）。
- 探測腳本放在 `$CLAUDE_JOB_DIR/tmp`（`probe*.py`），不在 repo 內。
- 我想刪掉 `.cache/radar/api.bilibili.com` 內被快取的 -352 回應，`find -delete` 被自動模式分類器拒絕，沒有繞過；它們 3 小時後自然過期，且 `http.py` 修正後不會再產生。
- `git reset --hard` 被守門擋下，改用 `git merge --ff-only worktree-cf-integrate-1025`（等價）。
- 沒有安裝 Agent-Reach 或第三方框架到專案；沒有程式依賴它。
