# 選題雷達：中文網路來源與跨頻道選題池

指令：`python scripts/produce.py radar --all`（或 `--channel <c> --pool`）。除了每頻道的 `<channel>.json`，多寫 `output/radar/<日期>/POOL.json` 與 `POOL.md`。

## 新增來源

| 來源 | 端點（公開、免登入） | 取什麼 | 注意 |
|---|---|---|---|
| V2EX 熱門／節點 | `www.v2ex.com/api/topics/hot.json`、`/api/topics/show.json?node_name=<節點>` | 標題、連結、回覆數、發文時間、前 120 字摘要 | 熱門榜是綜合榜（生活、情感也上榜）；`share` 節點全是推廣貼，已不收 |
| B 站熱門 | `api.bilibili.com/x/web-interface/popular?ps=50` | 標題、連結、播放／讚／留言數、分區、前 120 字簡介 | 綜合榜、偏娛樂；用 `bilibili_popular_zones` 只留指定分區 |
| B 站分區榜 | `x/web-interface/ranking/v2?rid=<分區>` | 同上 | 資料新，但 B 站風控會間歇回 `code -352`，失敗就降級 |

不收：作者／發文者名稱、回覆與留言內容。`ranking/region`（舊分區榜）會回數個月前的舊資料，不用。

### 為什麼之前是 -352
B 站對非瀏覽器 User-Agent 一律回 `code -352`（HTTP 仍是 200）。現在只對 `api.bilibili.com` 送一般瀏覽器 UA＋站內 Referer，**不帶 cookie、不登入、不簽章（wbi）、不走代理**；仍被風控就記錄為異常並略過，不重試、不換招。`-352` 這種「HTTP 200 但 body code 非 0」的回應不進快取（否則失敗會被重播 3 小時）。

## 選題池
`channels/radar/pool.yaml`：
- `watch`：池子自己的中文網路來源（與各頻道的 `watch` 同一個 schema）。
- `rules`：頻道適配規則。`target` 是頻道代碼，或 `new-…`（新頻道方向，只是標籤）；`keywords` 簡繁都寫；ASCII 關鍵字比對整個單字，中文比對子字串；`min_hits` 預設 1。
- 每則候選最多標 2 個現有頻道＋1 個新方向，來源頻道（種子題）一定排第一。同一則出現在多個頻道（同網址／同主題）合併成一筆。

## 如何擴充
- 新來源：在 `trending.py` 加 `fetch_xxx(...) -> list[Signal]`（只留標題、連結、公開數字、短摘要）；`models.SourceName` 加名字；`scoring.TREND_REFERENCE` 加「滿分參考值」；`build._trending_jobs` 掛上；`build.HOST_SOURCE`、`http.HOST_SPACING` 補主機。
- 新頻道方向：在 `pool.yaml` 加一條 `target: new-xxx` 規則即可。
- 單測：`tests/unit/test_radar_cn.py`（假回應，不連網）。

## 隱私與授權
輸出只在 `output/radar/`、快取只在 `.cache/radar/`（都被 `.gitignore` 排除，不得 commit）。只存標題、連結、公開統計數字、短摘要與抓取時間。
