# 頻道聲音接線＋Fish Audio 真配音重出（feat/real-voice）

## TL;DR
- 頻道聲音接上了：runner 依 `channels/<code>.yaml` 的 `voice.voice_id_env` 讀聲音 ID（先看環境變數，再看 `--env-file`），以 `CF_TTS_VOICE_ID` 傳給 TTS 的 `voice_id`。沒設時退回 `CF_FISH_AUDIO_REFERENCE_ID`，log 會寫「退回預設」。voice 步驟的指紋包含 provider＋voice_id；generator 只在 provider、聲音、念稿文字都相同時才重用舊音檔。🟢
- 三支長片和一支 Short 都已用 Fish Audio 重出：CoWoS 6:51、九尾狐 8:39、動畫產業 6:42、7,722 Short 0:21（晶片貓）。四份 manual-kit 都標「配音：Fish Audio」，沒有「暫用機器聲」。全部停在 gate_final，等 Leon 審。🟢
- 用量：Fish Audio 共 89 次呼叫、9,094 字，沒有遇到 402。念錯修正只動了 CoWoS 的講稿發音表，只重配 8 場。🟢
- 順手修了三處：年份「2016 年」（有空格）原本不會轉成中文念法；Short 放在 16:9 頻道時，QC 會誤判解析度錯誤；manual-kit 的 Studio「變造或合成內容」建議改成「否」（Leon 的決策）。pytest 結果是 1 failed（基準就有的那支）／1091 passed。🟢
- 要 Leon 決定：CoWoS（411 s）和 cel（402 s）短於頻道目標下限（420／480 s），QC 是 warn。另外 API 上傳路徑仍會勾選合成內容（見 §6）。🟡

## 1. 聲音接線改動（commit `feat(voice)…`）

| 檔案 | 改動 |
|---|---|
| `production/voice_choice.py`（新） | `choose_voice(channel, env_file, mock)` → `VoiceChoice(provider, voice_id, source, from_channel)`。查找順序：process env → env file。`describe()` 輸出一行說明，例如 `fish_audio voice_id=…（來源 CF_CHIPCAT_VOICE_ID）`，或「（來源 CF_FISH_AUDIO_REFERENCE_ID（CF_X 未設），退回預設）」。`env_file_defaults()` 把 env file 裡、process env 還沒有的 `CF_*` 值交給子程序，因為 worktree 沒有 `.env`，子程序原本讀不到設定 |
| `production/steps.py` | `_voice_env`：非 mock 時設定 `CF_TTS_PROVIDER=<頻道 provider>`；頻道有設聲音時再設 `CF_TTS_VOICE_ID`。Step 新增 `identity` 欄位，兩條 pipeline 的 voice 步驟都填 `voice_choice(c).describe()` |
| `production/runner.py` | cmd 步驟的指紋改為「檔案指紋＋identity 的 sha256」。執行前把 identity 寫進 runner log 和 `production.log.jsonl` |
| `config.py` | 新增 `tts_voice_id`（`CF_TTS_VOICE_ID`） |
| `voice/factory.py` | 新增 `effective_voice_id(settings)`：回傳覆寫值，沒有覆寫就回傳 provider 的預設值 |
| `voice/generator.py` | 把 `voice_id` 傳給 provider。每合成完一場就寫一次 `audio/voice_identity.json`（provider、voice_id、念稿文字 sha）。舊音檔只有在紀錄相符時才重用（會印「Reusing existing audio」），否則印「Re-synthesizing…」並重做。沒有紀錄的舊音檔一律重做 |

- 測試（新增 8 支）：
  - runner：有設頻道聲音（env、log、event 都正確，API key 不出現在 log／event）；沒設時退回預設並寫明；process env 優先於 env file；換聲音時重跑 voice、同一聲音時跳過。
  - generator：voice_id 有傳到 provider；沒有覆寫時傳 `None`，紀錄寫的是預設 ID；同聲音同文字時重用，換聲音或改發音表時重做；沒有紀錄的舊音檔會重做。🟢
- 實際跑的時候，改發音表後只重配了文字有變的 8 場（log 裡的 `Re-synthesizing` 剛好是 s06 s08 s09 s11 s14 s17 s20 s22），其餘 16 場重用。🟢
- 外洩檢查：把 `output/` 和本 session 的背景工作輸出共 972 個檔案，拿去比對 `.env` 裡 API key 的實際值，命中 0 次。對照組是 chipcat 的聲音 ID，命中 8 次，證明這個掃法掃得到 log。🟢

## 2. 每支片

| 片 | run-dir | 聲音（來源） | 片長（舊 macOS say） | 念稿字數 | Fish 呼叫 | voice wall | QC |
|---|---|---|---|---|---|---|---|
| CoWoS（chipcat） | `output/cowos-chipcat` | `bbfff76f…`（CF_CHIPCAT_VOICE_ID） | 411.3 s（舊 496.6） | 2,763（重配 8 場後累計送出 3,765） | 24＋8 | 293.0＋94.5 s | 0 error／1 warn：短於 420 s |
| 九尾狐（yokai） | `output/yokai-kyubi` | `28df7fe4…`（CF_YOKAI_VOICE_ID） | 519.1 s（舊 503.1） | 2,649 | 29 | 497.2 s | 0／0 |
| 動畫產業（cel） | `output/cel-ep1` | `bbfff76f…`（CF_CEL_VOICE_ID，和 chipcat 同一個江湖聲） | 401.6 s（舊 543.9） | 2,522 | 24 | 281.7 s | 0 error／1 warn：短於 480 s |
| 7,722 Short（chipcat，教育） | `output/chipcat-7722` | 沿用 CoWoS s09 的配音 | 21.1 s | — | 0 | cut 9.9 s | 0／0（修正後，見 §5） |

- 另外的探針呼叫：CoWoS 場景 1 試合成 1 次（73 字），數字念法 A/B 3 次（85 字）。總計 89 次、9,094 字。🟢
- 渲染時間：CoWoS media 402 s／assembly 143 s／mascot 718 s；yokai media 655 s／assembly 202 s；cel media 262 s／assembly 137 s。全部帶 `--max-load 8`，經 render lock 一次只渲一支（log 裡有「render lock held by another run; waiting」和 load 等待紀錄）。🟢
- 複製 run-dir 時排除了 assembly/、audio/、voice／subtitle／assembly artifact、subtitles/、upload/、qc/、review/、logs/。來源 run-dir 唯讀，沒有寫入。
- 閘門：發音表改了 deck.json，所以 gate_deck 重開；重配後時長改了，所以三支片的 gate_media 也重開。我都以 `claude-real-voice` 核可，並附理由。gate_deck 的理由是只改 pronunciation_map。gate_media 的理由是 `compare_media.py` 比對前後兩版，素材種類、來源 ID、credits 都 0 差異；對照組是 cowos 對 cel，比出 20 處差異，證明這個比對有效。這和先前 `claude-draft` 核可的作法相同。**gate_final 沒有動，留給 Leon。** 🟢
- 外部 API：media 步驟的 Pexels 大多走 cache，CoWoS s01 重新下載了一次。Pexels 是免費 API，下載的是同一支素材（ID 相同）。

## 3. 念法檢查與修正（全部改在講稿層，字幕顯示不變）

方法：whisper-base 逐場轉寫，和送進 TTS 的文字並排比對（`small` 模型下載卡在 2.6 MB，所以改用已快取的 base）。base 對中文同音字很不準，所以只當「英文縮寫／數字」的偵測器，同音字的落差不採信。🟡（沒有實際用耳朵聽）

| 片 | 問題（轉寫證據） | 修正（`deck.json` 的 `pronunciation_map`） |
|---|---|---|
| CoWoS | `扣窩斯-L/-S` 被念成「Cowoss 剪L」，連字號被念成「減」。原因是發音表依插入順序套用，`CoWoS` 先被換掉，`CoWoS-L` 那條永遠匹配不到 | 把 `CoWoS-L`／`CoWoS-S` 移到 `CoWoS` 前面 → 轉寫為「KOWA4L／KOWA4S」，「減」消失 |
| CoWoS | `CoW` 被念成「靠」（cow），`WoS` 被念成「Wars」 | 新增 `CoW→C O W`、`WoS→W O S` → 轉寫為「COW」「WOS」 |
| CoWoS | `HBM2` 那條同樣被 `HBM` 蓋掉，送出的是「H B M2」 | 把 `HBM2` 移到 `HBM` 前面 → 送出「H B M 二」 |
| CoWoS | `AP7`、`A4`、`Intel` 念法不確定 | `A P 七`、`A 四`、`英特爾` → Intel 那句轉寫為「英特尔」 |
| 全部 | 年份：講稿寫「2016 年」（數字和「年」之間有空格），`_YEAR_PATTERN` 匹配不到，數字原樣送進 TTS | 程式修正（commit `fix(voice)…`）：允許「年」前面有一個空格，轉成「二零一六年」。補了測試 |
| cel | 逗號分隔的數字（`8,407`、`1,008`）轉寫成「3.8407億」「108億」 | **沒有修**。A/B 探針把同一句分別寫成「逗號版」「無逗號版」「全中文版」，三版時長是 5.07／4.88／4.65 s，詞的時間點幾乎一樣，而全中文版也被轉寫成「108億」。所以問題出在 whisper，不是 Fish 讀錯 |
| yokai | 人名（達己、玉早前、古米虎、張濁）轉寫正常；落差都是同音字 | 不改 |

- 動 CoWoS 的 deck.json 時，除了 pronunciation_map，另有兩個 `keywords` 陣列因為 JSON 重新輸出而換行，值不變（`git diff --no-index` 可以看到）。
- 字幕：四支片都是 whisper 對齊（CoWoS 150 cue、yokai 144、cel 135）。畫面上仍顯示 `CoWoS`，不會顯示「扣窩斯」。🟢

## 4. 四份 preview.html

- `/Users/lileon/project/content-farm/.claude/worktrees/cf-real-voice/output/cowos-chipcat/upload/manual/preview.html`
- `/Users/lileon/project/content-farm/.claude/worktrees/cf-real-voice/output/yokai-kyubi/upload/manual/preview.html`
- `/Users/lileon/project/content-farm/.claude/worktrees/cf-real-voice/output/cel-ep1/upload/manual/preview.html`
- `/Users/lileon/project/content-farm/.claude/worktrees/cf-real-voice/output/chipcat-7722/upload/manual/preview.html`

四份 README 和 preview 裡「暫用機器聲／macOS say」的出現次數都是 0。剩下的「暫用」指的是縮圖（品牌縮圖產生器 R2 還沒做），和配音無關。四份說明欄最後一行都是「本影片由 AI 輔助製作（配音為合成語音；畫面無 AI 生成圖像）。」，維持現行邏輯。四份都標示「成片閘門未核可：預覽版」。Short 的 README：頻道晶片貓、類別教育、相關影片指向 CoWoS 長片。🟢（沒有開瀏覽器，依指示）

## 5. QC 與另外兩項修正

- **QC 的 Short 判定**（commit `fix(qc)…`）：chipcat 是 16:9、420–660 s 的頻道，所以 7,722 Short 一開始被判成「resolution 1080x1920 (expected 1920x1080)」error，還有片長 warn。舊的 offwork 版之所以沒事，是因為 offwork 頻道本身就是 9:16。新增 `qc.qc_channel()`：有 `short_source.json` 的 run 改用 9:16、≤60 s 的格式來檢查，其餘頻道設定不變。補了測試。重跑 QC 後 0／0。🟢
- **Studio「變造或合成內容」**（commit `fix(manual-kit)…`）：README 原本建議選「是」。依 Leon 的決策改成「否」，說明欄的揭露文字照舊保留。🟢

## 6. 要 Leon 看的

1. **片長低於頻道目標**：Fish 念得比 macOS say 快。CoWoS 411 s（目標 ≥420），cel 402 s（目標 ≥480）。選項：放寬 `channels/*.yaml` 的 `target_seconds`、補講稿，或接受 warn。🟡
2. **API 上傳路徑和「不勾」的決策不一致**：`youtube_meta.json` 的 `contains_synthetic_media` 仍然是 true，`google_provider` 會把它送成 `status.containsSyntheticMedia`，等於勾選。這次只改了手動上傳包的建議，並在 README 註明；改 API 旗標屬於政策變更，留給 Leon。🟡
3. cel 和 chipcat 共用同一個聲音 ID（江湖）。這是照任務設定，只是提醒一下：兩個頻道聽起來會是同一個人。

## 7. 測試

`PYTHONPATH=<worktree>/src .venv/bin/python -m pytest -q -p no:cacheprovider tests`（worktree 裡沒有 .env）：

```
FAILED tests/unit/test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results[asyncio]
1 failed, 1091 passed, 1 skipped, 1 warning in 64.70s
```

唯一的失敗是基準就有的那支（`assert 2 == 1`）。通過數從 1081 增加到 1091，新增 10 支：runner 4、generator 4、年份 1、Short QC 1。🟢

## 8. 清理與留下的東西

- `output/`（gitignored，沒有 commit）：四個交付 run-dir；`output/voice-probe-cowos/` 是場景 1 試合成的證據，保留。
- job tmp（`~/.claude/jobs/cea2c06c/tmp/`，job 刪除時一起清掉）：survey／probe_voice／transcribe／contexts／set_pmap／compare_media／ab_numbers／usage／leak_scan 等腳本，轉寫結果 `*_heard*.jsonl`，A/B 音檔 `ab/`，以及 deck 備份 `cowos-deck.before.json`。
- `~/.cache/huggingface/hub/models--Systran--faster-whisper-small`：下載中斷，只剩 2.6 MB 的殘檔。`rm` 在 deny 清單裡，請 orchestrator 視需要刪除。
- 沒有 push，沒有開瀏覽器，沒有上傳，沒有動 `mascot/`、main、`feat/explainer-*`。沒有用 stash。
