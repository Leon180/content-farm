# visual-v4：評審精簡＋全頻道 AI 圖為主的視覺（分支 `worktree-cf-visual-v4`）

## TL;DR
- 🟢 評審只剩兩種：**腳本評審**（觀眾＋編劇，評一次、照意見自動改稿一次、不重評不擋）與**正確性查核**（信心度 ≥ 0.5 才算錯，走 `auto_fix_then_pass`）；選題評分留作排序、不當閘門。title_thumb／media／final／shorts_title／shorts_final 全部 `enabled: false`（`review_panels.yaml` 逐關可開回）；授權改程式規則。`ent` 頻道 `enabled: false`。
- 🟢 追加（orchestrator 要求）：自動修失敗不再讓 run 停下——退而求其次直接刪被點名的錯句，刪不了就記錄後放行。
- 🟢 視覺：deck lint 新增四條規則（每段 ≥ 1 AI 圖、純文字頁 ≤ 30%、連兩頁不同版型、長片 2–3 個 Wan 鏡頭）；AI 圖新增 `media.frame`（`lower`／`panel_left`／`panel_right`）；Wan 上限 2→3；cel／technews 加本機合成配樂（`studio`／`pulse`，`audio.enabled` 開關）；Shorts（HN 快報）每支 ≥ 3 張 AI 圖＋視差。
- 🟢 示範 cel run2 → v4：沿用文章／腳本／配音，AI 圖 5→16 張，文字頁 14→6 張，成片 484.0 s；Wan 只烤完 1 段（s01），**s14 被系統低記憶體中止，待烤**。
- 🟢 pytest：`1915 passed, 1 skipped`（排除 test_multi_provider，既有失敗）。
- 產物：`output/cel-run2-v4/assembly/release.mp4`（gitignore）、`artifacts/cel-run2-v4/cel-run2-v4-part{1,2}.mp4`（12.0／12.1 MB，未 commit）、`artifacts/cel-run2-v4/compare.jpg`（已 commit）。

## 1. 評審精簡
| 項目 | 做法 | 檔案 |
|---|---|---|
| 只留兩種評審 | `Stage.enabled`；停用關直接放行（`panel_gate`／`panel_step` 都擋），seat 規則對停用關不驗，要開回改 `true` 即重新受規則約束 | `review/config.py`、`review/gate.py`、`production/panel_flow.py`、`channels/shared/review_panels.yaml` |
| 腳本評審一次＋改稿一次 | `policy.script_revise_once`：評完若有修改清單，發一次自動修（沿用 `_auto_fix` 機制），改稿後不重評、直接放行；座位＝觀眾×5（含 1 holdout）＋編劇（故事）＋編劇（密度），拿掉導演與事實席（`REQUIRED_ROLES` 同步） | `review/gate.py` |
| 正確性 ≥ 0.5 才算錯 | 查核員與仲裁員每條填 `confidence`（0–1，schema 可省略、省略＝確定）；< 0.5 的 wrong／unsourced 於 `client.py` 收件時降成 `low_confidence`（原狀態留在 `original_status`），下游（verdict、仲裁、reuse）一律視為非錯誤 | `review/confidence.py`、`schemas.py`、`arbitration.py`、`prompts.py`、`client.py` |
| 授權＝程式規則 | 素材 kind 白名單（yaml `review.license_rules.allowed_kinds`）＋ pending 為空＋授權欄位＋AI 圖標示（「AI 示意圖」）與 model／prompt／seed、禁擬真與畫家；media 關停用後跑這個，不過就停（blocked） | `review/license_rules.py` |
| 自動修不停 run | 自動修的改稿被守門拒收／agent 失敗／檔案沒變 → 還原 → 直接刪旗標句（文章 `pN.M`、講稿 sentence id，不清空整張投影片）→ 刪不了就記錄放行；寫進 `review/auto_fix.jsonl`（`fallback_deleted`／`fallback_nothing_to_delete`／`fallback_recorded`）。只有雲端費用上限仍會停 | `production/auto_fix_fallback.py`、`panel_flow.run_producer`、`runner.py` |
| ent 停用 | `channels/ent.yaml` `enabled: false`（同 offwork 先例；程式與素材保留）。🟡 Leon 說「設定移到 backlog」——我沒搬檔（搬了 `load_channel("ent")` 與既有 run-dir 會壞），若要實體移動請告知 | `channels/ent.yaml` |

測試：`test_review_v4.py`、`test_auto_fix_fallback.py`（新）；舊的整套評審機制測試改指向 `tests/fixtures/review_panels_v3.yaml`（v4 前的完整設定，機制還在、可開回，測試照樣驅動它）。`test_review_config.py` 以「所有關都開」驗硬規則，另加 v4 現況斷言。

## 2. 視覺規則
- **Deck lint**（`explainer/lint.py`，`--strict` 失敗）：`section-no-ai-image`、`text-only-share`（> 30%）、`form-repeat`（連兩頁同版型：文字頁看 layout、AI 圖看 `frame`、其他看 media kind）、`wan-shots`（≥ 10 頁的長片需 2–3 個）。cel run2 舊 deck 對照：**7 條違規**（3 段無 AI 圖、14/23 純文字、2 處同版型、0 個 Wan）→ v4 deck **0 條**。
- **`media.frame`**：AI 圖永遠滿版＋動態，文字以 `lower`（下三分之一）或 `panel_left`／`panel_right`（半透明卡，標題＋投影片本文 1–4 行；big_number 放大數字）疊上去。「圖為主、文字為輔」。
- **動態**：所有 AI 圖預設 2.5D 視差；`motion: wan` 上限 3（QC、bake、lint 同步）；沒烤的退回視差。
- **畫風（各頻道原本的 `ai_illustration.style_prefix`）**：cel 動畫產業插畫、chipcat 科技插畫、technews 資訊插畫、yokai 水墨；仍禁擬真／畫家／真人肖像（lint＋QC＋授權規則三重）。deck skill 已寫入 v4 規則。
- **配樂**：`audio_mix/synth_bgm.py` 新增 `studio`（C 大調五聲木琴，cel）、`pulse`（A 小調五聲節拍點，technews）；yokai 沿用 `wafu`；chipcat 已有 ACE-Step 錄好的 bgm（優先於 preset）。三者皆確定性、可無縫循環（測過），`audio.enabled` 開關。
- **Shorts（HN 快報）**：`Beat.image_prompt`；`news/visuals.py` 逐張生圖（本機模型、一次一張）→ 直式視差片 → 拆成 JPEG 影格，頁面在 `__anim.seek` 內乒乓播放（Chromium 實測 0‑1‑2‑1‑0）；`render` 少於 3 張 prompt 直接停並說明；credits 逐張記 model／prompt／seed／標示／動態。🟡 **沒有實際重出任何 Short**（只有單元測試與 Chromium 影格切換測試）；「一個數字」（`short-from-long`）與已停用頻道不在此範圍。

## 3. 示範：cel run2 → `output/cel-run2-v4`
做法：複製 `cf-cel-run2/output/cel-run2`，`deck.json` 只改 `media`（frame／prompt／motion）；narration、id、來源、mascot 不動；`--no-panels` 跑 deck→slides→illustrate→media→assembly→mascot→mix，閘門以 `--override` 手動核可（理由寫在 production log：腳本沿用、授權程式規則 0 問題）。
- 配置：23 張＝AI 圖 16（5 張沿用舊圖＋11 張新圖）、title_card 1、文字頁 6（26%）；frame 輪替 lower／panel_left／panel_right；Wan 鏡頭 s01、s14。
- 前後對照：`artifacts/cel-run2-v4/compare.jpg`（s02、s05、s10、s11、s15、s20，左舊右新）。
- 成片：`release.mp4` 484.0 s，與舊片等長；540p 兩段 12.0／12.1 MB（2‑pass 340k＋aac 48k 單聲道）。
- 🟡 **配音沿用的但書**：cel run2 的 `deck.json` 與其音檔／字幕其實就已不完全同字（deck 為事實修正後的版本，音檔較舊；舊 run 既有狀況，約 8 場有詞句差異）。v4 沿用音檔與字幕，沒有重配，所以字幕是音檔實際唸的字、畫面的面板文字是 deck 的字。要完全一致需重配（本機 VoxCPM2 約 21 分）。
- 🟡 QC：1 error（dead_zone 0–32 s）、2 warn（beat_gap、still_frames）——與舊片同數，未處理。
- 🟡 **已知小瑕疵**：panel 內 big_number（s11「200–250 日圓」）換行；CSS 已改小（72px），**成片未重渲染**。
- 🟡 風格：cel 目前用 z-image-turbo（cel-run2 因 klein 權重不在離線快取而改，已 cherry-pick `31ee705`）。

### 數字（🟢 取自本次執行紀錄）
| 項目 | 數值 |
|---|---|
| 生圖 | 11 張新圖 594 s（約 54 s／張，z-image-turbo，1280×720），逐張載入、峰值約 6–7 GB（舊紀錄 6.4 GB） |
| 視差 | media 內建；media 2 次共 273 s＋151 s |
| Wan I2V | s01 840 s 完成；**s14 開跑後被 Claude Code 以「系統低記憶體」中止**（swap 約 88–93%，同時有別的重工作），依指示**未重啟**。**待烤清單：`cel-run2-v4/s14`**（`python scripts/ai_motion.py bake --run-dir output/cel-run2-v4`，約 15 分、峰值 26 GB，須單獨跑；烤完重跑 media→assembly→mascot→mix） |
| 其餘本機步驟 | assembly 118 s、mascot 193 s、mix 20 s |
| 排隊（lanes／swap／load 閘門） | media／assembly／mascot 前各等 swap ≥ 90% 或 load 偏高數個輪詢週期（log 未計秒數）🟡；機器上同時有科技新知 worker |
| 費用 | 示範 run **$0 雲端**（沿用文章／腳本／配音、不跑評審團）；本機模型免費。開發階段僅單元測試（全為假 client），無 `claude -p` 呼叫 |
| 牆鐘 | 執行（機器）約 37 分（生圖 10＋media 7＋Wan 14＋後段 5.5）；排隊／等記憶體另計、未精確量到；總牆鐘含開發與等待遠大於此 |

## 4. 清理與限制
- 本 worktree `output/`、`artifacts/` 皆未 commit（mp4 約 24 MB 只放本機）。暫存在 `~/.claude/jobs/02df0357/tmp`（隨 job 清）。
- 未 push、未付費、未開瀏覽器（Chromium 為本機 playwright，僅渲染）、未上傳；科技新知 worker 的 worktree／output 未動。
- 🟡 未做：Shorts 實際重出；chipcat／technews 長片未重出；`shorts_script` 評審的「改稿一次」邏輯與長片共用 `script_revise_once`，但無 Short 端到端測試。
- 本分支由 `worktree-cf-ent` 與 `worktree-cf-kyubi-tweak` 合併而來（唯一衝突：兩邊的 `CLAIMS.jsonl`，取聯集）；另 cherry-pick `31ee705`。
