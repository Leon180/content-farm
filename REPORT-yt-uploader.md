# REPORT — YouTube 多頻道授權＋上片包 API 上傳工具

## TL;DR
- 5 個頻道各一組 token（`CF_YOUTUBE_REFRESH_TOKEN_<CHANNEL>`，沒有就退回共用的；technews → chipcat）。授權腳本與上傳腳本都寫好、有 mock 測試；**沒有呼叫任何 API、沒有上傳**。
- 全套 pytest：2015 passed, 1 skipped（`test_multi_provider` 7 個已排除，既有失敗）。🟢
- **有 3 支長片目前會被擋：說明欄超過 YouTube 的 5000 bytes 上限**（chipcat 6318、yokai 7208、deepsea 5465）。要 Leon 先把 `metadata.md` 的說明欄縮短（例如把來源清單搬到置頂留言）。腳本不會自動截斷，因為尾端是授權／AI 示意圖揭露。
- 配額：預設 10,000 單位／天，只夠一天上 6 支（見下）。

## Leon 要跑的指令（每頻道一行；在 content-farm repo 根目錄）
先確認 `.env` 已有 `CF_YOUTUBE_CLIENT_ID` / `CF_YOUTUBE_CLIENT_SECRET`。每支都會開瀏覽器，在 Google 帳號選擇器選對應的品牌頻道，終端機會印「已授權頻道：<名稱>」，核對後輸入 `y` 才寫入 `.env`（不印 token）。已存在同名變數會拒絕，要覆蓋加 `--replace`。

```
.venv/bin/python scripts/get_youtube_token.py --channel chipcat
.venv/bin/python scripts/get_youtube_token.py --channel cel
.venv/bin/python scripts/get_youtube_token.py --channel yokai
.venv/bin/python scripts/get_youtube_token.py --channel deepsea
.venv/bin/python scripts/get_youtube_token.py --channel fable
```

授權完先 dry-run，再正式上傳（一律 `privacyStatus=private`）：

```
.venv/bin/python scripts/upload_pack.py --dry-run
.venv/bin/python scripts/upload_pack.py --only technews-hn-50195959   # 先單支試
.venv/bin/python scripts/upload_pack.py                                # 照 INDEX 順序，配額不夠就停
```

- 預設 `--pack-dir output/upload-20261024`（相對於 repo 根目錄；output/ 不進 git，所以在 worktree 裡要用 `--pack-dir` 指絕對路徑）。
- 每支成功寫 `<資料夾>/upload_result.json`（videoId、Studio 連結、頻道名稱）；已有此檔的會跳過，`--force` 才重傳。
- 上傳前先 `channels.list mine=true` 確認 token 對應的頻道（日誌會印頻道名稱）。
- 置頂留言（chipcat、yokai）只印提醒，不自動留言。

## 做了什麼
| 檔案 | 內容 |
|---|---|
| `src/content_farm/youtube/channel_tokens.py` | 頻道清單、`technews→chipcat` 別名、token 解析（專屬優先、共用退回） |
| `src/content_farm/youtube/env_file.py` | 原子寫入 `.env`，只追加／（`replace`）取代單行，保留權限與其他行 |
| `src/content_farm/youtube/quota.py` | 本機配額帳本（太平洋時間日界；API 不回報用量，只能自己記） |
| `src/content_farm/youtube/pack.py` | 解析 INDEX.md＋metadata.md（頻道、標題、說明欄、標籤、縮圖、合成內容旗標、類別） |
| `src/content_farm/youtube/pack_upload.py` | dry-run 描述、上傳流程（配額檢查、結果檔、縮圖失敗保留 videoId） |
| `google_provider.py` / `factory.py` | 新增 `get_authorized_channel()`；`create_youtube_uploader(settings, channel=...)` |
| `scripts/get_youtube_token.py` | `--channel`，授權→核對頻道名→確認→追加 `.env` |
| `scripts/upload_pack.py` | `--dry-run` / `--only` / `--limit` / `--include-unlisted` / `--force` |
| `tests/test_youtube_pack_upload.py` | 23 個測試（全 mock，含「dry-run 不碰 API」） |

說明：INDEX 的 `不建議上傳` 列（deepsea-short-1）自動排除；`--only` 指到它會報「no such folder」。

## 配額估算
- 單位：`videos.insert` 1600、`thumbnails.set` 50、`channels.list`（頻道核對）1。Short 1601、長片 1651。
- 預設日配額 10,000（`CF_YOUTUBE_DAILY_QUOTA` 可改），專案內所有頻道共用，太平洋午夜重置。
- 目前 11 支共需 17,861 → 一天放不完。**第一天（照 INDEX 順序、跳過被擋的 3 支）：technews×2、cel、deepsea-short-2、fable-asymmetry、fable-confirmation，共 9,656，剩 344，下一支起停止。** 第二天：fable-gradient、fable-ess，加上說明欄修好後的 chipcat、yokai、deepsea 長片，約 8,205。
- 帳本只記這支腳本的花費；若在 Studio／別的工具用了 API 配額，要自己調 `CF_YOUTUBE_DAILY_QUOTA`。可到 Cloud Console 申請提高配額／稽核（未稽核的專案上傳的影片會被鎖成私人，所以腳本固定 private）。

## dry-run 輸出（對現有上片包，未呼叫 API；token 顯示 MISSING 是因為 worktree 沒有 `.env`）

```
pack: /Users/lileon/project/content-farm/output/upload-20261024  (11 videos)  mode: DRY-RUN

[technews-hn-50195959]  Short
  channel    : chipcat  (token: MISSING)
  title      : 晶片貓快報｜Quad9 宣布 11 月 24 日退出法國 #Shorts
  description: 528 chars / 934 bytes
  tags       : Shorts, 晶片貓快報, 晶片貓, 科技新聞, DNS, Quad9, 法國
  category   : 28
  thumbnail  : (none)
  containsSyntheticMedia: false
  privacyStatus: private
  quota      : 1601 units

[technews-hn-50202217]  Short
  channel    : chipcat  (token: MISSING)
  title      : 晶片貓快報｜AI 開始替程式碼寫數學證明 #Shorts
  description: 606 chars / 1000 bytes
  tags       : Shorts, 晶片貓快報, 晶片貓, 科技新聞, AI, 資訊安全, 形式化驗證
  category   : 28
  thumbnail  : (none)
  containsSyntheticMedia: false
  privacyStatus: private
  quota      : 1601 units

[chipcat-cowos-v4]  長片
  channel    : chipcat  (token: MISSING)
  title      : AI 晶片為什麼卡在台積電這一關？產能一直翻倍，為什麼還不夠
  description: 4788 chars / 6318 bytes
  tags       : CoWoS, 先進封裝, 台積電, AI晶片, 輝達, 半導體, 產業拆解
  category   : 27
  thumbnail  : thumbnail.jpg
  containsSyntheticMedia: false
  privacyStatus: private
  quota      : 1651 units
  reminder   : 公開後手動貼置頂留言 ← pinned-comment.txt
  PROBLEM    : description 6318 > 5000 bytes

[cel-run2-v4]  長片
  channel    : cel  (token: MISSING)
  title      : 動畫市場創新高，為什麼六成接案的動畫公司說光靠製作費就是赤字？
  description: 1615 chars / 2979 bytes
  tags       : 動畫產業, 製作委員會, 公取委, 動畫外包, 取適法, 賽璐璐研究室
  category   : 27
  thumbnail  : thumbnail.jpg
  containsSyntheticMedia: false
  privacyStatus: private
  quota      : 1651 units

[yokai-kyubi-v3]  長片
  channel    : yokai  (token: MISSING)
  title      : 山海經說九尾狐會吃人，漢代書裡也說牠是吉兆
  description: 4793 chars / 7208 bytes
  tags       : 九尾狐, 妖怪, 山海經, 妲己, 玉藻前, 封神演義, 殺生石, 浮世繪, 妖怪溯源所
  category   : 27
  thumbnail  : thumbnail.jpg
  containsSyntheticMedia: false
  privacyStatus: private
  quota      : 1651 units
  reminder   : 公開後手動貼置頂留言 ← pinned-comment.txt
  PROBLEM    : description 7208 > 5000 bytes

[deepsea-giant-squid]  長片
  channel    : deepsea  (token: MISSING)
  title      : 大王烏賊：為什麼人類這麼晚，才拍到牠活著的樣子？
  description: 4061 chars / 5465 bytes
  tags       : 大王烏賊, 深海, 小笠原, 久保寺恒己, 抹香鯨, 深海生物, 科普
  category   : 27
  thumbnail  : thumbnail.jpg
  containsSyntheticMedia: true
  privacyStatus: private
  quota      : 1651 units
  PROBLEM    : description 5465 > 5000 bytes

[deepsea-short-2]  Short
  channel    : deepsea  (token: MISSING)
  title      : 大王烏賊跟相機拉鋸了 4 小時 #Shorts
  description: 381 chars / 721 bytes
  tags       : Shorts, 深潛一則, 大王烏賊, 深海, 小笠原, 久保寺恒己, 抹香鯨, 深海生物, 科普
  category   : 27
  thumbnail  : (none)
  containsSyntheticMedia: false
  privacyStatus: private
  quota      : 1601 units

[fable-asymmetry-short]  Short
  channel    : fable  (token: MISSING)
  title      : 為什麼最好的燈籠，最先從夜市消失了 #Shorts
  description: 605 chars / 1141 bytes
  tags       : 資訊不對稱, 逆向選擇, 檸檬市場, 經濟學, 寓言, 科普, Akerlof
  category   : 27
  thumbnail  : (none)
  containsSyntheticMedia: false
  privacyStatus: private
  quota      : 1601 units

[fable-confirmation-short]  Short
  channel    : fable  (token: MISSING)
  title      : 貓頭鷹的小本子，為什麼只有一邊寫滿字 #Shorts
  description: 583 chars / 949 bytes
  tags       : 確認偏誤, 心理學, 認知偏誤, 寓言, 科普, Wason, 同溫層
  category   : 27
  thumbnail  : (none)
  containsSyntheticMedia: false
  privacyStatus: private
  quota      : 1601 units

[fable-gradient-short]  Short
  channel    : fable  (token: MISSING)
  title      : 霧裡的小山羊，怎麼靠一個笨方法走到水邊 #Shorts
  description: 727 chars / 1200 bytes
  tags       : 梯度下降, 機器學習, 學習率, 局部最小值, 寓言, AI, 科普
  category   : 27
  thumbnail  : (none)
  containsSyntheticMedia: false
  privacyStatus: private
  quota      : 1601 units

[fable-ess-mid]  長片
  channel    : fable  (token: MISSING)
  title      : 老樹林的山雀，為什麼誰也佔不到便宜
  description: 789 chars / 1485 bytes
  tags       : 演化穩定策略, ESS, 鷹鴿博弈, 賽局理論, 演化生物學, 寓言, 科普
  category   : 27
  thumbnail  : thumbnail.jpg
  containsSyntheticMedia: false
  privacyStatus: private
  quota      : 1651 units

quota day 2026-10-24 (Pacific): used 0 / 10000, remaining 10000; this run needs 17861 (1600/video + 50/thumbnail + 1/channel check) -> will stop partway
```

## 注意與未驗項
- 🟢 解析、配額、runner、`.env` 寫入、dry-run 不碰 API：mock 測試通過。
- 🔴 **真實 OAuth 流程與 `videos.insert` 都沒實跑**（依任務規定不上傳、不開瀏覽器）。`get_authorized_channel()` 與 `access_type=offline, prompt=consent` 只靠 API 文件，首次實跑請先用 chipcat 驗證。
- 類別對照：教育→27、科學與技術→28（metadata 的「類別」欄）；其餘退回 22。
- 說明欄超限的 3 支：腳本回報 PROBLEM 並跳過，不會送出。
- **變數名稱不一致（需 Leon／orchestrator 知道）**：`channels/*.yaml` 的 `youtube.refresh_token_env` 寫的是 `CF_YT_<CHANNEL>_REFRESH_TOKEN`（走 `production/publish.py`），本工具依任務指定用 `CF_YOUTUBE_REFRESH_TOKEN_<CHANNEL>`。兩條上傳路徑目前讀不同變數；我沒改 yaml／publish.py（超出範圍）。要統一的話把 yaml 的值改成新名稱即可。
- 本機環境是 Python 3.10，所以用 `timezone.utc` 而非 `datetime.UTC`。

## 清理
沒有留下暫存檔（dry-run 輸出放在 job tmp，不在 repo）。worktree 根目錄既有的未追蹤 `graft/` 不是我建的，沒動也沒 commit。
