# REPORT — offwork skit build（(a) 劇本 agent＋skill、(b) 選題＋劇本評審團）

## TL;DR
- 🟢 (a)(b) 完成，全套 pytest 綠（1753 passed，僅既有的 `test_multi_provider` 1 項失敗）。
- 🟢 驗收跑通：`produce.py run --channel offwork … --auto-agents` 一路跑到 **voice 產出音檔**（`output/offwork-run2/audio/scene_001–003.mp3`、`subtitles.srt`），停在 `skit_render`（預期）。
- 🔴 **劇本評審團三輪都沒過**（writer_comedy 5 → 4.5 → 4 < 6.5；三位觀眾離開中位 0.53/0.69/0.69 都過 0.4 門檻）。為了驗收流程，我用 `produce.py approve --gate script --override "…--force 授權…"` 手動放行（紀錄在 state）。**這支笑話本身沒過品質關，不是可上片的稿。**
- 費用（名目，訂閱計費）**$1.28**（預算 $20）；牆鐘 6m28s、機器 4m24s（雲端 3m24s／本機 voice 1m00s）；評審 **3 輪**（shorts_topic 1 輪、shorts_script 3 輪）。

## 做了什麼
- (a) `src/content_farm/production/skit.py`＋`scripts/check_skit.py`＋`.claude/skills/skit-script/SKILL.md`：格式放在 `Script` 模型保得住的欄位（voice 步驟會用該模型整份重寫 script.json，額外欄位會掉）——`scene.title`＝`NN 鋪陳|笑點|收尾`、最後一場鋪陳 `transition: "pause:0.6"`、`visual_hint.description`＝金魚表情（neutral/surprised/smug/speechless，測試對照 pack manifest）。檢查：1–3 場鋪陳＋1 場笑點（≤40 字）＋可省收尾、20–50 秒（5.5 字/秒＋停頓）、不用「狂」「絕了」、「欸」≤1、AI 揭露。
- (a) 註冊：`panel_flow.PRODUCER_STEPS`、`review/producers.py`（`skit_script` 任務／退回任務／`check_skit.py` 白名單、`STEP_STAGE`）、`routing.PIPELINE_ORDER`、`REWORK_STEPS`、`usage.PRODUCER_STAGE`；產出若違規會被 `channel_rule_violations` 還原重做。
- (b) `SHORTS_SKIT_STEPS` 前面加 `topic`／`gate_topic`；`Gate.TOPIC` 列為 shorts_skit 必備、`offwork.yaml` gates＝[topic, script, final]。冷笑話選題 agent 不查資料、不需來源，用 `shorts_topic` 的 sonnet 層（長片的 topic 是 opus）。
- (b) 評審團（`channels/shared/review_panels.yaml`）：新角色 `writer_comedy`（rubric 笑點／鋪陳／停頓／時長／頻道調性；明寫不評音效配樂）；`personas.offwork`（6 位，含 1 位 holdout）；`channels.offwork.stages.shorts_script`：3 觀眾＋1 writer_comedy、rework→`skit_script`。`config.ROLE_ALTERNATES` 只讓 shorts_script 的 writer_story 可由 writer_comedy 替代，其他規則不放寬。全部 sonnet·low。
- 劇本素材 `materials.short_script`：有 pause 時列場景結構（金魚表情、之後停頓秒數）與估計片長給評審看。
- 測試：`test_production_skit.py`（19）、`test_review_skit_flow.py`（12，含整條 topic→panel→skit_script→panel→voice、低分退回 `skit_script`）。

## 驗收跑的細節（run-dir `output/offwork-run2`，已 gitignore）
- topic：10 題原創冷笑話（沿用 backlog 的 friday-deploy 等），shorts_topic 第 1 輪通過；選 t01「週五下午五點的部署」。
- 評審退件原因（原文摘要，round-3）：笑點「那一行字，還在。」因果不清、非上班族看不懂；「週五部署出事」是工程師圈轉過無數次的梗；收尾像唸規則、連三個「而且」。→ 評審判斷合理，我同意（🟡 主觀）。
- 模型是 sonnet·low 產出：三輪改稿只是精簡，沒換梗。**若要自動過關，需讓產出 agent 在退回時換梗（目前 TASKS_REWORK 寫「不要換笑點的梗」），或提高產出層級——這是取捨，留給 Leon/orchestrator。**
- 手動放行為 `--override`（後門，已記錄）；之後 `--until voice` 跑完，voice 1m00s（含排隊 1m00s）。

## 沒解決／已知
- `gate_script` 的觀眾 prompt 仍是通用「投影片」措辭（segments.slide_id 實際是 c1…c3 場景），模型照樣答得出來，沒出錯，但措辭可再貼近短片。🟡
- `brands.py` 的 offwork `BrandSpec` 仍寫「下班貓＋PM 狗」，與 `offwork.yaml`（飲水機金魚）不一致；我照 yaml，沒動 brands。backlog 的 `pm-yidiandian`、`box-packaging`（貓）需要別的角色，金魚單人劇演不了，選題 agent 已被要求只出金魚能演的題。
- 選題通過但 `top_n_short: 3`，只取 `chosen[0]` 寫劇本。

## (c) 渲染器設計草案（下一輪，未動工）
- 輸入：`script.json`（scenes/pause）、`audio/scene_*.mp3`、`subtitles/subtitles.srt`、金魚包 `pngtuber/cooler-goldfish-3d`。輸出 `assembly/final.mp4`（9:16，1080×1920）。
- 時間軸：逐場音檔長度＋ pause 場後插 0.6 秒靜音（`transition=pause:0.6`，空白畫面不換表情，金魚維持鋪陳表情，笑點才切）。總長 = Σ音檔 + 0.6。
- 畫面：純色／品牌 pastel 底（offwork 品牌 collage/pastel），不放素材；金魚用既有 `pngtuber/run.run_host_overlay`＋`render.VERTICAL` placement（左下，高 440，字幕禁區 y 1220–1420 已定義）。參考 `shorts_scripted_render._overlay_host` 的 SceneCue 做法，把 `visual_hint.description` 轉成 SceneCue.pose（pack 的 `pose_map` 目前是空的，要補 neutral/surprised/smug/speechless 對應）。嘴巴已移除，講話用氣泡（pack `speech_fx`）。
- 字幕：沿用 voice 步驟的 `subtitles.srt`（offwork 設 24 字/行）→ SRT→ASS（PlayRes 1080×1920、置中、Bold），避開左下角金魚。笑點那句可放大字級（單句、≤40 字）。
- 步驟：`skit_render` 改成 `cmd`（heavy），輸出 `assembly/final.mp4`；`qc` 與 `gate_final`（shorts_final：3 觀眾＋editor_visual）沿用。音效、「叮」、配樂依 Leon 規則後期加，不進這一輪。
- 測試：對齊檢查（總長 = 音檔和＋0.6、笑點前恰有 0.6 秒無聲、金魚不進字幕禁區，沿用 `mascot clearance` 測試）。

## 副作用／清理
- `output/offwork-run2/`（gitignore）可刪（`rm` 在 deny，留給 orchestrator）。無其他暫存檔；沒 push、沒付費服務、沒開瀏覽器、沒上傳。
- 起點：分支 ff 到 `f00a946`（`worktree-cf-offwork-run1` 最新）。

## 進度紀錄
- (a)(b) 兩個 commit 完成、全套綠；驗收跑到 voice；報告與 CLAIMS 寫完後寄信。
