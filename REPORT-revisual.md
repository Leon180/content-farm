# REPORT — revisual（分支 `worktree-cf-revisual`，自 a082593 快進）：CoWoS v4＋科技新知 2 支＋cel v4 重組裝完成，Wan 避臉

## TL;DR
- 🟢 **CoWoS v4**：29 張投影片中 AI 圖 15 張（原 2）、純文字頁 7 張（24%）、Wan 2 段（s02、s20，均無人物，已烤）、全部視差；`lint_deck` 0 條。成片 `output/cowos-v4/assembly/release.mp4`（664 s）。540p 兩段 12.6／12.5 MB、前後對照 6 格。
- 🟢 **科技新知 2 支**：各 4 張 AI 圖（hook／what／analogy／take，均為視差）＋ pulse 配樂，51.7 s。
- 🟢 **cel v4**：s01、s14 改視差（cel 現 0 段 Wan），重組裝，540p 兩段 12.0／12.1 MB 已覆蓋（覆蓋前驗過新檔：h264＋aac、各 242 s）。
- 🟢 **Wan 避臉**（orchestrator 追加）：lint `wan-face`、prompt 加「人物靜止」子句、`--negative-prompt` 臉部變形詞、deck skill 寫入；`wan-shots` 在 0 段 Wan 時降為 warn（`LintIssue.severity`，`--strict` 只擋 error）。
- 🟢 **heavy 預約環修正**（orchestrator 追加）：預約只對「更早排隊」的票生效，且只在有本機任務在跑時才生效。
- 🟢 pytest：`1918 passed, 1 skipped`（排除既有失敗的 test_multi_provider）；之後只加了 lint severity 測試（49 passed 重跑相關檔）。
- 🟡 **CoWoS 片長 8:23→11:04**：舊 `cowos-final` 的音檔只有 24 場景（舊稿），deck 現有 29 場景；`--force deck` 使 voice 步驟（VoxCPM2、同一 chipcat 參考聲音、tempo 1.15）重配全 29 場景（2043 s），所以是「旁白對上現行 deck」的結果，不是視覺造成。未重跑評審（內容照 deck 沒變）。
- 🔴 未做：Shorts／CoWoS 未做人耳聽感驗收；未打開瀏覽器看成片（只看了對照圖）。

## 1. 每支數字
| 片 | AI 圖 | Wan | 純文字頁 | 成片 |
|---|---|---|---|---|
| CoWoS v4 | 15（z-image-turbo，1280×720） | 2（s02、s20，各 ≈ 12.5 min） | 7/29 | `output/cowos-v4/assembly/release.mp4`；540p `artifacts/cowos-v4/cowos-v4-part{1,2}.mp4`（245k 視訊，12.6／12.5 MB）；對照 `artifacts/cowos-v4/compare.jpg` |
| Quad9 Short | 4（視差） | 0 | — | `artifacts/technews-v4/short-quad9-hn-50195959-v4.mp4`（7.5 MB） |
| LLM 形式驗證 Short | 4（視差） | 0 | — | `artifacts/technews-v4/short-verification-hn-50202217-v4.mp4`（6.9 MB） |
| cel v4 | 16（沿用） | 0（原 2，已清） | 6 | `cf-visual-v4/output/cel-run2-v4/assembly/release.mp4`；540p 覆蓋於 `cf-visual-v4/artifacts/cel-run2-v4/` |

對照圖（`compare.jpg`）左舊右新：s02、s17、s07、s20、s31、s18。🟡 舊片音檔場景較少，同一 slide id 的舊畫面與新畫面時間點只近似對齊（取各自 slide 起點＋4 s）。

## 2. 費用與牆鐘
- 費用：**$0 雲端**（無 `claude -p`、無付費 API；本機模型）。
- 執行（機器）：CoWoS voice 2043 s、illustrate 746 s（15 張）、media 366 s＋Wan 重跑 media、assembly 101 s、mascot 131 s、mix 30 s、Wan 烤 765＋742 s；Shorts 渲染 424 s（無視差版，已捨棄）＋204 s（視差版）／另一支同量級；cel media＋assembly＋mix 數分鐘、540p 轉檔約 2 分鐘。
- 排隊／死結：第一輪佇列三方互等 ≥ 40 分鐘零執行（見 §3）；其後各步仍有 swap／load 閘門的短暫等待（log 未計秒）。Wan 烤時 `waited 0.0 s`（單獨跑，佇列空）。

## 3. 改了哪些檔（供合併）
| 檔案 | 改動 |
|---|---|
| `src/content_farm/explainer/lint.py` | `wan-face`；`LintIssue.severity`；`wan-shots` 0 段時 warn |
| `scripts/deck_to_script.py` | `--strict` 只計 error |
| `src/content_farm/explainer/wan.py` | `FACE_CLAUSE`、`NEGATIVE_PROMPT` → `--negative-prompt` |
| `src/content_farm/lanes/resources.py` | anti-starvation：只為更早排隊的票預約＋需有本機任務在跑 |
| `channels/chipcat.yaml`、`channels/technews.yaml` | 圖像模型改 `z-image-turbo`（klein 權重不在離線快取） |
| `src/content_farm/production/news/glossary.yaml` | 與 `cf-technews-run1` 同內容（含 DNS 詞條，Shorts lint 需要；本 worktree 原版缺） |
| `.claude/skills/deck/SKILL.md` | Wan 無臉規則 |
| `tests/unit/test_visual_v4.py`、`test_lanes_resources.py`、`test_explainer_motion.py`、`test_explainer_illustrate.py` | 新測試／期望值同步 |
| `CLAIMS.jsonl` | 覆寫了 visual-v4 帶來的版本（合併時可能衝突，取聯集） |

預約環根因（🟢 原始訊息）：`chipcat/cowos-v4:slides ↳ reserved for deepsea:voice-design`、`deepsea:slides ↳ reserved for chipcat/cowos-v4:slides`、`voice-design ↳ reserved for chipcat/cowos-v4:slides`（且 voice-design 缺 1.7 GB 記憶體）。新規則下沒有環（全序＝排隊時間），無任務在跑時預約不生效。測試：`test_reservations_never_form_a_ring_and_need_a_running_job_to_wait_for`。

## 4. 給接手者的坑（🟢 都踩過）
- worktree 沒有 `.env`：`produce.py` 要帶 `--env-file /Users/lileon/project/content-farm/.env`；`news.py render`（Shorts）不吃 `--env-file`，需在環境變數給 `CF_MFLUX_BIN_DIR=~/.local/share/mflux/venv/bin`、`CF_MFLUX_HF_HOME=~/.local/share/mflux/hf`，**並給 `CF_MLX_VIDEO_HOME=~/.local/share/mlx-video`，否則 AI 圖全部是靜止（credits 寫 `motion tools not configured`），第一輪 Shorts 就是這樣被我丟掉重跑。**
- Shorts 的步驟表沒有 `mix`：配樂要另跑 `scripts/audio_mix.py --run-dir <dir> --channel technews`（我做了）。建議把 mix 接進 NEWS_SHORT_STEPS（未做）。
- 舊 cowos deck 的 `thumbnail_variants.json`／缺 `titles.json` 與現行 schema 不合（label ≤ 8 字、需 titles.json）；我補了 titles.json、縮短 1 個 label。
- `--force deck` 會連帶重配全部旁白（CoWoS 花 34 分）；若要真正「沿用配音」，下次改只 force `media`。
- Wan 烤前不要跑任何 ffmpeg（烤機會等 ffmpeg 結束）。

## 5. 清理
`~/.claude/jobs/af5727eb/tmp`（隨 job 清）；`output/`、`artifacts/*.mp4` 未 commit；無殘留背景程序。未動 deepsea worker 的任何票或 worktree。未 push、未付費、未開瀏覽器、未上傳。

## 進度紀錄
- 2026-10-24：全部完成；對話約 25 萬 token 以下。
