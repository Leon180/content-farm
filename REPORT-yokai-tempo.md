# REPORT — 九尾狐開台片 tempo 1.20 → 1.29（決策 40e6b445a7ed）

## TL;DR
- 🔴 **前提失效，已停下**：`produce.py run` 在第一個步驟 `policy` 就失敗：`青蛙書記 on 0/29 slides (>= 80%)`。配音、media、assembly 都還沒跑。
- 原因：`feat/incremental-render` 帶進了 `design/channel-hosts`（d95ee3e，Leon 10-17 選的 Y14 青蛙書記，`rig_ready: true`）。這條規則要求 ≥80% 投影片有主持角色。launch 版的 run-dir 是在 `feat/channel-voices` 上做的，那條分支沒有這個 commit，所以 deck 裡 `mascot` 是 0/29。
- 要繼續就得**在 deck 裡加角色**（這是內容變更，要重審 gate_deck，還要新跑 mascot 疊加），已經超出「只改語速」的範圍。下面列了三個選項，等 Leon 決定。
- 已完成：yokai tempo 改成 1.29（只改這個頻道），測試跟著改。run-dir 複製到 `output/yokai-kyubi-v2`，音檔沒動過（`tempo.json` 仍然 29×1.2）。

## 失敗原文 🟢
```
✗ policy: 青蛙書記 on 0/29 slides (>= 80%)
[failed] policy: 青蛙書記 on 0/29 slides (>= 80%)
```
`production.log.jsonl`：`{"at": "2026-10-18T09:25:50+00:00", "step": "policy", "outcome": "failed", "message": "青蛙書記 on 0/29 slides (>= 80%)"}`

- 規則：`src/content_farm/production/channel_rules.py:68` 的 `mascot_findings`，`MIN_MASCOT_SHARE = 0.8`；只有 `channel.mascot.rig_ready` 為 true 時才檢查。
- `channels/yokai.yaml`：`mascot: {name: 青蛙書記, ref: pngtuber/frog-scribe, host: pngtuber, rig_ready: true}`，來自 d95ee3e（2026-10-17 14:02 +0800）。
- `git branch --contains d95ee3e` 的結果是 design/channel-hosts、feat/cowos-v3、feat/incremental-render、feat/review-panels、feat/yokai-tempo，**沒有 feat/channel-voices** 🟢。
- `grep -c '"mascot"' output/yokai-kyubi-v2/deck.json` → 0 🟢。

## 選項（等 Leon 決定，我沒有做）
| 選項 | 做法 | 影響 |
|---|---|---|
| A. 加青蛙書記（建議，符合 10-17 選角） | 在 deck 的 ≥24/29 張加 `mascot` pose，重審 gate_deck，再跑 voice（只重算時間）→ media → mascot → mix | 畫面多了角色，gate_media／gate_final 都要人看；角色可能擋字，要檢查；mascot 冷渲約 3 分鐘（依 incremental-render 的數字）|
| B. 這支片暫不放角色 | 在 run-dir 層級關掉 `rig_ready`（或讓 policy 對這支 run 放行），只改語速 | 跟頻道 10-17 的設定不一致；要改程式或頻道設定，不只改 tempo |
| C. 改在 feat/channel-voices 上跑 | 從沒有 channel-hosts 的分支跑 tempo 1.29 | 拿不到 incremental-render 的快取加速；之後合併時還是會撞到同一條規則 |

## 已完成的部分
- 分支 `feat/yokai-tempo` 從 `feat/incremental-render` 1352879 開。
- `channels/yokai.yaml` 的 `voice.tempo` 從 1.20 改成 1.29。其他頻道沒動：cel 1.12、chipcat 1.15、offwork 1.0，測試裡有斷言。
- `tests/unit/test_voice_tempo.py::test_channel_tempo_follows_decision_and_enters_identity` 改成 1.29：`pytest tests/unit/test_voice_tempo.py` 3 passed 🟢。全套沒有跑，因為只改了這一支測試的斷言。
- 已確認改 tempo 不會重新合成 🟢（讀碼）：`voice/generator.py:132` 的每段 identity 只看 provider、voice、model 和 TTS 文字，不含 tempo；tempo 只走 `tempo.retime`（第 323–327 行）。
- `CF_MLX_VIDEO_HOME` 已經在主 `.env` 裡（`grep -c '^CF_MLX_VIDEO_HOME='` → 1），media 不會再退回 Ken Burns。
- run 用的參數是 `--no-stock`（不打 Pexels）加 `--env-file /Users/lileon/project/content-farm/.env`。

## 還沒量的（因為停在 policy）
新片長、QC、拼音層級的念錯檢查、各步驟耗時、preview（`output/yokai-kyubi-v2/upload/manual/preview.html` 目前是複製來的 1.20 舊版）——全部 🔴 未產生。
- 估算（不是實測）：tempo 1.20 的版本是 641.6 s，raw 是 770.2 s，770.2 ÷ 1.29 ≈ **597 s（9:57）**。字/秒 ≈ 2,358 ÷ 597 ≈ **3.95**，比 CoWoS 4.53、cel 4.47 還低，不會觸發「比其他頻道高 25%」的門檻 🟡（用 channel-voices 報告的數字算的，沒有重量）。
- 拼音層級檢查：本機在 `/` 往下 7 層內找不到 pypinyin（`find` 零命中，沒有做對照組）🟡；repo 的 venv 裡也沒有。要做的話得先決定裝在哪裡（channel-voices §9-4 的同一個問題）。

## 副作用與清理
- `output/yokai-kyubi-v2/`：完整複製的 run-dir，gitignored。`production.json` 多了一筆 policy failed 的紀錄，音檔、media、assembly 都沒變。
- job tmp：`media_report.t120.json`（複製前的 media_report，之後做 gate_media 比對用），job 刪除時一起清掉。
- 沒有背景程序殘留：run 自己以 exit 1 結束。沒開瀏覽器、沒上傳、沒 push、沒用付費服務。

## 進度紀錄（append）
- 2026-10-18 開分支，改 tempo 和測試，複製 run-dir。
- 09:25 UTC `produce.py run` 在 policy 失敗，停下回報。
- 接手方式：Leon 選了選項之後，A 要先改 deck（加 mascot pose）並重審 gate_deck，再執行 `PYTHONPATH=<wt>/src .venv/bin/python scripts/produce.py run --run-dir output/yokai-kyubi-v2 --no-stock --env-file /Users/lileon/project/content-farm/.env`。
