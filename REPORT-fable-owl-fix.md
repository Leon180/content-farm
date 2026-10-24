# REPORT — 貓頭鷹不長人手＋「鳥／鷹」念錯修正（fable）

分支 `worktree-cf-fable-owl-fix`（自 `worktree-cf-brand-kit` 快進；thumbnail-v2 沒有多出 commit）。未 push、未付費服務、未開瀏覽器、未上傳。等級：🟢 本機實測 ／ 🟡 有保留 ／ 🔴 未驗。

## TL;DR
- 🟢 貓頭鷹片 9 張插圖裡 **3 張**貓頭鷹長出人手（b2.2 拿羽毛筆寫字、b3.2 拿筆、b4.2 雙手拿書）；三張都**第一次重生就沒有手**，已重組裝（沿用配音與字幕）。
- 🟢 規則已寫進程式：fable 頻道 `animal_characters: true`（每張圖加「動物保持動物身體」規則＋預設 negative prompt）、lint 擋 holding／hands／arms／fingers／reading 等字眼、SKILL 說明。
- 🟡 鳥／鷹念錯：原樣 VoxCPM2 把「貓頭鷹」念成「貓頭七／旗／起」、「鳥」念成「球／酒／油」。鷹改送「英」（ASR 回讀 2/2 對）；**鳥改送「尿」（niào，回讀 6/6 是「尿」，聲調差一聲，🟡 要耳聽）**。
- 🟢 為什麼沒被抓到：見 §3。已修（key term＋逐次計數）。
- 🟡 **中片與貓頭鷹片都已上傳私人，要重傳**：中片 `elOj9nypwGo`、貓頭鷹短片 `jzUQP3xQR8Q`（`upload_result.json` 記的）。上片包 video.mp4 已換新版，舊檔改名保留。
- 測試：全套 2005 passed, 1 skipped（排除既有失敗的 test_multi_provider）。

## 1. 有手的畫面（前後對照 `artifacts/fable-owl-fix/before-after.png`，上排舊、下排新）
| 畫面 | 舊 | 問題 | 新 prompt 重點 | 重生 |
|---|---|---|---|---|
| b2.2（也用在 b7 對照列） | `before/b2_2.png` | 羽毛筆握在手裡、另一手按書 | 本子翻開放桌上、羽毛筆與蠟燭在旁、貓頭鷹翅膀收起站在桌緣樹枝 | 1 次（seed 44 不變，prompt 改）🟢 無手 |
| b3.2 | `before/b3_2.png` | 屋頂上拿筆在本子上寫 | 貓頭鷹翅膀收起站屋脊、翻開的本子放在屋瓦上 | 1 次 🟢 無手 |
| b4.2 | `before/b4_2.png` | 雙手捧著綠色書本閱讀 | 合起的本子放在樹枝上、貓頭鷹翅膀收起坐在旁邊（轉頭） | 1 次 🟢 無手 |

（三張都沿用原 seed，prompt 與 negative 改了；`reseed` 機制備用，這次沒用到。）
- 保留未重生：b1.1（站柱上、本子放旁邊）、b2.1、b4.1（貓頭鷹站樹枝、書放樹枝上，無手）、b5.2；刺蝟 b3.1（前爪捧麵包）、b5.1（前爪握推車把）是動物的自然前爪，🟡 如要更嚴格可再重生。
- 生圖模型 Z-Image-Turbo 可能忽略 negative prompt（蒸餾模型 guidance 低），所以規則同時用**正向敘述**寫進 prompt；兩者都送。negative 是否有效 🔴 未做對照實驗，這次靠正向構圖＋看圖驗證。

## 2. 規則（附測試，`tests/unit/test_fable_animal_bodies.py`）
- `explainer/illustrate.py`：`ANIMAL_BODY_RULE`、`ANIMAL_NEGATIVE`（human hands, hands, arms, fingers, holding, gripping, anthropomorphic hands, humanoid body, standing like a person, writing with a pen）、`with_animal_rules()`；`IllustrationRequest.negative_prompt` → mflux `--negative-prompt`。
- `channels.py`：`ai_illustration.animal_characters`（預設關；fable 開）。其他有動物角色的頻道日後在 yaml 開同一旗標即可。`channels/styles/fable.md` 不存在，風格前綴在 `channels/fable.yaml`，規則放那裡與 `.claude/skills/fable-script/SKILL.md`。
- `fable/check.py`：`HANDS_WORDS` lint（提示詞出現 hands／arms／fingers／holding／gripping／reading／writing with… 就退回，附改法）。
- `fable/images.py`：重生用 `reseed`（每次 +1000 seed）；sidecar 記錄 negative_prompt。
- **偵測（QC）**：本機沒有可用的「畫面有人手」偵測；沒有加影像 QC 警告。只能靠生成規則＋lint（擋提示詞）＋人眼。🔴 不宣稱能自動抓。
- 順手修的 bug：`compose.pingpong` 以檔名快取，**重畫的圖仍播舊的 loop**（第一次重組裝的片裡三張還是舊圖，抽格才發現）。改為 clip 比 loop 新就重建，附測試。

## 3. 鳥／鷹念錯
**發音表**（`channels/shared/pronunciation.yaml`，voxcpm2，來源＝`scripts/pronunciation_trial.py` 試驗，fable 參考聲，whisper 回讀）：
- 鷹：原樣 → 貓頭**七**（2/2 seed）。候選：英 → 回讀「貓頭鷹」2/2；嬰 → 迎／銀；鶯 → 尹／鷹 1/2。取「英」。key 用 2 字以上詞（`貓頭鷹→貓頭英`、`鷹鴿→英歌`、`派是鷹→派是英`、`派是鴿→派是歌`），因為回讀對照會略過單字，避免「英國」被改成「鷹國」。
- 鴿 gē 也被念歪（中片 scene_016「英鴿」→「英之」「是獅」，重生 3 次不變），改送「歌」；重跑後 scene_016 第 1 次就過（回讀「鷹歌博弈…是鷹…是歌」）。
- 鳥：原樣 → 球／酒／油／九（9 次全錯，連「飛鳥」、「鳥兒」也錯，鳥兒只 1/3）。裊／嫋／嬝／褭／蔦 → 鳩、寧、弄、庫、柱（念成別的音）。**尿**（niào）→ 回讀「尿」6/6。🟡 這是聲調差一聲的同音替字，聽感上「小尿」可能怪，**請 Leon 耳聽**；若不接受，退路是 `鳥兒`（1/3）或不處理（念成「酒」）。字幕仍是原文「鳥」。
**為什麼既有檢查沒抓到**（🟢 用 speech_check.json 查）：
1. 鳥、鷹不是 key term；單字念錯對整段 CER 只貢獻 0.02–0.03，門檻 0.12 → 貓頭鷹 scene_004（CER 0.086）、005（0.07）都是 `ok`，回讀明明是「貓頭七／起」。
2. scene_002、007 其實是 `warn`，但 warn 是「保留最佳一次、繼續」，不擋、也不在成片報告顯眼處。
3. key term 只檢「有沒有出現」，一句裡有兩個鷹聽到一個就過。
修正：鳥、鷹列為 key term；`missing_terms` 改**逐次計數**（講稿出現 n 次、回讀要聽到 ≥ n 次）；測試用 speech_check.json 的真實回讀（貓頭起／七、球）驗證會抓。🟡 單一 `warn` 仍不擋成片，沒改（那是政策）。

## 4. 成品
| 片 | 狀態 | 路徑 |
|---|---|---|
| 貓頭鷹的小本子（Short，82.7 s） | 重畫 3 圖＋重配含貓頭鷹的 4 個場景（002/004/005/007，回讀全聽到「鷹」）；QC 0 error, 1 warning | `artifacts/fable-owl-fix/release.mp4`（1080×1920）、`fable-confirmation-short-540w.mp4`（540 寬預覽）、`contact.png`（抽格）；run-dir `output/fable-confirmation-short/` |
| 中片「老樹林的山雀」（鷹鴿博弈） | 只重配含鳥／鷹／鴿的 11 個場景；QC 0 error, 1 warning；全 23 場景回讀 missing_terms 為空 | `artifacts/fable-owl-fix/fable-ess-mid-release.mp4`、`fable-ess-mid-540-part1/2.mp4`（各 ~6.3 MB） |
上片包（`/Users/lileon/project/content-farm/output/upload-20261024/`）：
- `fable-confirmation-short/video.mp4` 換新；舊檔 → `video-v1-hands.mp4`
- `fable-ess-mid/video.mp4` 換新；舊檔 → `video-v1-pron.mp4`
- 🔴 `metadata.md`、kit 沒動；縮圖沒動。**兩支都已上傳私人，需重傳**（我沒上傳）。
- 🟡 沒有人耳聽過新配音（尤其「尿」）、沒有完整看過成片；只抽格看過。

## 5. 其他片檢查
- 圖（子代理逐張看，Sonnet）：asymmetry-short 8 張、gradient-short 8 張、ess-mid 32 張。**ess-mid、gradient 無手**（鳥只有翅膀與爪、熊／狗自然）；**asymmetry b2_1 borderline**（狐狸抬手抓燈桿，像人手臂）→ 未重做，回報即可。🟡 這是模型判讀。
- 鳥／鷹字：asymmetry、gradient 的 voice_text 無這兩字；technews（v1 兩支、run1/2、v4）、ent 三支的 voice_text 也無。yokai kyubi 的 metadata 有「鳥山石燕」「鳥羽天皇」（來源名，不一定在旁白；我沒掃它的旁白稿）。deepsea／cel／chipcat 的旁白未掃 🔴。
- 發音表對 fable 以外 provider（qwen3_tts、fish）未試；只加在 voxcpm2。

## 6. 費用與清理
- 雲端 $0（只有已存在的審稿 gate 重新放行，未開新輪；沒有 `claude -p` 產出）。本機：生圖 3 張、配音 2 輪、試驗 2 輪（約 8 分＋）、重組裝。大半是排隊（swap ≥ 90%）。
- 清理：舊三張圖與 sidecar 用 `mv` 移到 `artifacts/fable-owl-fix/before/`（`rm` 在 deny）。`$CLAUDE_JOB_DIR/tmp` 有試驗 wav（`pron-trial*`），可刪。**注意**：這條分支追蹤了 `__pycache__/*.pyc`（brand-kit 帶來的），工作樹顯示一堆 modified pyc，我沒有 commit 它們，也沒清；建議 orchestrator 處理（`.gitignore`＋`git rm --cached`）。
- 複製了 run-dir 到本 worktree 的 `output/`（gitignore，不 commit）；原 `cf-fable` worktree 的 output 沒動。

## 7. 要 Leon 決定
1. 「鳥→尿」耳聽後接不接受？
2. 兩支私人影片重傳（中片 elOj9nypwGo、短片 jzUQP3xQR8Q）。
3. asymmetry b2_1（狐狸抬手）、刺蝟 b3.1／b5.1 要不要也重畫。

## 進度紀錄
- 2026-10-24：貓頭鷹片重畫／重組裝、中片重配完成；全套測試通過；報告寄出。對話 token 未超過交接門檻。
