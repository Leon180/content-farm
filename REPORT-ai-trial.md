# AI 插圖本機試做：3 個模型 × 九尾狐 5 個段落（feat/ai-illustration）

## TL;DR
- 試了 3 個本機開源模型：Z-Image-Turbo 4-bit、FLUX.2 [klein] 4B q4、FLUX.1 [schnell] q4。每個模型各生 5 張（九尾狐的 5 個段落），共 15 張，全部成功。**原始 repo 的 LICENSE 原文都是 Apache-2.0，可以商用** 🟢。
- 速度與記憶體（1024×576，mflux 自報峰值）🟢：
  - **klein 4B**：21–30 s／張，5.8 GB
  - Z-Image：64–74 s／張，4.4 GB
  - schnell：54–62 s／張，13.6 GB
- 我的推薦（🟡 畫面判讀）：**klein 4B 當主力**，最快、最聽 prompt；**Z-Image 當水墨風備選**，筆墨最好看。**schnell 不建議**：它會自己蓋假印章、寫亂碼漢字，而且峰值記憶體是另外兩個的 2–3 倍。
- gallery：`docs/design/ai-trial/gallery.html`（commit，縮圖 768 寬）和 `output/ai-trial/gallery.html`（全尺寸）。總覽圖是 `contact_sheet.png`。每張圖左上角都疊了「AI 示意圖」標籤作示範。
- 依改序指示，**沒有接 pipeline，也沒有動九尾狐成片**。停在這裡等 Leon 選模型。

## 1. 授權（原始 repo 的 LICENSE 原文）

| 模型 | 原始 repo | LICENSE 原文出處 | 結論 |
|---|---|---|---|
| Z-Image-Turbo | `Tongyi-MAI/Z-Image-Turbo`（HF）／`Tongyi-MAI/Z-Image`（GitHub） | GitHub [`LICENSE`](https://github.com/Tongyi-MAI/Z-Image/blob/main/LICENSE)（blob `261eeb9e`，GitHub API 判定 `Apache-2.0`）。全文已讀，是未修改的 Apache-2.0 | 可商用 🟢 |
| FLUX.2 [klein] 4B | `black-forest-labs/FLUX.2-klein-4B` | HF [`LICENSE.md`](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/blob/main/LICENSE.md)：Apache-2.0 全文，176 行，沒有附加條款（grep `commercial` 只命中第 8 條免責） | 可商用 🟢 |
| FLUX.1 [schnell] | `black-forest-labs/FLUX.1-schnell` | GitHub `black-forest-labs/flux` 的 [`model_licenses/LICENSE-FLUX1-schnell`](https://github.com/black-forest-labs/flux/blob/main/model_licenses/LICENSE-FLUX1-schnell)：Apache-2.0 全文 | 可商用 🟢 |

**Z-Image 4-bit 衍生 repo 的授權矛盾**（寫清楚，供日後查）：
- `filipstrand/Z-Image-Turbo-mflux-4bit` 的 card front matter 是 `license: other`、`license_name: tongyi-qianwen-license`，正文寫「inherits the Tongyi Qianwen License」，連結指向 `huggingface.co/Tongyi-MAI/Z-Image-Turbo/blob/main/LICENSE`。
- **那個檔案不存在**。我用 `list_repo_files` 列出原始 HF repo 的檔案，裡面沒有 LICENSE；29 個 commit 的標題也沒有加入或刪除 LICENSE 的紀錄。原始 card 的 front matter 是 `license: apache-2.0`。
- 判讀：衍生 repo 的標示看起來是誤植（套用了 Qwen 系列的舊授權名稱）。轉成 4-bit 不會改變上游授權，上游是 Apache-2.0。🟡（「誤植」是推論；事實部分都是 🟢）
- 如果要完全避開這個疑慮：改用 mflux 從原始 repo 自行量化（`--quantize 4`），但要另外下載約 33 GB。或者直接用 klein，klein 的衍生 repo 標的也是 apache-2.0，沒有矛盾。

**其他已知授權（只看 card，沒讀 LICENSE 檔）**：SDXL-Turbo 是非商用授權，依指示沒有試。FLUX.2 klein **9B** 是非商用授權（只有 4B 是 Apache），所以沒選 9B。🟡

**著作權提醒**：純 prompt 生成的圖，各國多半認定不受著作權保護（二手轉述，見 `design/mascot-quality` 報告 §1）。🔴 這對「示意插圖」影響不大：我們不需要擁有它的著作權，只要授權允許商用。

## 2. 設定

- 段落（`docs/design/ai-trial/prompts.json`）：只挑現行是動畫投影片、**沒有公有領域畫作**的段落：

  | 段落 | 用途 | 內容 |
  |---|---|---|
  | s05 | 場景重建 | 青丘之山的九尾獸 |
  | s09 | 場景重建 | 大禹在塗山遇見九尾白狐 |
  | s12 | 氣氛 | 玄中記：狐狸化成婦人 |
  | s13 | 場景重建 | 唐代百姓家家拜狐神 |
  | s24a | 轉場 | 田邊、墳地、夜裡的狐狸 |

  有真古畫的段落（s01、s04、s11、s15、s17、s19–s25a 的 artwork）都不換。
- 畫風：每個 prompt 都寫了 ink wash／ink and watercolour illustration、`illustration, not a photograph`、`no text`。沒有提到任何畫家名字。
- 參數：
  - 尺寸 1024×576（16:9），seed 42
  - 步數照各模型建議：Z-Image 9 步，klein 和 schnell 都是 4 步
  - 每張圖獨立跑一個 mflux 程序，生完就卸載；兩張之間停 5 秒；一次只跑一張；生圖期間沒有渲染影片
- 工具：
  - `docs/design/ai-trial/run_trial.py`：生圖＋量測。每張圖寫一行 `output/ai-trial/results.jsonl`，可以中斷後續跑。
  - `docs/design/ai-trial/build_gallery.py`：加標籤、做縮圖、出總覽圖和 gallery。
  - 每張原圖都附 `*.metadata.json`（mflux `--make-conf`）和 `*.log`。
- 環境：
  - mflux 0.22 的 venv 和 Z-Image 權重沿用 `design/mascot-quality` 那個 job 的 tmp（`~/.claude/jobs/d3bbd556/tmp/`）
  - klein 和 schnell 下載到本 job 的 tmp：klein 4.62 GB（22 分鐘）、schnell 9.61 GB（48 分鐘），合計 14.2 GB，低於 25 GB 上限
  - 沒有動 repo 的 `.venv`

## 3. 耗時與資源（每張圖都量）🟢

| 模型 | 每張秒數 | mflux 自報峰值 | 程序 RSS 峰值 | swap（跑前 → 最高 → 跑後，MB） |
|---|---|---|---|---|
| Z-Image | 68.1／70.7／63.9／64.3／74.4 | 4.43–4.44 GB | 2.1–3.2 GB | 4524→10111→10111，之後在 10.1–11.2 GB 之間 |
| klein 4B | 29.6／26.1／25.3／23.3／21.1 | 5.78 GB | 2.1–3.0 GB | 10689→11984（逐張小漲） |
| schnell | 62.2／55.0／54.8／54.0／55.0 | **13.56 GB** | 7.1 GB | 8539→**18357**→17337 |

- 秒數包含每張重新載入模型的時間。如果改成常駐程序連續生成，每張會再快一些，但這次照規則一張一卸。
- swap 是整台機器的數字，同時段還有別的 session 在跑，所以**不能全部算在 mflux 頭上**。🟡（歸因）
  - 最清楚的訊號是第一張 Z-Image：swap 從 4.5 GB 跳到 10.1 GB。
  - schnell 跑的時候 swap 衝到 18.4 GB。這和它 13.6 GB 的峰值吻合。
- macOS 不會主動把 swap 縮回去，所以「跑後」的數字比「跑前」高，不代表記憶體洩漏。
- 生圖期間這台機器的 Claude hook 有兩次逾時（`block-dangerous-git.sh: timed out`），可見記憶體壓力真的會影響其他 session。

## 4. 畫面比較（🟡 我的判讀，請 Leon 直接看 gallery）

| 段落 | Z-Image | klein 4B | schnell |
|---|---|---|---|
| s05 九尾獸 | 水墨筆觸最好，**只畫一條尾巴** | **有畫出多條尾巴**，構圖完整 | 一條尾巴，**左下右下自己蓋了紅色假印章** |
| s09 塗山白狐 | 白狐多條尾巴（扇形，數不到九）、旅人背影，最貼 prompt | 白狐只有一條大尾巴，旅人背影 OK | 畫成一位女子加一個小孩，**偏離 prompt**，也有假印章 |
| s12 狐化婦人 | **最好**：窗內是女子剪影，窗外有紅狐 | 只畫了狐狸剪影，沒有變身 | 狐狸剪影旁邊有個女子側影，算勉強 |
| s13 拜狐神 | 繪本風、乾淨，村舍略偏現代 | 氣氛最好，**右側疑似電線桿**（時代錯誤） | **招牌上有亂碼漢字**，又有假印章 |
| s24a 田邊墳地 | **西式墓碑**（不對） | 土墳、蘆葦、狐狸回頭，最貼 prompt | 稻草堆似的墳、狐狸，可以用 |

- 結論：
  - klein 4B 最聽 prompt，也最快。
  - Z-Image 的水墨質感最好，但細節（尾巴數、墓碑）常常錯。
  - schnell 有兩個系統性問題：一直會蓋假印章、寫假字，而且 `no text`、`no seal` 都壓不住。上片後觀眾會以為那是真古畫的落款，這違反「AI 圖不能假裝是古畫」的精神。
- 共通問題：三個模型都**沒辦法穩定畫出「九條」尾巴**。真的要上片，可以用以下幾種方法處理：
  - 多跑幾個 seed 挑一張；
  - 畫面避開正面數尾巴；
  - 只在不需要精確細節的氣氛和轉場段落使用。

## 5. 「AI 示意圖」標籤示範

`build_gallery.py` 的 `labelled()`：左上角半透明黑底圓角框，白字「AI 示意圖」，字高約為畫面高度的 1/28（1080p 上約 38 px）。放左上角是為了避開右下角的吉祥物和底部字幕。接 pipeline 時，這段可以直接搬進 media 步驟。

## 6. 要 Leon 決定的事

1. **選哪個模型**：我推薦 klein 4B 當主力、Z-Image 當水墨備選。schnell 不建議。
2. 接 pipeline 時要不要同時保留兩個模型（`local_mflux` provider 用設定切換 model）？
3. 「九條尾巴畫不準」能不能接受？如果不行，s05、s09 這類需要精確細節的段落就不放 AI 圖。

Leon 選定後，下一輪再做：
- `media.kind: ai_image` 的 `local_mflux` provider
- 把生成參數寫進 credits.json
- QC 規則「ai_image 沒有標籤＝error」
- deck 規則
- 九尾狐重出成片和前後對照

## 7. 副作用

- `output/ai-trial/`：原圖、標籤版、results.jsonl、gallery、contact_sheet。在 gitignore 裡，不 commit。
- `docs/design/ai-trial/`（commit，合計 3.1 MB）：prompts.json、run_trial.py、build_gallery.py、`img/` 15 張縮圖、contact_sheet.png、gallery.html、chipcat_7722_strip.jpg。
- 權重：
  - `~/.claude/jobs/f9ab0177/tmp/hf`（klein＋schnell，14.2 GB），會隨本 job 刪除。
  - Z-Image 和 mflux venv 在 `~/.claude/jobs/d3bbd556/tmp/`，會隨 d3bbd556 刪除。
  - **要保留本機出圖能力，請先把 klein 權重（4.6 GB）和 venv 搬到持久的位置**，例如 `~/.local/share/mflux/`。schnell 不建議留。
