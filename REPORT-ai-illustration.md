# Leon 2026-10-16 三項決策套用＋AI 插圖接進 pipeline（feat/ai-illustration）

## TL;DR（第二輪：決策 cc801e14fbc2，AI 插圖 both）
- 已 merge `feat/real-voice`（`ec6120c`）。衝突 4 處：
  - qc.py 採用 real-voice 的 `qc_channel`。它跟我 `0b40904` 修的是同一件事，我的版本拿掉，但測試保留。
  - manual_readme 保留本分支的拆欄版本。real-voice 沒拆欄，所以 API 上傳仍會勾選；本分支已經把這個不一致消除，見 §A。🟢
- **AI 插圖已接進 pipeline**：
  - `channels/<code>.yaml` 新增 `ai_illustration` 設定：模型、畫風前綴、seed、尺寸。chipcat／cel 用 FLUX.2 klein 4B，yokai 用 Z-Image-Turbo 水墨。
  - 新增 `illustrate` 步驟，放在 media 之前，透過 `local_mflux` provider 生圖。provider 走介面，之後可以換 api 或 browser。
  - 一次生一張。memory pressure 在 warn 以上，或偵測到 `mlx_video`／其他 `mflux-generate` 在跑時，就先等。
  - 每張圖附一個 sidecar，記錄模型、prompt、seed、步數、授權，再寫進 credits.json。
  - 畫面左上角固定燒入「AI 示意圖」。
  - QC 會擋三種情況：沒有標籤、沒有參數、prompt 要求擬真或指定畫家畫風。
  - 三條規則都寫進了 deck skill。🟢
- **九尾狐重出**（真配音版，**沒有重配音**）：s06、s09、s13、s24a 四張改成 AI 水墨。
  - 成片：`output/yokai-kyubi/assembly/draft.mp4`，519.1 s，QC 0 error／0 warn，`ai_image` 檢查通過。
  - 預覽頁：`output/yokai-kyubi/upload/manual/preview.html`
  - 前後對照：`docs/design/ai-illustration/kyubi_before_after.jpg` 🟢
- 資源：Z-Image 每張 54–61 s，峰值 6.4 GB。第一張開跑前因為 memory pressure 是 warn，等了 60 s。之後 media 和 assembly 因為 load 超過 8（AI 影片 worker 在跑 Wan）等了約 77 分鐘。生圖和渲染沒有重疊。🟢
- pytest：1 failed / 1105 passed / 1 skipped。唯一的失敗是基準就有的那支。🟢

## TL;DR（第一輪）
- 決策 1（`916c2864e31f`）：Studio「變造或合成內容」改成**不勾**，說明欄的揭露句照舊依實際內容產生。頻道設定拆成 `ai_disclosure`（說明欄文字）和 `altered_content_label`（Studio 勾選，預設 false），補了測試。commit `5aefd51`。🟢
- 決策 2（`88093246da75`）：7,722 Shorts 改用 chipcat 重出，片頭片尾換成晶片貓品牌，類別是教育。產物在 `output/chipcat-7722/`（QC 0 error），上傳包在 `upload/manual/`。順手修了一個 QC bug：長片頻道上的 Short 原本被判解析度錯。offwork 開台片另列 3 個候選。commit `0b40904`。🟢
- 決策 3（`5ae6d3d8bd8e`）：orchestrator 中途改了順序（mail `e4ddeb2bf0950e11`），所以**先不接 pipeline、不動九尾狐成片**，改做 3 個本機模型的試圖和 gallery。3 個模型的原始 LICENSE 都是 Apache-2.0，可以商用。細節見 `REPORT-ai-trial.md`。
- pytest：1 failed / 1083 passed / 1 skipped。唯一的失敗是基準就有的 `test_multi_provider…returns_first_provider_results`（基準 1081 passed，新增 2 支）。🟢

## 1. 決策 1：Studio 不勾，說明欄文字揭露

| 檔案 | 改了什麼 |
|---|---|
| `production/channels.py` | `YouTube.ai_disclosure` 的語意改成只管說明欄揭露句。新增 `altered_content_label: bool = False`，對應 Studio 勾選＝API `status.containsSyntheticMedia` |
| `production/publish.py` | `contains_synthetic_media = altered_content_label and 內容有合成`。原本是 `ai_disclosure and …`。揭露句的產生邏輯沒動。新增常數 `DISCLOSURE_MARK` |
| `production/manual_readme.py` | 建議改成：說明欄有揭露句時寫「選『否』，不勾（Leon 2026-10-16 決策 916c2864e31f）……已寫在 description.txt」；勾選旗標為 true 時才建議「是」；兩者都沒有時寫「否（本片沒有合成內容）」。檔尾那行改成同時列出兩者 |
| `templates/preview.html.j2` | 上傳設定拆成兩列：「變造或合成內容：勾選／不勾」和「說明欄揭露：有／無」 |

- 測試：`test_studio_label_and_description_disclosure_are_separate_switches`（新增）證明兩個開關各自獨立，四種組合都有測到。三支既有的斷言從 `contains_synthetic_media is True` 改成 False，各附上決策 id 註解。`test_synthetic_advice_follows_the_flag` 改成斷言「不勾」以及指向 description.txt。🟢
- API 上傳路徑（`run_stage --stage youtube`）會讀同一個 `contains_synthetic_media`，所以現在會送出 `containsSyntheticMedia: false`，與 Studio 手動不勾一致。🟢（看程式碼；沒有實際上傳）
- 實測 `output/chipcat-7722/upload/manual/README.md` 第 25 行：「變造或合成內容：選 **「否」**，不勾（Leon 2026-10-16 決策 916c2864e31f）……」。第 40 行：「Studio 勾選 `contains_synthetic_media=False`；說明欄文字揭露有」。🟢
- `output/kit-check/` 底下那四份舊上傳包**沒有重出**。它們在別的 worktree，下次跑 `manual-kit` 就會套用新的文字。

## 2. 決策 2：7,722 Shorts 改放晶片貓

```
python scripts/produce.py short-from-long --from <cf-ch-chipcat-ep1>/output/cowos-chipcat --slide s09 --channel chipcat \
  --run-dir output/chipcat-7722 --title "7,722 平方毫米有多大？台積電的超級載板" \
  --number 7,722 --unit "mm²" --caption "台積電規劃的超級載板可用面積" --aside "≈ 8.8 × 8.8 公分的正方形"
```

- 來源長片只讀不寫，產物都在本 worktree 的 `output/chipcat-7722/`：
  - `assembly/final.mp4`：1080×1920、24.7 s
  - `review/final.html`
  - `upload/manual/{README.md, preview.html, title.txt, description.txt, tags.txt, 縮圖, subtitles.*}`
- **品牌**：intro.html／outro.html 裡只有「晶片貓／chipcat」，沒有 offwork。截圖 `docs/design/ai-trial/chipcat_7722_strip.jpg`（片頭、數字頁×2、片尾）。🟢
- **類別**：README 寫「類別：教育（Education）」（chipcat 是 explainer pipeline → 27）。播放清單是「晶片貓｜台灣科技產業拆解」。相關影片指向同頻道的 CoWoS 長片。🟢
- **QC bug 修正**：第一次跑出現 `resolution: 1080x1920 (expected 1920x1080)` error 和 duration warn（channel target 420–660 s）。原因是 `run_qc` 用頻道的長片格式來判 Short。現在 run-dir 有 `short_source.json` 時，任何頻道都改用 `SHORTS_FORMAT`（9:16、15–60 s）。重跑結果 `qc: 0 error(s), 0 warning(s)`。新測試 `test_short_cut_on_a_long_channel_is_judged_as_a_short` 先用沒有 spec 的情況當對照組（應該是 error），再斷言有 spec 時是 ok。🟢
- 停在 gate_final 等 Leon：`python scripts/produce.py approve --run-dir output/chipcat-7722 --gate final`。配音仍是 macOS say，上傳包有「暫用機器聲」和「預覽版」兩個警告。

### 選題池
- `channels/backlog/chipcat.yaml` `cowos-number`：notes 改成「Leon 2026-10-16（88093246da75）定案放晶片貓……output/chipcat-7722」。
- `channels/backlog/offwork.yaml` `cowos-7722`：改成 `dropped`，notes 指向 chipcat。

### offwork 開台片候選
三則都要等 shorts_skit 渲染器（R4）才能出片；只有「從長片切」那條路現在就能出片，但切出來的屬於晶片貓。

| # | id | 題目 | 理由 | 卡在 |
|---|---|---|---|---|
| 1（推薦）| `box-packaging` | 貓為什麼最懂封裝 | 只要下班貓一隻角色；接 CoWoS s04 的紙箱梗，可以導流到晶片貓長片 | R4 |
| 2 | `friday-deploy` | 週五下午五點的部署 | 單角色，上班族一看就懂，原創梗 | R4 |
| 3 | `pm-yidiandian` | 需求只改一點點 | 品牌 Shorts 樣張那則，辨識度最高 | R4＋PM 狗 rig（R11） |

offwork 池裡另有一則 `hbm-stack`（一個數字：HBM 疊幾層）。它也是從晶片貓長片切出來的；照這次的決策，應該也歸晶片貓。我**沒有改**，請 Leon 一併確認。

## 3. 決策 3：AI 插圖（本機）

照 orchestrator 的改序信（`e4ddeb2bf0950e11`），只做試圖和 gallery，**沒有**接 pipeline（`local_mflux` provider、credits、QC 標籤規則），也**沒有**動九尾狐成片。結果、授權、耗時與資源見 `REPORT-ai-trial.md`。gallery：`docs/design/ai-trial/gallery.html`（commit），全尺寸版在 `output/ai-trial/gallery.html`。

原任務裡「畫面規則寫進 deck 規則與 QC」「九尾狐新成片」「前後對照截圖」這三項，等 Leon 看完試圖、選定模型後再做。

## 4. 測試

`PYTHONPATH=<worktree>/src .venv/bin/python -m pytest -q -p no:cacheprovider tests`（worktree 裡沒有 .env）：

```
FAILED tests/unit/test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results[asyncio]
1 failed, 1083 passed, 1 skipped, 1 warning in 68.93s
```

## 5. 清理與副作用

- `output/chipcat-7722/`、`output/ai-trial/` 都在 gitignore 裡，是交付物，保留。
- 模型權重：
  - Z-Image 沿用前一個 job 的快取（`~/.claude/jobs/d3bbd556/tmp/hf`，連同 mflux venv `flux-venv/`）。**那個目錄會隨 d3bbd556 刪除而消失**，要保留本機出圖能力就要先搬走。
  - klein／schnell 下載到本 job 的 `~/.claude/jobs/f9ab0177/tmp/hf`，會隨本 job 刪除。
- 沒有動 repo 的 `.venv`，沒有 push，沒有開瀏覽器。

---

# 第二輪：AI 插圖接進 pipeline（決策 cc801e14fbc2）

## A. merge feat/real-voice（`ec6120c` → merge commit `0989216`）

| 檔案 | 衝突 | 處理 |
|---|---|---|
| `production/qc.py` | 兩邊都修了「長片頻道上的 Short 被判解析度錯」：real-voice 用 `qc_channel()`，我用 `SHORTS_FORMAT` | 採用 real-voice 的 `qc_channel`，我的常數拿掉。我那支「長片頻道上的 Short」測試在 run_qc 層級，而且有對照組，所以保留。兩支測試都過 |
| `production/manual_readme.py`＋測試 | 兩邊都把 Studio 建議改成「否」。real-voice 沒有拆欄：`contains_synthetic_media` 仍為 true，README 另外警告「API 上傳會被勾選」（它報告 §6-2 列為待決） | **保留本分支**。`altered_content_label` 預設 false，旗標本身就是 false，API 上傳路徑也不會勾選，real-voice §6-2 的不一致就此消除 |
| `CLAIMS.jsonl` | 兩邊各是自己 job 的版本 | 保留本分支的，收工時重寫 |
| `test_production_runner.py` | 自動合併 | 確認合併結果等於 real-voice 版，只差 synthetic 那一行（取本分支） |

real-voice 帶進來的其他改動（聲音接線、generator 重用、年份念法等）都自動合併，沒有衝突。

## B. 設計（commit `b7bcefe`、`9facd51`）

| 檔案 | 內容 |
|---|---|
| `channels.py` `AiIllustration` | 欄位：`provider`（目前只有 `local_mflux`）、`model`（必須在 registry 裡）、`style_prefix`（擬真或畫家名的字眼會被擋）、`seed`、`width`／`height`（16 的倍數） |
| `channels/{chipcat,cel,yokai}.yaml` | chipcat／cel：`flux2-klein-4b`，用各自品牌的插畫前綴（cel 註明不能畫出近似官方角色）。yokai：`z-image-turbo`，前綴是水墨、宣紙、`no text, no seal`。offwork 不開放 ai_image，所以 illustrate 步驟不會出現 |
| `explainer/illustrate.py`（新） | `ModelSpec` registry 只列兩個模型，授權照第一輪讀過的原文。另有 `IllustrationProvider` 協定，以及 `LocalMflux`：每張圖開一個 mflux 程序，生完就卸載；在 `HF_HUB_OFFLINE` 下跑；路徑讀 `CF_MFLUX_BIN_DIR`／`CF_MFLUX_HF_HOME`，不寫死在程式裡。生圖前呼叫 `wait_for_memory`：pressure ≥ warn 時等，`pgrep -f mlx_video|mflux-generate` 有命中時也等，最多等 30 分鐘才報錯。`illustrate()` 先檢查所有 prompt 再載入模型；只生還缺的圖，手放的圖不覆蓋 |
| `scripts/illustrate.py`（新）＋ `steps.py` | 新增 `illustrate` 步驟，放在 media 之前。它佔 render lock（heavy），identity 是頻道的 ai_illustration 設定，所以換模型或換前綴會觸發重生。沒有缺圖時不需要 mflux 的 env |
| `media.py`／`cards.py`／`frame.html.j2`／`media.css` | ai_image 的 overlay 在左上角加上「AI 示意圖」徽章（位置在頂欄下方，避開右側吉祥物欄和下方字幕）。credit 從 sidecar 抄入 provider、model、repo、origin_repo、license_url、prompt、seed、steps、size，並加上 `ai_generated: true`、`ai_label` |
| `media_run.credits_text` | 說明欄的素材授權區多一段「AI 示意圖 / AI illustrations（非史料，僅示意）」，每個模型列一行，附原始 repo 和授權連結 |
| `qc.py` | `ai_image_findings`：沒有徽章是 error，缺 model／prompt／seed 是 error，prompt 含擬真或畫風字眼是 error。`policy_findings` 在 deck 階段就檢查同一組字眼。credits 有 error 時不再同時給一條 blanket ok |
| `.claude/skills/deck/SKILL.md` | 新增「AI image rules」三條（標籤、只用在沒有公有領域畫作的段落、非擬真、不模仿畫家），並更新 illustrate 的用法 |

「只用在沒有公有領域畫作的段落」這條**沒辦法自動判定**，靠的是 deck skill 規則和 gate_media 人工審核。這是設計上的限制，不是遺漏。🟡

測試（`tests/unit/test_explainer_illustrate.py`，12 支）：
- 生圖寫出 sidecar、已有的圖會保留、`--replace` 會重生；
- 擬真或畫風 prompt 在載入模型前就被拒，另有對照組；
- env 缺漏時報錯、entry point 不存在時報錯、argv 正確；
- memory pressure 的等待和逾時；另一個模型在跑時的等待（`pgrep` 對照組：不存在的程序名回 None；實機上 `pgrep -fl mlx_video` 命中 PID 77401）；
- 各頻道的模型對應、壞設定被拒；
- 步驟順序，以及 offwork 沒有 illustrate；
- 徽章只出現在 AI 畫面；
- QC 四種情況；
- policy 擋擬真 prompt；
- 說明欄列出模型名；
- media 的 credit 從 sidecar 抄入，沒有 sidecar 時 QC 會擋。

## C. 九尾狐重出

- 來源是 `cf-real-voice/output/yokai-kyubi`，只讀，`cp -R` 複製到 `output/yokai-kyubi`。音檔和 `audio/voice_identity.json` 一起帶過來。
- **沒有重配音**。改 deck.json 會讓 voice 和 gate_deck 的指紋失效，runner 會重跑 voice。所以沒有走 runner，改用 job tmp 的 `after_media.py`，直接呼叫 runner 自己的 Step command 和 `_internal`，依序跑 policy → media → assembly →（yokai 沒有 mascot）→ qc → package，同樣佔 render lock、同樣等 load。`logs/voice.log` 沒有新的合成紀錄。
- 段落選擇：key line 要能保留原本投影片的資訊。

  | 投影片 | 版型 | 換成 AI 圖後保留的文字 |
  |---|---|---|
  | s06 青丘國 | quote | 引文「其狐四足九尾。」 |
  | s09 大禹與九尾白狐 | quote | 引文 |
  | s13 唐代家家拜狐神 | quote | 引文「無狐魅，不成村。」 |
  | s24a 為什麼偏偏是狐狸 | bullets，3 項 | 3 項全部 |

  第一輪試做的 s12（玄中記升級表）**這次不換**：它是 timeline 版型，換了只剩「50 歲 → 1000 歲」，那張表的內容就沒了。四段都沒有公有領域畫作可用：s06、s13、s24a 原本是純文字動畫，s09 也沒有古畫。
- s13 第一版左邊畫出**電線桿和電線**，即使 prompt 寫了「no wires or poles」（負面詞反而像在提示它畫）。我把那張移到 job tmp 的 `s13_rejected_poles.png`，prompt 改成只描述年代材質（茅草屋頂、柳樹、紙燈籠），重生一張，沒有電線桿了。prompt 也拿掉了神像（yokai 頻道規定不生成神像）。
- 結果：
  - 成片：`output/yokai-kyubi/assembly/draft.mp4`，1920×1080，519.1 s，和 real-voice 版同長
  - QC：9 項全部 ok，其中 `ai_image: 4 AI image(s) labelled 「AI 示意圖」 with model/prompt/seed recorded`
  - credits：16 筆，沒有待補
  - 預覽頁：`/Users/lileon/project/content-farm/.claude/worktrees/cf-ai-illustration/output/yokai-kyubi/upload/manual/preview.html`
  - 說明欄最後一行自動變成「本影片由 AI 輔助製作（配音為合成語音；部分插圖為 AI 生成）。」，上一段是 AI 示意圖的模型列。README 寫 Studio「不勾」，配音是 Fish Audio，QC 0／0。🟢
- 前後對照（commit）：`docs/design/ai-illustration/kyubi_before_after.jpg`，左邊是 real-voice 版，右邊是新版，取每段中點的畫格（100.6／152.1／221.2／453.6 s）。

## D. 資源

| 項目 | 數字 |
|---|---|
| Z-Image 每張 | s06 55.9 s／s09 56.3 s／s13（重生）60.9 s／s24a 54.0 s；第一次的 s13 54.9 s（已淘汰） |
| 峰值（mflux 自報） | 6.37 GB／張（1280×720，比第一輪 1024×576 的 4.4 GB 高） |
| 等待 | 第一張生圖前 pressure 是 warn，等了 60 s；之後幾張都是 0 s |
| swap | 5.6 GB → 12.2 GB（第一張載入）→ 最高 13.5 GB。這是整台機器的數字，AI 影片 worker 同時在跑 🟡 |
| 渲染 | media 5,286 s（其中約 77 分鐘是在等 load 降到 8 以下，那時 load 在 8.5–112 之間），assembly 596 s（含等待）。生圖時沒有渲染，渲染時也沒有生圖 |

orchestrator 中途通知 swap 已到 92%（`mlx_video` 在跑）。那時我的四張圖已經生完，正在等 render lock；我把「`pgrep -f mlx_video` 有命中就等」做進 provider（`9facd51`），之後每次生圖都會先檢查。

## E. 看圖要注意的（🟡 我的判讀，請 Leon 在 gate_media／gate_final 看）

- s06 這次真的畫出多條尾巴（數不到九條）；s24a 是土墳，沒有再出現西式墓碑。
- **s09**：Ken Burns 是置中推近，加上下方的 lower-third 字卡，白狐在中點畫格裡大半被字卡擋住，只看得到旅人。可以在 prompt 加構圖指示（「主體放在畫面上半部偏右」）再重生，或者接受。這次沒有改。
- 淺色宣紙底上，最下面那行來源字的對比偏低（`footage-shade` 是為深色影片設計的）。要改 media.css，留待後續。
- 這支片還停在 gate_final，需要 Leon 看完成片再核可：`python scripts/produce.py approve --run-dir output/yokai-kyubi --gate final`。gate_media 我**沒有**代為核可：這輪新增的就是 AI 圖，讓人看過比較合適。runner 狀態檔裡的 gate 紀錄還是 real-voice 那一輪的；如果改用 runner 繼續，它會因為 deck.json 指紋改了而要求重新審 deck 和 media，**而且會先跑 voice**：同一聲音、同一段念稿會走 generator 的重用路徑，不會重新合成，但我這次沒有實測這一步。

## F. 測試（第二輪）

```
FAILED tests/unit/test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results[asyncio]
1 failed, 1105 passed, 1 skipped, 1 warning in 63.51s
```

1105 = real-voice 的 1091 ＋ 第一輪新增的 2 ＋ 這輪新增的 12。唯一的失敗是基準就有的那支。🟢

## G. 清理（第二輪）

- `output/yokai-kyubi/`（580 MB 起跳，gitignored）是交付物，保留。
- job tmp：`after_media.py`、`before_after.py`、`kyubi_ai_grid.jpg`、`s13_rejected_poles.{png,json}`，job 刪除時一起清掉。
- **本機出圖能力目前寄放在別的 job 的 tmp**：mflux venv 和 Z-Image 權重在 `~/.claude/jobs/d3bbd556/tmp/`，klein 權重在本 job 的 `~/.claude/jobs/f9ab0177/tmp/hf`。正式使用前要搬到持久位置，例如 `~/.local/share/mflux/{venv,hf}`，再把 `CF_MFLUX_BIN_DIR`／`CF_MFLUX_HF_HOME` 寫進 `.env`。schnell 權重（9.6 GB）不需要留。
