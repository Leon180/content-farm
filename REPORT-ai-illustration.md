# Leon 2026-10-16 三項決策套用＋AI 插圖本機試做（feat/ai-illustration）

## TL;DR
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
