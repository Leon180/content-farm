# REPORT — 九尾狐成片微調（拿掉青蛙＋加配樂）

## TL;DR
🟢 青蛙已拿掉、配樂已加、成片已渲染（`output/yokai-kyubi-v3/assembly/release.mp4`，682 s）。人聲響度 -23.44 → -23.43 LUFS（不變）。
🔴 final 評審只跑完第 1 輪就停：未過（visual／content 欄），退回點是 **deck（內容改寫）**，超出「只微調、不重寫」範圍，我沒做；第 2、3 輪（會放行）未跑。留給 Leon／orchestrator 決定是否直接放行。
預覽：`artifacts/kyubi-tweak/kyubi-tweak-part1.mp4`、`part2.mp4`（540p 2-pass，12.5／12.4 MB，未 commit）。停在 gate_final 前，沒 push、沒上傳。

## 改動（分支 `worktree-cf-kyubi-tweak`，自 fe97c23）
1. **拿掉青蛙**：沿用 fe97c23 的 `rig_ready: false`。重跑 assembly（94 s）；mascot 步驟不適用，`draft.mp4` 本來就無青蛙，投影片沒有為青蛙預留區塊，版面不需補。縮圖：`thumbnail.json` 改用既有 A 款（公有領域〈古今圖書集成〉九尾狐，keyart 版型，滿版大圖），縮圖不含青蛙。青蛙素材／profile 未刪。
2. **配樂（後期步驟，可開關）**：repo 原已有 `mix` 步驟（`audio.enabled` 開關，`scripts/audio_mix.py`，人聲壓低 sidechain ducking、合成 SFX／轉場）。新增：
   - `audio.synth_bgm: wafu`（`channels.py`）＋ `audio_mix/synth_bgm.py`：純 numpy 本機合成，無下載、無模型、無付費。做法：D 都節旋法（D Eb G A Bb）低音 drone＋柔和 pad＋稀疏箏式撥弦＋少量風聲＋圓周迴響；各持續成分在 96 s 內整數週期、迴響為圓周卷積，所以 `-stream_loop` 無接縫。固定 seed，可重現。
   - 有真實 `bgm` 檔時不啟用合成（真檔優先）；credits 記為「自製、無第三方素材」。
   - `channels/yokai.yaml` 加 `audio:`（enabled、synth_bgm、voice_lufs／master_lufs -23.4、bgm_under_voice_db 16）。其他頻道設 `audio.enabled: true` ＋ `synth_bgm: wafu` 即可用。
   - 轉場音（stinger）與 SFX 用既有 sfx.py 合成，本片 14 個 cue。
   - 測試：`tests/unit/test_synth_bgm.py`（5 個：確定性、無接縫、credits、真檔優先、yokai 設定），與 test_audio_mix 共 10 passed。commit：`feat(audio): locally synthesized wafu BGM preset…`。全套 pytest 未跑（僅跑相關測試）。
3. **人聲響度維持原值**：draft 實測 -23.44 LUFS；yokai 的 voice_lufs／master_lufs 設 -23.4，避免預設母帶拉到 -14（會 +9 dB）。成片 release.mp4 實測 -23.43 LUFS。BGM stem -37.0 LUFS（比人聲低 ~13.6 dB，含壓低段）。🟡 副作用：pre-master 限幅器（-4.4 dBFS）把人聲峰值 true peak 從 -1.21 壓到 -4.19 dBTP，響度不變；整片偏小聲，若要 -14 把 yaml 兩個值改回預設。
4. 🟡 沒有人耳聽過配樂（只看頻譜圖：撥弦與 drone 如預期）；音量／風格請 Leon 試聽 part1／part2。

## final 評審
- 只跑成片評審，`new-cycle` 把 v2 的舊 3 輪（含青蛙、舊 rubric）歸檔到 `review/final/cycle-1`，新 cycle 第 1 輪：**未過**，客觀指標 visual／content 欄有關鍵項未過 → 退回 deck。修改清單 `output/yokai-kyubi-v3/review/final.fixes.json`，主要是：3:00–5:00 流失集中（純文字對照表、空白頁、4:40 靜止字卡 17.5 s、「我們的看法」重複）、2:50–4:20 約 90 s 無懸念。都是內容／簡報結構問題。
- 再跑 `produce.py run` 會停在 `waiting_agent: deck 退回重做`；要走第 2、3 輪（第 3 輪放行）需先改 deck 或手動放行。我沒改內容、沒用 `--auto-agents`。
- **未達標項**：上列 visual／content 欄關鍵項（音訊項不評）。

## 費用與牆鐘
- 本次新增雲端：final 第 1 輪 1 輪 7 席，名目約 **$2.3**（🟡 估：`review_cost_report` 為含 v2 clone 的累計 final 3 輪 $6.6，v2 已知 2 輪 $4.90 → 差 ≈ $1.7–2.3）；產出 agent $0；本機合成與 ffmpeg $0。預算 $20 未觸及。
- 牆鐘：約 50 分（複製 4.7 GB、assembly 94 s、等載入 mix 前排隊 ~3 min、mix 57 s、final 評審 ~2 min、預覽 2-pass ~5 min）。

## 其他
- `gate_title` 重跑時第 3 輪放行（「沒有首頁情境結果」缺競品首頁），非我改動。
- 縮圖左上標籤「山海經 · 九尾狐」白字落在淺底上對比偏低（🟡 目視），要改請改 `thumbnail.json` 的 badge。
- 清理：暫存放在 job tmp（頻譜圖、2-pass log）；沒有留在 repo。`output/yokai-kyubi-v3`（4.7 GB，ignored）與 `artifacts/kyubi-tweak/*.mp4` 留著給 Leon 看，需要時可手動刪。

## 進度紀錄
- 2026-10-23：分支 ff 到 fe97c23；v3 複製；縮圖、assembly、mix 完成；final 第 1 輪未過並停；對話遠低於 30 萬 token。
