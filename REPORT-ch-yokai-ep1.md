# REPORT — 妖怪溯源所 EP1〈九尾狐不是一開始就是狐狸精〉

## TL;DR

- 片子做好了，停在成片閘門等 Leon 審。檔案在 `output/yokai-kyubi/assembly/draft.mp4`，1920×1080，片長 9:06（545.8 s），61.3 MB。配音是 macos_say 機器聲。🟢
- QC 結果 **0 error、0 warn**。10 件公有領域／CC0 畫作逐張寫進 `credits.json`（共 12 筆，有兩張用了兩次），沒有 pending，也沒用到大英博物館的來源。🟢
- 新增 `artwork` 媒體種類，每張畫都要有授權連結和出處，NC 授權在載入時就擋掉；另外寫了 Commons 抓圖腳本，會把 API 回傳的授權資料一起存下來。🟢
- 依 orchestrator 追加的兩項，新增 `produce.py manual-kit`，產出手動上傳包和離線預覽頁 `upload/manual/preview.html`。🟢
- 需要 Leon 決定：成片審片、「變造或合成內容」要勾哪一項、縮圖（目前只是暫代）、要不要只用館方 CC0 的圖。

等級：🟢 本機實測、可重跑；🟡 只驗到存在或二手資料；🔴 推論或未驗證。

## 1. 選題與選題池

- 調查推薦的前五題中，選了**九尾狐**當開台第一支。🟢
  - 公有領域素材最多：古今圖書集成、北齋、國芳、芳年、石燕都有，Met 和 Rijksmuseum 也有 CC0 件。
  - 魔神仔幾乎沒有公有領域圖可用。
  - 不碰原住民族題材。
- 選題池 `channels/backlog/yokai.yaml` 共 7 題（長片 6、短片 1）：九尾狐、九尾狐圖鑑卡、天狗、饕餮、東西方的龍、河童、魔神仔。`produce.py plan` 讀得到這份檔案。🟢

## 2. 成片

| 項目 | 值 |
|---|---|
| 成片 | `/Users/lileon/project/content-farm/.claude/worktrees/cf-ch-yokai-ep1/output/yokai-kyubi/assembly/draft.mp4` |
| 為什麼是 draft | `rig_ready: false`，所以跳過角色疊加，沒有 final.mp4 |
| 片長／大小 | 545.8 s（9:06）／61.3 MB（QC 量到的視訊軌是 544.1 s） |
| 結構 | 29 張投影片、7 個章節、講稿 2,649 字 |
| 畫面組成 | 10 張 artwork（Ken Burns 推近，整幅不裁切，右上角有作者／年代／公共領域字卡），其餘是動態投影片 |
| 審核頁 | `output/yokai-kyubi/review/final.html`（gate_final 等待中） |

截圖都在 `docs/examples/ch-yokai-ep1/`：

- 成片截圖：`final_075s_kokon.jpg`、`final_195s_mural.jpg`、`final_290s_compare.jpg`、`final_370s_sekien.jpg`
- `media_contact_sheet.png`
- `thumbnail.png`
- 文章、deck、sources、credits、artwork manifest、qc_report 的副本，以及 `manual_upload_README.md`

各閘門狀態：

- `gate_article`、`gate_deck`、`gate_media`：依共同背景的例外，以 `--by claude-draft` 核可，每一筆都附了自審 note。
- `gate_final`：**沒有碰，留給 Leon。**

所以 `package` 這一步還沒跑，`upload/youtube_meta.json` 也還不存在。Leon 核可後執行下面這行，就會產生 `youtube_meta.json`（`privacy_status: private`）：

```
python scripts/produce.py run --run-dir output/yokai-kyubi --mock-voice --no-stock
```

### 各步驟耗時（本機實測）🟢

| 步驟 | 耗時 |
|---|---|
| article | 0.2 s |
| deck | 0.3 s |
| slides | 26.9 s |
| voice（macos_say） | 70.2 s |
| media（重跑那次；第一次是 767 s） | 724 s |
| assembly | 328 s |

全機負載一直在 28–35 之間。所有步驟都帶 `--max-load 30` 跑，有等過渲染鎖。

### QC（`qc/qc_report.json`）🟢

| 檢查項 | 結果 |
|---|---|
| media_policy | ok |
| credits | 12 筆，none pending |
| 字幕安全區 | ok |
| 解析度 | 1920×1080 |
| 片長 | 544.1 s（頻道目標 480–720 s） |
| 音畫差 | 1.69 s |
| 黑幀 | 沒有 ≥0.5 s 的黑段 |

## 3. 寫稿

- **比喻**：每個名詞先用比喻講，再給定義。祥瑞比作「老天爺蓋給皇帝的章」，志怪比作「古代版都市傳說合輯」，妖怪譜系比作「追一個迷因從哪個論壇冒出來」。🟢
- **八卦都有來源**：共 6 則 gossip beat，全部附 `source_ids`。🟢
  - 吃了九尾狐的肉能辟邪（南山經）
  - 《白虎通》：九條尾巴＝子孫繁盛
  - 《玄中記》的狐狸升級表
  - 《封神演義》第 1 回寫「千年狐狸精」，到第 97 回才出現「九尾」
  - 國芳畫題簽上的「惡狐華陽夫人」
  - 2022 年殺生石裂開：那須町觀光協會新聞稿＋《衛報》
- **冷笑話**：7 則，和八卦交替出現（例如大禹被狐狸「催婚」、殺生石的詛咒一部分是火山化學）。
- **資料截至**：投影片頁腳和說明欄都標了 2026-10。
- **檢查結果**：deck 用 `--strict` lint 通過；`check_article` 0 problem。🟢
- **原典核對**：全部改用維基文庫的原文，沒有餵現代譯本。
  - 研究 subagent 打開頁面核對過：南山經、海外東經、大荒東經郭璞注、白虎通、吳越春秋、玄中記、朝野僉載、封神演義第 1／97 回。🟢
  - 「禹三十未娶……白者，吾之服也；其九尾者，王之證也」這句，我另外用 WebFetch 逐字核過。🟢
- **研究過程修正的常見錯誤說法**：🟢
  1. 「太平則出而為瑞」是《大荒東經》的郭璞注，不在《海外東經》。
  2. 《封神演義》開頭幾回沒有「九尾」兩個字。
  3. Commons 上檔名寫 "Yanju's tomb" 的壁畫，描述其實是**甘肅酒泉丁家閘五號墓**（5 世紀）。我一度誤標成高句麗，已經改掉。
- **片中自己承認查不到的事**（第 18 張投影片「我們還沒查到的事」）：🟡
  - 《武王伐紂平話》只看到轉引（澎湃新聞）
  - 宋代轉折沒有學者給出明確年份
  - 鳥山石燕畫冊的說明文字沒有取得
- **只有二手支撐、沒有直接原典的說法**：🟡
  - 「三國妖婦傳把華陽夫人→妲己→玉藻前串成同一隻狐狸」：鹿兒島大學的書目頁只能證明這本書和 1803 這個年份。串連的直接證據是國芳那張畫題簽上寫的「惡狐華陽夫人」。
  - 「玉藻の草紙是室町作品」：辭典頁只寫「室町時代以降」。
- **沒驗到的**：發音表（妲己、張鷟、玉藻前）在 macos_say 下讀得對不對，我沒有逐句聽。🔴

## 4. 畫作與授權（credits 摘要）

每件作品的授權字串、授權連結、作者和日期都取自 Commons API 的 `extmetadata`。原始回應存在 `assets/artwork/<id>.commons.json`，可以稽核。🟢

| id | 作品 | 授權 | 收藏／來源 |
|---|---|---|---|
| hokusai_fox | 葛飾北齋〈白面金毛九尾之妖狐〉 | CC0 | **Met 56.121.31** |
| gakutei_tamamo | 八島岳亭〈玉藻前と三浦介〉 | CC0 | **Met DP135896** |
| dijian_daji | 《帝鑑圖說》妲己害政（約 18 世紀） | CC0 | Commons（書格掃描） |
| kokon | 《古今圖書集成》九尾狐圖 | PD | Commons |
| yanju_fox | 酒泉丁家閘五號墓壁畫（5 世紀） | PD | Commons（原始出處是 sohu 文章） |
| daji_1814 | 《夏商合傳》妲己 | PD | Commons |
| sekien_tamamo | 鳥山石燕〈玉藻前〉1779 | PD | Commons（掃自 1992 年國書刊行會的復刻本） |
| sekien_sessho | 鳥山石燕〈殺生石〉1780 | PD | Commons（同上） |
| hanzoku | 歌川國芳〈天羅國班足王・惡狐華陽夫人〉 | PD | Commons（visipix） |
| yoshitoshi_tamamo | 月岡芳年〈那須野原殺生石之圖〉1891 | PD | Commons（畫商網站掃描） |

- 每件作品在說明欄只列一次。🟢
- 片中每張畫的右上角都有字卡，例如「圖｜鳥山石燕〈玉藻前〉1779・公共領域」。🟢
- **刻意排除**：搜尋結果裡標「BM …」的大英博物館來源件（國芳〈那須野〉、〈本朝水滸傳〉等）。調查已指出大英博物館是 NC 授權。🟢

## 5. 程式變更（commit 在本分支）

1. **`artwork` 媒體種類**
   - 新增 `src/content_farm/explainer/artwork.py`，`deck.py`、`media.py`、`ffmpeg_ops.artwork_plate`、`cards.py`、frame 模板與 CSS、`lint.py`（artwork 計入 footage 比例）、`to_script.py`、`qc.policy_findings` 都有對應修改。
   - manifest 的檔名是 `assets/artwork/artwork.json`。
   - 缺圖時會出現「畫作待補」佔位，並寫進 credits 的 `pending`。QC 會把它判成 error。
2. **`scripts/fetch_commons_artwork.py`**：提供 `search` 和 `fetch` 兩個子指令。授權不是 PD 或 CC0 的檔案會直接拒抓。
3. **Bug 修正**：media 步驟的輸入指紋原本沒包含 `assets/artwork/*`，所以換圖不會重跑 media，也不會重開 media 閘門。已補上。
4. **AI 揭露文字依 credits 決定**：credits 裡有 AI 圖時，才寫「配音與部分插圖為合成內容」；沒有的話，改寫成「配音為合成語音；畫面無 AI 生成圖像」。原本那句對這支片是不實陳述。
5. **`produce.py manual-kit`**（orchestrator 追加項目 1、2）
   - 新增 `production/manual_kit.py` 和 `production/preview.py`。
   - 產出到 `upload/manual/`：
     - `README.md`：照 Studio 上傳畫面的順序寫，含目標頻道、兒童內容＝否、合成內容的勾選建議、播放清單、片尾畫面建議、私人可見度。機器聲會自動從 `logs/voice.log` 偵測，偵測到就在最上方加警示。
     - `title.txt`、`description.txt`、`tags.txt`
     - `subtitles.srt` 和 `subtitles.vtt`
     - `thumbnail.png`：1280×720，369 KB
     - `preview.html`：單一檔案、離線可開，不用外部 CDN。
   - `preview.html` 的設計：
     - 字幕把 cue 直接嵌在頁面裡，再用 `addTextTrack` 載入。原因是 Chrome 從 `file://` 開檔時會擋 `<track src>`（這是我依過去經驗做的設計，**沒有實際開瀏覽器驗證**，依指示也不該開）。🔴
     - 章節可以點擊跳轉。
     - 頂端狀態列顯示配音來源、QC 結果、片長、檔案大小。
     - Shorts 會用 9:16 的直式播放器。
   - 還沒有 `youtube_meta.json` 時，會臨時用 `build_meta` 產生內容，並在終端機印出提示。
   - 產物路徑：
     - `output/yokai-kyubi/upload/manual/README.md`
     - `output/yokai-kyubi/upload/manual/preview.html`

### 測試 🟢

```
PYTHONPATH=<wt>/src .venv/bin/python -m pytest tests -q -p no:cacheprovider
→ 1 failed, 1049 passed, 1 skipped
```

- 唯一失敗的是 `test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results`。基準分支 `d9749c1` 的報告就記錄過同一支失敗，不是本分支造成的。
- 新增 20 項測試：
  - `test_explainer_artwork` 12 項，其中 ffmpeg 測試用一張直式長卷確認整幅畫不會被裁切
  - `test_production_manual_kit` 6 項，涵蓋 `</script>` 跳脫、離線無 CDN、縮圖尺寸
  - `test_production_qc` 2 項（artwork 政策、AI 揭露）
- 既有的 meta 測試改成預期新的揭露文字。
- 新檔都通過 `ruff check`。
- 跑測試時 worktree 裡沒有 `.env`。

## 6. 需要 Leon 決定

1. **審成片**：審核頁 `output/yokai-kyubi/review/final.html`。核可指令：
   ```
   python scripts/produce.py approve --run-dir output/yokai-kyubi --gate final
   ```
2. **「變造或合成內容」要勾哪一項**：頻道設定是 `ai_disclosure: true`，所以 README 建議勾「是」。但畫面沒有擬真的合成人物或事件，只有旁白是合成語音，依 YouTube 的規定可能不需要勾。要改成「否」的話，說明欄的揭露文字仍會保留。🟡
3. **縮圖**：目前只是第 3 秒的影片截圖，畫面上帶著燒進去的字幕，只能暫代。正式縮圖要等 roadmap R2「縮圖套品牌」。🟢（現況）
4. **畫作來源要不要更嚴格**：
   - 目前 10 件裡只有 2 件來自館方 CC0（Met），另有 1 件是上傳者自行聲明 CC0。
   - 其餘 7 件是 Commons 的 PD-Art：作者都已過世百年以上，但掃描來源是復刻書、畫商網站等。
   - 若要「只用館方 CC0」，石燕的兩件、芳年、國芳要找 Met／Rijksmuseum 的同作品替換，或者拿掉。
5. **換真配音**：Fish Audio 的 key 到了之後，從 voice 之後重跑：
   ```
   python scripts/produce.py run --run-dir output/yokai-kyubi --allow-paid --force voice
   ```
   我沒有呼叫付費 TTS。
6. **`check_article` 的必備章節是科技頻道的形狀**（a-chain、a-taiwan、a-numbers）。這支片沿用了那些錨點名稱，但標題換成神話的內容。要做 `myth` category 和專屬的章節模板，對應 roadmap。🟡
7. **小毛病**：artwork 上緣會被頂部的標題列遮掉約 30 px。要調整的話，改 `artwork_plate` 的垂直偏移就好。🟢

## 7. 副作用與清理

- `output/yokai-kyubi/`：本次的 run-dir，已 gitignore。內含 10 張原圖、clips、draft.mp4（61 MB）和 media 中間檔。審完可以刪；`rm` 在 deny 清單，留給 orchestrator 處理。
- `PROGRESS-ch-yokai-ep1.md`：進度紀錄，沒有 commit。
- job tmp `/Users/lileon/.claude/jobs/91e11b49/tmp/` 裡有：`deck_body.json`（deck 原稿）、`build_deck.py`、`clean_institution.py`、`research-kyubi.md`、`f21.png`。job 刪除時會一起清掉。
- 沒有複製 `.env`（全程 `--no-stock`），沒有呼叫 Pexels，也沒有付費 API。沒開瀏覽器，沒用 AI 生圖。
- 對外的網路請求只有 Wikimedia Commons API 和 upload.wikimedia.org（抓 10 張圖），以及 WebFetch 讀維基文庫。
- `docs/` 在 `.gitignore` 裡，所以 `docs/examples/ch-yokai-ep1/` 是用 `git add -f` 加入的。
