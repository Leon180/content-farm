# REPORT：妖怪溯源所上線準備（封面、頭像、簡介、九尾狐上片資料、縮圖）

## TL;DR
- 封面：Leon 中途更正「不要標語、純背景」，並選定選項 2（卷軸＋狐狸）。純水墨、無任何文字，3 選項＋選項 2 的重生版（2b-1／2b-2，狐狸變大、尾巴扇形）。**尾巴約 11–12 條，不是精確 9 條**（Z-Image 數不準，4 個 seed 都 >9）。拼版 `artifacts/yokai-launch/yokai-banner-v2-sheet.png`、`yokai-banner-v2-2b-sheet.png`（皆附手機中央裁切）。
- 頭像：舊 A/B/C 保留，新增 D（水墨九尾狐）、E（「妖」字朱印）；拼版 `yokai-avatar-v2-sheet.png`（240/96/48 px 圓形預覽）。
- 簡介：妖怪溯源所、不奇而寓各 2 版（皆 <1000 字）。
- 九尾狐說明欄 7208 → **3940 bytes**，`upload_pack.py --dry-run` **無 PROBLEM**；完整出處移到 `pinned-comment.txt`。
- 縮圖 3 選項 `kyubi-thumb-sheet.png`（A 狐臉「原典說牠吃人」最強；B 的字壓在狐身上）。未上傳、未 push。

## 1. 封面（🟢 看過拼版）
- 畫風：九尾狐影片同模型 Z-Image-Turbo ＋ `channels/yokai.yaml` 的 `style_prefix`，seed 8601–8603（選項 1–3）、8611–8614（選項 2 重生）。紀錄 `artifacts/yokai-launch/generation_log.jsonl`（含 prompt、秒數）。
- 無文字：Leon 2026-10-25 經 orch-personal 轉達「不要標語，純背景就好」，所以沒有頻道名、標語、更新時間。最初依任務寫的「書法感標題＋標語」版本（兩側圖＋中央留白）在收到更正時尚未生圖，已丟棄，不在產物內。
- 構圖：主體必須落在手機會看到的中央 1546×423，所以每張都是「主體在正中、周圍淡墨山霧、邊緣羽化進宣紙色」，PIL 後製（`src/compose_yokai.py` 的 `banner()`）把主體對到畫面中心。
- 選項 1 山月＋側身九尾狐；選項 2 卷軸＋狐狸；選項 3 蘆葦＋月牙＋紅狐。**選項 1、3 原圖尾巴只有 3–4 條**（見下），選項 2 重生版才做了多尾。
- 選項 2 重生（2b）：4 個 seed 的 prompt 要求「九條尾巴扇形展開、每條分開」。結果四張都是孔雀開屏式的大扇，尾巴 >9 條；seed 8612 還長出孔雀眼斑，淘汰。挑 8614（2b-1，最乾淨）與 8611（2b-2，墨色偏黑）。若要精確 9 條，沒有可靠辦法（不是 prompt 能控制），只能手改或不宣稱數量。
- 手機中央裁切：2b 的尾尖上緣會被切到一點、卷軸只剩一條邊；狐狸本體與扇形尾仍完整。
- 卷軸原圖左右下角有淡淡的仿印章紋（AI 生成，不是文字），在安全區外。

## 2. 頭像（🟢）
- D：Z-Image 水墨九尾狐剪影（seed 8402，同 prompt 另一張 seed 8401 未用），裁成較緊構圖。48 px 時仍認得出是狐加扇尾，但灰階偏淡、不如舊 A/B 醒目。
- E：「妖」字朱文印章，PIL 以 macOS 系統字型 Weibei TC 合成（字型只渲染成像素，沒有散布字型檔），邊緣加墨跡粗糙與紅色斑駁；48 px 最清楚。
- 我的偏好（不定案）：E 小圖最穩、與水墨封面最搭；舊 B 次之。

## 3. 頻道簡介
- `artifacts/yokai-launch/about-yokai.md`（版本 A 375 字、B 289 字）、`about-fable.md`（A 353、B 223），字數為程式實測。
- 內容事實來源：`channels/yokai.yaml`、`channels/fable.yaml`（隔週一支長片、Shorts 每週一／三支、公共領域畫作、AI 揭露）。聯絡方式留空。
- 注意：`channels/yokai.yaml` 的 `cadence.publish_days` 寫週六、`publish` 區塊寫週五，兩者不一致；簡介只寫「隔週」，沒寫星期。

## 4. 九尾狐上片資料（🟢 dry-run 實跑）
- 原檔備份：`output/upload-20261024/yokai-kyubi-v3/metadata.md.bak`、`pinned-comment.txt.bak`（`output/` 在 gitignore，不進 repo）。腳本 `artifacts/yokai-launch/src/shrink_metadata.py`（讀 .bak，可重跑）。
- 說明欄保留：抬頭、章節、摘要、11 條主要原典（山海經南山經／海外東經、白虎通、吳越春秋、玄中記、朝野僉載、封神演義第一回、玉藻前、殺生石、Guardian）、畫作署名清單、AI 示意圖與工具署名、AI 揭露、署名。21 條次要參考與畫作原頁連結移到 `pinned-comment.txt`（5,972 字，<YouTube 留言上限 10,000）。
- 結果：`description: 2278 chars / 3940 bytes`，無 PROBLEM。原始輸出：

```
[yokai-kyubi-v3]  長片
  channel    : yokai  (token: CF_YOUTUBE_REFRESH_TOKEN)
  description: 2278 chars / 3940 bytes
  containsSyntheticMedia: false
  privacyStatus: private
  desc tail  : 本影片由 AI 輔助製作（配音為合成語音；部分插圖為 AI 生成）。
  desc tail  : — 妖怪溯源所
```
- 頻道名／署名：說明欄抬頭「【妖怪溯源所・原典追蹤】」、結尾「— 妖怪溯源所」、標籤含「妖怪溯源所」；標題、說明欄、標籤、置頂留言搜尋「青蛙／蛙／frog」零命中（🟢 grep；零命中前已先確認檔案有內容）。
- **要注意**：dry-run 顯示 `token: CF_YOUTUBE_REFRESH_TOKEN`，而 `channels/yokai.yaml` 設的是 `CF_YT_YOKAI_REFRESH_TOKEN`。上傳新頻道前要確認 pack 用的是新帳號（kaidan1802）的 token，不然會傳到舊頻道。（我沒查是哪個 worktree 的程式決定這個名稱，🟡。）
- `kit/description.txt` 仍是舊版長說明（上傳器不讀它，讀 `metadata.md`），沒改。
- `containsSyntheticMedia` 建議：**圖像維持「否」**——5 張 AI 圖是明顯的水墨插畫、不是擬真影像，且畫面標「AI 示意圖」，不會被誤認為真實影像或真實事件（YouTube 的揭露義務針對「可能被當成真實」的內容）。**但配音要先確認**：頻道設定是 VoxCPM2 以參考聲複製；若參考聲來自一位可辨識的真人（不是 Leon 本人或自行合成的聲音），那是「擬真的真人聲音合成」，建議改填「是」。`yokai-take1.wav` 的來源我沒查（🔴）。metadata.md 的「否」仍是 Leon 2026-10-16 決策 916c2864e31f，我沒改。

## 5. 縮圖（🟢 看過拼版；規則取自 cf-thumbnail-v2 的 `docs/design/thumbnails/rules.md` §5）
| 選項 | 鉤子 | 主體 | 前 60 秒兌現 |
|---|---|---|---|
| A | 原典說／牠吃人（6 字） | 狐臉特寫＋扇尾 | 旁白第 2 句「最早的原典裡，牠會吃人」（script.json 第 2 場，未量秒數） |
| B | 牠本來／不是妲己（7 字） | 九尾狐全身側面 | 第 1 句講妲己、第 2 句講原典吃人，「不會變身也不會魅惑人」在第 6 句（未量秒數，🟡） |
| C | 殺生石／裂開了（6 字） | 裂成兩半的巨石 | 第 3 句起講 2022 年殺生石裂成兩半，並預告片尾揭曉（未量秒數） |
- 刻意**不用「吉兆」當鉤子**：原專案 QC 已指出「漢代吉兆」要到 1:18 才講，違反 H1。
- 規格：1280×720 JPEG（`kyubi-thumb-{A,B,C}.jpg`，約 160–205 KB）；字用 Xingkai TC 書法體、黑字白描邊、重點字朱紅；左上角紅底頻道標籤。168×94 縮小與 2× 預覽在拼版右欄。
- 問題：B 的「牠本來」字距偏鬆、字壓在狐腿上；C 的「狐影」幾乎看不見，主體其實是裂石。我推薦 A。沒有跑程式化的字高／對比 QC（只目視拼版，🔴）。
- 沒接進 `thumbnail_variants` 上傳流程（任務說不上傳）。

## 生圖紀錄
Z-Image-Turbo 4-bit（Apache-2.0），本機 mflux、走 `scripts/heavy`。機器 swap 93% 時排隊約 25 分鐘，每張 172 秒（無負載時 45–85 秒）。共 12 張（封面 7、頭像 2、縮圖 3）；未使用：ykc2b2（孔雀眼斑）、ykc2b3、ykav1。

## 副作用與清理
- 清不掉：`rm` 被拒，`artifacts/yokai-launch/` 內的暫存檔 `_av_contact.png`、`_c2b_contact.png`、`_seal_test.png` 留在磁碟上（已 gitignore 的 `_*.png`，沒有 commit）。
- `output/upload-20261024/yokai-kyubi-v3/` 新增 `metadata.md.bak`、`pinned-comment.txt.bak`，並改寫 `metadata.md`、`pinned-comment.txt`（不在 repo 內）。
- 沒有 push、沒有開瀏覽器、沒有付費服務、沒有上傳。
- repo 大小：已 gitignore `raw/`（21 MB，可由 seed 重生）與 `*-safe.png`；仍 commit 全尺寸封面（每張約 4 MB）。若嫌大，可只留拼版。

## 與派工的偏離
1. 封面依 Leon 更正改成無文字（任務原文要書法標題＋標語）；因此「書法感妖怪溯源所」字樣沒有做，Xingkai 書法體只用在縮圖。
2. 選項 2 重生後，簡報要求的「尾巴盡量接近九條」沒達到精確 9，見 §1。
3. 起始分支：worktree 一開始在 main（`6c47dd1`），已 fast-forward 到 `worktree-cf-brand-kit`（`d11bc27`）再開工。

## 檔案
`artifacts/yokai-launch/`：`yokai-banner-v2-{1,2,3}.png`、`yokai-banner-v2-2b-{1,2}.png`、兩張封面拼版、`yokai-avatar-v2-{D,E}.png`＋拼版、`kyubi-thumb-{A,B,C}.jpg`＋`kyubi-thumb-sheet.png`、`about-yokai.md`、`about-fable.md`、`generation_log.jsonl`、`src/`。
