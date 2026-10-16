# 開台片政策審查修正（feat/launch-fixes）— 進度報告（未完成，用量上限中斷）

## TL;DR
- 🔴 **未完成**：四支新成片、manual-kit、preview 都**還沒渲染**；Short 重剪、yokai s06 重生、cel/CoWoS 重配音都還沒做。用量上限到了，停在中途。
- 🟢 已 commit（分支 `feat/launch-fixes`，base `195561d`；ai-motion 沒有 REPORT，所以不從它開）：Fish 模型可設定、頻道 identity＋規則＋QC、縮圖產生器 R2、新聞卡「媒體原標題／本頻道摘要」、Route A 貓 rig（cherry-pick `301bd21`）。
- 🟢 pytest：除了基準就失敗的 `test_multi_provider…returns_first_provider_results`，其餘全部通過（deselect 那支後 0 failed），新增 25 支測試。
- 🟢 CoWoS／cel 的 deck 已改好，strict lint 也通過（只存在 `output/`，是 gitignored 的 run-dir；改法可以用 `docs/launch-fixes/edit_*_deck.py` 重跑）。

## 已完成（commit）
1. **Fish TTS 模型**（orchestrator 要求）：`CF_FISH_AUDIO_MODEL`，預設 `s2.1-pro`；頻道 yaml 可用 `voice.model` 覆寫。模型納入 voice 指紋與每場的 `voice_identity.json`。沒有 model 欄位的舊紀錄一律視為 `speech-1.5`（SDK 舊預設）。
   - **換聲音時要跑的指令**：在 `.env` 改 `CF_<CH>_VOICE_ID`（或 `CF_FISH_AUDIO_MODEL`），再執行 `python scripts/produce.py run --channel <ch> --run-dir <run> --allow-paid`。voice 步驟會整片重配。gate_media／gate_final 要重新核可。
   - **本輪改動場景的重配**（還沒做）要在 env 設 `CF_FISH_AUDIO_MODEL=speech-1.5`，這樣未改動的場景會重用舊音檔，不會出現同一支片混用兩種模型。
2. **頻道差異化**：`channels/{chipcat,cel,yokai}.yaml` 新增 `identity`，包含開場格式與口播簽名、觀點段名稱、片尾簽名、片尾卡句子、說明欄 header／來源標籤／footer。
   - `publish.build_description` 改用這套模板。
   - 跨頻道撞句由測試檢查。
3. **規則與 QC**（`production/channel_rules.py`，policy 步驟和 QC 都會跑）：
   - 開場和片尾必須有頻道簽名；
   - 禁用模板句，例如「用二十四張圖」「我先把結論放在這裡」「所有數字附來源」，也禁用他頻道的簽名；
   - 至少一張 `take: true` 的原創觀點投影片；
   - 有 rig 的頻道，角色要出現在 80% 以上的投影片。
   - 偵測器已驗證會命中：未修改的 cel deck 跑出 3 個 error；這是對照組。
4. **片長**：三個長片頻道改為 `target_seconds [420,600]`、`goal_seconds 480`，低於 8:00 時 QC 給 warn。
5. **新聞卡**：`Source.headline` 存媒體原標題（原文），卡片上分開標「媒體原標題」和「本頻道摘要」。沒有原標題時，卡片標「非媒體原標題」，lint 也會擋。各篇原標題已抓好，寫在 edit scripts 裡。
6. **縮圖產生器 R2**：`thumbnail.json` → `scripts/make_thumbnail.py` → `thumbnails/thumbnail.png`，另外輸出手機尺寸版。
   - QC 檢查：大字 ≤10、promise 要在前 60 秒的講稿裡出現、縮圖上的數字要出現在講稿裡、晶片貓頻道的縮圖必須有貓。
   - runner 新增 `thumbnail_spec` 和 `thumbnail` 兩個步驟；preview 的縮圖區多一張手機大小的預覽。
   - 三張縮圖已產出，在 output/ 底下：CoWoS 用 Route A 驚訝貓、九尾狐用北齋〈九尾狐〉CC0、cel 用品牌主視覺加「6成 業績變差」。cel 的 promise 檢查目前會報錯，因為講稿還沒重配。

## 已改但未渲染（output/，gitignored）
- **CoWoS deck**（`edit_cowos_deck.py`）：
  - s09「超級載板」改為「9 倍光罩中介層，7,722 mm²，約 8.8 公分見方」。依據 IFTLE 615；子代理查證 7,722 mm² 是中介層面積，基板「超過 120×120 mm」。
  - s01／s03 去掉模板句；s02 的「媒體轉述」改成卡片小字；s24 換上頻道片尾。
  - 新增 4 張：k1 一片晶圓排得下幾片（自算約 70→17→10→5，腳本在 job tmp 的 `pack.py`，**還沒放進 repo**）、k2 產能翻倍不等於晶片翻倍、k3 晶片貓的三個判斷、k4 看新聞盯三個數字。
  - 估計片長約 9.2 分鐘（新的 5.5 字/秒估算）。實際片長要配音後才知道。
- **cel deck**（`edit_cel_deck.py`）：
  - s03 改「六成業績變差」；s10 畫面註記「本頻道依兩項不同口徑資料估算」；開場和片尾改成 cel 自己的版本。
  - 新增 MAPPA《鏈鋸人》100% 出資段（c1–c3，來源 ANN 2022-07-11、東洋經濟 2023-05-17、ANN 2023-05-18）。估計約 8.5 分鐘。
- **yokai s06**：Z-Image 試了 seed 1/2/3，尾巴分別約 5／7／6 條，都不是 9 條。seed 7/11/23/42 正在背景跑，候選圖在 `~/.claude/jobs/dcda373f/tmp/s06/`。如果還是數不到 9 條，就改圖說（例如「AI 示意圖・尾數非依原典」）。

## 還沒做的
1. 7,722 Short 重剪：鉤子開場、旁白說出「8.8 × 8.8 cm」、下半部放貓和逐步長大的光罩動畫、不留靜止畫面。要新寫配音，ShortSpec 要擴充。
2. CoWoS 和 cel 依上面的 model pin 重配有改動的場景，然後重跑 media、assembly、mascot（Route A），再跑 thumbnail、QC、manual-kit。
3. yokai：決定 s06、把 s25／s26 標成 take、重跑 illustrate、media、assembly，做出 final。
4. 每條修正的前後對照截圖、REPORT 完整版、CLAIMS 補齊。
5. 頻道片尾目前只有口播簽名和 `endcard` 文字設定，還沒有真的把片尾卡畫面接到成片尾端。
6. deck skill（`.claude/skills/deck/SKILL.md`）還沒寫入縮圖、觀點段、頻道開場的規則。規則目前只在程式和 QC 裡。

## 副作用與清理
- `output/` 底下的四個 run-dir 是從 cf-real-voice／cf-ai-illustration 複製來的，來源沒有改動。
- job tmp 裡有 patch scripts、`pack.py`、s06 候選圖。
- 背景還有一個 mflux 生圖程序（s06 seeds），跑完會自己結束。
- 沒有 push，沒有開瀏覽器，沒有呼叫 Fish TTS。外部存取只有子代理的 WebSearch／WebFetch，以及我抓的一頁 phileweb。
