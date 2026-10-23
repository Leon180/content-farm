# REPORT — revisual（分支 `worktree-cf-revisual`，自 a082593 快進）：卡在 heavy 佇列，視覺尚未重出

## TL;DR
- 🟢 程式側完成並 commit：Wan 避臉（lint `wan-face`、Wan prompt 加「人物靜止」子句、`--negative-prompt` 臉部變形詞）、chipcat／technews 改用已快取的 z-image-turbo（同 cel 先例）。pytest 全綠（排除既有失敗的 test_multi_provider）。
- 🟢 CoWoS v4 deck 已改好（`output/cowos-v4/deck.json`，gitignore）：31 張中 AI 圖 15 張（原 2）、純文字頁 7 張（23%）、Wan 2 段（s02、s20，皆無人物）、`lint_deck` 0 條。旁白、id、來源沒動。
- 🟢 cel v4 的 deck（`cf-visual-v4/output/cel-run2-v4/deck.json`）s01、s14 已改 parallax（兩段 Wan 都清掉；cel 現在 0 段 Wan，lint 會報 `wan-shots`，見 §3）。**尚未重組裝。**
- 🔴 **所有重步驟都沒跑**：slides／illustrate／media／assembly 皆需 heavy 票，佇列三方互等（§2）。成片、540p、前後對照、科技新知 2 支都**未產出**。
- 費用 $0；牆鐘：開發約 1 h；排隊 ≥ 40 分鐘（全是死結等待，零執行）。

## 1. 已改檔案（供合併）
| 檔案 | 改動 |
|---|---|
| `src/content_farm/explainer/lint.py` | 新增 `wan-face`：Wan 鏡頭的 prompt／motion_prompt 含人物／角色／臉／表情等字報錯；「no people」例外 |
| `src/content_farm/explainer/wan.py` | `FACE_CLAUSE` 接在 prompt 後、`NEGATIVE_PROMPT` 以 `--negative-prompt` 傳給 mlx_video（舊快取因 prompt 變動自動失效→退回視差） |
| `channels/chipcat.yaml`、`channels/technews.yaml` | `ai_illustration.model` → `z-image-turbo`（klein 權重不在離線快取） |
| `.claude/skills/deck/SKILL.md` | 寫入 Wan 無臉規則 |
| `tests/unit/test_visual_v4.py`、`test_explainer_motion.py`、`test_explainer_illustrate.py` | 新測試與期望值同步 |

## 2. 死結（原始訊息）
`scripts/heavy --status`（我 kill 自己的票前）：
```
1. long chipcat/cowos-v4:slides  waiting 25m  ↳ reserved for deepsea:voice-design (waiting 2350 s, anti-starvation)
2. long deepsea/deepsea-1:slides waiting 22m  ↳ reserved for chipcat/cowos-v4:slides (waiting 1518 s, anti-starvation)
3. other deepsea:voice-design 19.5 GB gpu=exclusive waiting 39m
   ↳ memory: 20.8 GB free ... < 19.5 + 3 GB，差 1.7 GB；reserved for chipcat/cowos-v4:slides
```
三張票的 anti-starvation 預約互指成環，且 voice-design 本身缺 1.7 GB 記憶體，沒人能先動。更早一次（只有我與 voice-design）是「heavy process outside the queue pid 14490」互等，與 technews-run2 報告 §1 同一型。🟡 推測根因：預約判斷沒排除「預約對象自己也在等」。**我已 kill 自己的 produce（票），未動 deepsea worker 的票。**

## 3. 待辦（依序）
1. 佇列暢通後：`produce.py run --run-dir output/cowos-v4 --channel chipcat --no-panels --no-stock --force deck --until slides`，再 illustrate→media→（gate 以 `--override` 核可，理由：旁白沿用、授權程式規則）→assembly→mascot→mix；14 張新圖約 13 分。
2. Wan 烤 s02、s20（`scripts/ai_motion.py bake --run-dir output/cowos-v4`，各 ~15 分、26 GB，須單獨跑）。
3. 兩支 technews Shorts：已複製為 `output/technews-v4-50195959`、`-50202217`，尚未補 `Beat.image_prompt`（需 ≥3 張）。
4. cel v4：以 deck（已改）重跑 media→assembly→mascot→mix，轉 540p 後覆蓋 `cf-visual-v4/artifacts/cel-run2-v4/`。**取捨待 orchestrator 決定**：cel 無 Wan 會被 `wan-shots`（長片 2–3 段）報錯；可換兩個無人鏡頭（例：s01 桌上報紙原本就無臉，Leon 看到的變形可能來自別處）再烤，或放寬 lint 對「找不到無臉鏡頭」的要求。
5. 對照圖 6 格、540p 兩段 ≤13 MB。

## 進度紀錄
- 2026-10-24：程式與 deck 改完；佇列死結，停下回報。對話遠低於 30 萬 token。
