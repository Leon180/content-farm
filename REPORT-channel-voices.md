# 頻道聲音：本機 TTS provider＋四支開台片重配（feat/channel-voices）

## TL;DR
- 🟢 四支開台片都用**本機 VoxCPM2** 重配完成，停在 **gate_final 等 Leon 核可**，四份 preview 在 §7。
  - **Fish 0 次呼叫**：晶片貓中途依決策改成本機女聲。
  - 每片的 QC error 都是 0。
  - 過程中 Leon 改了四次決策：晶片貓改本機（b6c665874b97）→ 晶片貓改女聲（b25068faf5a4）→ 加 tempo（944769e1fc01）→ 晶片貓 tempo 1.15（89e23b7129d2）。
- 🟢 provider（VoxCPM2／Qwen3-TTS，各自在 TTS venv 用子程序執行）、共用發音表、whisper 念錯檢查（CER＞0.12 或缺關鍵詞就換 seed 重生，最多 3 次）、資源閘門、頻道 `voice.tempo` 都已 commit。pytest：只有基準就失敗的 1 支，其餘全過（§8）。
- 🟡 **片長**（加速後）：
  - 九尾狐 **10:42**，超過頻道上限 600 s，QC warn；用的是 Leon 指定的 1.20。
  - cel 9:35、CoWoS 9:49、Short 0:28。
  - cel 沒有掉到 8:00 以下。
- 🟡 **念錯檢查仍 warn 的段落**，共 5 段，要人耳聽（§3.3）：
  - 九尾狐 s20 疑似真的念錯：「鳥」兩次都被轉回「修」。
  - 其餘四段多半是 whisper 寫成同音字或外文譯名。
  - 字元 CER 會把同音字算成錯，這是現行方法的限制；改用拼音層級的比對，需要在 venv 加 pypinyin，要 Leon 決定。
- 🟡 晶片貓女聲（Qwen3-TTS VoiceDesign 設計）和 cel 的說話人相似度是 0.44；cel 自己不同 take 之間是 0.82–0.84，所以聽得出是兩個人（模型量測，仍要人耳確認）。

## 進度（接手用）
- [x] 分支 `feat/channel-voices`，從 `48e2f70` 開；共 8 個 commit（§8）
- [x] 四個 run-dir 複製到本 worktree 的 `output/`；Short 的 `long_run_dir` 改指本 worktree 的 cowos-chipcat
- [x] voice ×4 → media（gate_media 由我重核，理由見 §7）→ assembly → QC → gate_final ×4
- [x] preview ×4

## 1. 決策紀錄（本輪中途改了四次）
| 時間 | 來源 | 內容 | 處理 |
|---|---|---|---|
| 派工 | 任務 prompt | chipcat 用 Fish 原創聲音 s2.1-pro；yokai、cel 用 VoxCPM2；offwork 用 Qwen3-TTS | 依此實作 provider |
| 15:4x | orchestrator b6c665874b97 | chipcat 也改成本機 VoxCPM2，不用 Fish | 改 `channels/chipcat.yaml`。Fish **一次都沒呼叫**，所以沒有 Fish 音檔需要保留 |
| 15:5x | orchestrator b25068faf5a4 | chipcat 改成女聲：用 Qwen3-TTS VoiceDesign 設計參考聲，再用 VoxCPM2 複製 | §4 |
| 17:0x | orchestrator 944769e1fc01 | 新增 `voice.tempo`：yokai 1.20、cel 1.12、chipcat／offwork 1.0 | §5 |
| 17:2x | orchestrator 89e23b7129d2 | chipcat 的 tempo 設 1.15（我回報 1.0 時 CoWoS 是 11:18） | §5 |

## 2. Provider 設計
- **兩個 provider**：`voice/voxcpm2.py`、`voice/qwen3_tts.py`，共用基底 `voice/local_clone.py`。
  - 合成透過 `scripts/local_tts_worker.py`，用 TTS venv（`CF_LOCAL_TTS_PYTHON`，預設 `~/.local/share/qwen3-tts/.venv/bin/python`）的子程序執行，以 JSON lines 溝通。
  - repo 的 `.venv` **不 import mlx**。
  - 模型從 HF hub 快取的 snapshot 載入，並設 `HF_HUB_OFFLINE=1`，**不會下載**。
- **一支片只載入一次模型**：
  - worker 在整片配完（`VoiceGenerator.generate` 的 `finally`）收到 `quit` 才結束，記憶體這時才釋放。
  - 本機 provider 的場景依序處理（semaphore 1），每段做完合成 → 轉回檢查 → 重生，才換下一段。
- **頻道設定**：
  - `voice.provider`：`voxcpm2`／`qwen3_tts`／`fish_audio`／…
  - `voice.reference`：`audio` 路徑（可用 `~`）、`text` 逐字原文、`note`。
  - `voice.tempo`：見 §5。
  - `voice.pronunciation`：發音表路徑，預設 `channels/shared/pronunciation.yaml`。
  - schema 會檢查：本機 provider 必須有 reference；Fish／ElevenLabs 必須有 `voice_id_env`；provider 名稱打錯會直接報錯。
  - 路徑都寫在設定裡；程式只有 venv 與 hub 位置的預設值（`CF_*` 可覆寫）。
- **voice 指紋**（runner 的 step identity）包含：provider、model、`ref:<sha256(參考音檔 bytes＋原文)[:12]>`、發音表中這個 provider／頻道實際用到的條目雜湊、tempo。任何一項改變，voice step 就會重跑。
  - 逐段音檔各有自己的 identity（provider／voice／model／tts 文字），沒變的段落直接重用。
- **付費與資源**：
  - 本機 provider 的 voice step **不算付費**（不需要 `--allow-paid`）。
  - 但會拿 render lock（新增 `Step.heavy_if`），不會和 media 渲染、assembly、mascot 同時跑。
- **AI 揭露**：
  - `voice_source` 從 `logs/voice.log` 認出 `voxcpm2`／`qwen3_tts`；worker 和檢查模組的 log 已排除，不會被誤認成 provider。
  - 說明欄照現行邏輯：只要有 TTS 合成紀錄，就算「配音為合成語音」。
  - manual kit 顯示為「VoxCPM2（本機合成語音）」。

## 3. 發音表與自動念錯檢查
### 發音表 `channels/shared/pronunciation.yaml`
- 合併順序：`shared` → `providers.<provider>` → `channels.<code>` → script.json 自己的 `pronunciation_map`。
- 只改送進 TTS 的文字，字幕和畫面照講稿原文。
- 每一條都附 ASR 證據，下表是本輪實測 🟢（VoxCPM2 用妖怪參考聲、Qwen 用下班了參考聲，各跑 seed 1 和 2）：

| provider | 原文 | 改成 | 原念法轉回 | 改後轉回 |
|---|---|---|---|---|
| voxcpm2 | 蘆葦 | 盧偉 | 寥戶／療戶／寥婦 | 蘆葦 |
| voxcpm2 | 掃過 | 嫂過 | 走過 | 掃過 |
| voxcpm2 | 霧 | 務 | 母裏／牡蠣 | 霧裏 |
| voxcpm2 | CoWoS | 扣窩斯 | Cosal Girls／Coors | 扣窩絲／扣沃斯（同音） |
| qwen3_tts | 員工 | 原工 | 雲共／雲供 | 員工（兩個 seed 都對） |
| qwen3_tts | 蘆葦 | 盧偉 | 君空／雲餐 | — |
| qwen3_tts | CoWoS | 扣窩斯 | Coke OS（seed 1） | 扣沃斯／扣國斯 |

- TSMC、HBM：兩個模型原樣都念對（轉回 TSMC／HBM），所以**不改**，只列為 key term。
- 註：寫「T S M C」反而偶爾會轉回「臺極電」。

### 念錯檢查（`voice/speech_check.py`、`voice/checked_synthesis.py`）
- **流程**：
  1. 每段合成後，用 whisper-large-v3-turbo（同一個 worker）轉回，再經 opencc s2t 轉繁體。
  2. 算 CER，並檢查 key terms。
  3. CER > 0.12 或缺 key term，就換 seed 重生，最多 3 次。
  4. 都沒過就保留最好的一版（先比缺幾個 key term，再比 CER），在 `audio/speech_check.json` 標 `warn`，QC 列出 `speech_check` warn。
- **CER 的比法**：拿「講稿原文」比，不是拿 TTS 文字比，因為發音表的替代字都是同音字。比之前先做這些正規化：
  - 統一異體字（臺／裏／爲／着／纔／喫…）；
  - 數字照念法展開（7,722→七千七百二十二；2024 年→二零二四年；60%→百分之六十；×→乘）；
  - 去掉標點。
- **同音字容錯**：
  - key term 的 `heard_as`（例：九尾狐←九尾湖、GAINAX←蓋納克斯）。
  - 發音表的念法（盧偉→蘆葦）會先在轉回文字裡換回原詞。單字條目（務→霧）不換回，以免「任務」被改壞。
- **提早停止**：新 seed 轉回的文字和之前某一次逐字相同，表示錯誤是系統性的（whisper 的譯名寫法或講稿本身），換 seed 沒用，就停止重生。
- **重判**：規則更新後（例如新增 `heard_as`），重用的段落會用已存的轉回文字重新判定，不必重新合成。

### 3.3 各片念錯檢查結果 🟢（數字取自各 run 的 `audio/speech_check.json`）

| 片 | 段數 | 合成次數 | 重生 | CER 平均／中位／最大 | 仍 warn |
|---|---|---|---|---|---|
| CoWoS | 28 | 35 | 7 | 0.048／0.038／0.153 | s22 |
| 7,722 Short | 5 | 6 | 1 | 0.018／0／0.053 | — |
| 九尾狐 | 29 | 52 | 23 | 0.070／0.066／0.174 | s15、s20、s21 |
| cel | 28 | 46 | 18 | 0.042／0.035／0.221 | s20 |

仍是 warn 的段落要人耳聽，判讀如下：

| 段 | whisper 轉回（節錄） | 判讀 |
|---|---|---|
| 九尾狐 s20 | 鳥羽→**修宇**、鳥山石燕→**修山石宴**、宮廷→**胸庭**、御伽→玉家 | **疑似真的念錯**：「鳥」兩處都變成 xiū。候選發音表條目 `鳥: 裊`，但未試，沒有放進表裡 |
| 九尾狐 s21 | 浮世繪→服飾會、題簽→提前、惡狐→鄂湖、國芳→國方 | 幾乎都是同音字，**很可能是假警報** |
| 九尾狐 s15 | 伐紂→罰車、封神演義→風神演繹、妲己→打擊 | 大多同音；「紂→車」、「妲己→打擊」（聲調不同）要聽 |
| cel s20 | Cuckoos' Nest→**咕咕潮**、Hanna-Barbera→漢納巴伯拉 | 英文專名，要聽 Cuckoos' Nest 念得對不對 |
| CoWoS s22 | CoPoS→扣破絲、Intel→英特爾、ABF 基板→ABF 機版 | 大多是同音字或譯名；CoPoS 沒有在發音表裡 |

其他觀察：
- 九尾狐 s02、s04 的「九尾湖」是 whisper 的同音字。已加 `heard_as`，重判後轉為 ok；這兩段第一輪各白重生了 3 次。
- 早期的重生裡，有一部分是同樣的系統性誤差反覆出現。後來加了「轉回逐字相同就停止」，cel 之後的片子省下這些重生。
- 7,722 Short 的 s04「12 吋」轉回「十二七」（CER 0.053，通過門檻），值得順便聽一下。
- **方法限制**：
  - 字元 CER 會把同音字算成錯（例如九尾狐 s21）。拼音層級的比對才是真正的「念錯率」，但要裝 pypinyin，這台機器只有 gpt-sovits 的 venv 有。
  - 裝進 repo 或 TTS venv 都會動到 worktree 以外的環境，所以沒做 🟡。

## 4. 晶片貓女聲（決策 b25068faf5a4）
- **設計**：Qwen3-TTS 12Hz 1.7B VoiceDesign（bf16）。
  - instruct：「女性的聲音，三十歲左右，中音域、音色溫暖飽滿，不尖細也不甜膩，台灣國語口音，咬字清楚，語氣自信從容，帶一點輕鬆幽默和俏皮，像科技頻道的女主持人在跟朋友聊天解說，語速中等。」
  - 原文沿用試驗的 chipcat 參考句。
  - 跑 6 個 take（seed 2000–2005）。
- **6 個 take** 🟢：

| take | 中位基頻 | whisper CER | ECAPA 對 cel-take0 |
|---|---|---|---|
| 0 | 210 Hz | 0.00 | 0.559 |
| 1 | 202 Hz | 0.021 | 0.488 |
| 2 | 224 Hz | 0.010 | 0.635 |
| 3 | 197 Hz | 0.00 | 0.444 |
| **4（選用）** | **243 Hz** | 0.010 | **0.440** |
| 5 | 254 Hz | 0.010 | 0.723 |

- 對照組：cel 自己的 take1、take2 對 take0，相似度是 0.816 和 0.841。
- 選 take4 的理由：和 cel 的相似度最低（與 take3 幾乎相同）；基頻 243 Hz，比 take3 的 197 Hz 離性別邊界更遠，所以「性別正確」更確定。
- 存放位置：`~/.local/share/content-farm-voices/chipcat-female-ref.wav`，原文與出處在同名的 `.txt`。
- 試聽：VoxCPM2 複製 3 句，放在 `/Users/lileon/Downloads/voice-trial/chipcat-female/`（附 README.md、similarity.json、trial.json）。
  - 三句對自己參考聲的相似度 0.80–0.85，對 cel 參考聲 0.50–0.53 🟢。
- HN「新聞播報女聲」還沒做，所以沒有比對。做好時要用 `sim.py` 的同樣方法（ECAPA）比一次 🔴。
- 原本派工時的 Downloads 參考聲（`ref-<channel>.wav`）**讀不到**（EPERM，原文：`EPERM: operation not permitted, open '/Users/lileon/Downloads/voice-trial/local/README.md'`）。
  - 所以 yokai、cel、offwork 的 take 是用試驗腳本 `trial-scripts/common.py` 的 `REF_PICK`（yokai-take1、offwork-take34、cel-take0）對出來的。這組 take 也是 clone.py 試聽句所用的參考 🟡（沒辦法和 Downloads 的檔案做位元比對）。
  - 寫入 Downloads 可以，讀不行。

## 5. tempo（決策 944769e1fc01）
- 做法：
  - 新增 `voice.tempo`，以 ffmpeg `atempo` 調速，音高不變。
  - tempo ≠ 1.0 時，原始合成版本放在 `audio/raw/scene_NNN.mp3`，`audio/scene_NNN.mp3` 由它調速產生，`audio/tempo.json` 記錄每段實際套用的 tempo。
  - 改 tempo **不會重新合成**；改回 1.0 時，原檔會搬回原位。
- 九尾狐、cel、CoWoS、Short 調速時都**沒有重新合成**。
  - 以九尾狐和 cel 驗證：調速那一輪的 voice.log 有 0 行「VoxCPM2 TTS」，「Re-timed」各 29／28 行，和張數相符 🟢。
  - voice step 耗時約 14–16 s（主要是重做字幕對齊）。

### 片長與語速 🟢

| 片 | Fish 舊版 | VoxCPM2 原速 | tempo | 加速後 | 字/秒（TTS 文字字數／秒） | QC 片長 |
|---|---|---|---|---|---|---|
| CoWoS（晶片貓女聲） | 492.2 s | 678.1 s | 1.15 | **589.4 s（9:49）** | 4.53（2,672 字） | ok |
| 7,722 Short（晶片貓女聲） | 24.3 s | 32.6 s | 1.15 | **28.4 s** | 3.95（112 字） | ok（Short 上限 60 s） |
| 九尾狐 | 518.9 s | 770.2 s | 1.20 | **641.6 s（10:42）** | 3.68（2,358 字） | **warn：超過 600 s** |
| cel | 482.6 s | 644.5 s | 1.12 | **575.2 s（9:35）** | 4.47（2,573 字） | ok，≥ 8:00 |

- 秒數是旁白音檔合計，成片長度和這個差 ±0.1 s（見 QC）。
- 九尾狐即使加速 1.20，仍然超過 42 s。
  - 原因是參考聲本身就慢：試驗時的 instruct 是「語速很慢、常停頓」。實測原速版本約 19% 是 0.4 s 以上的停頓，其中超過 1 s 的停頓只占 26 s，其餘是語速慢。
  - 要壓到 600 s 以內，需要 tempo ≈ 1.29，或換一個比較快的參考 take。這要 Leon 決定，我沒有改。

## 6. 資源與耗時
- **記憶體**：VoxCPM2-8bit 單段合成時，mlx 峰值約 5.7 GB（smoke test）。任務給的總用量約 21.7 GB 是系統層級數字，我沒有重測 🔴。
  - 閘門門檻：`memory_pressure -Q` 的可用比例 ≥ 25% 才載入。
  - 本輪實際看到的可用比例：載入前 71–87%，合成中 52%。
- **閘門實際觸發** 🟢：九尾狐 voice 剛開始時，另一個 session 在跑 `mflux-generate-flux2-edit`，閘門等了 60 s 才放行（voice.log：`Resource gate waiting: busy=[94826] free=71%` → `Resource gate open after 60s`）。
- **放行之後的干擾**：九尾狐 s04 有一段跑了 1,025.8 s（平常 35–55 s），時間點和另一個 session 的 mflux 重疊（推測是共用 GPU，🟡，沒有直接證據）。
  - 修正（commit `bfba017`）：每段合成前會再檢查一次 `pgrep -f 'mlx_video|mflux|ffmpeg'`。有其他程序就暫停（模型保持載入），等它們結束；只看程序，不看記憶體，因為我們自己的模型已經占了記憶體。
  - 同一個 commit 也改成場景依序處理，並修掉並發時重複送出 load 的問題。
- **一次只有一個模型**：worker 持有機器層級的 `~/.cache/content-farm/local_tts.lock`。voice step 也拿 render lock，所以不會和其他 run 的 media、assembly、mascot 同時跑。
- **耗時**（voice step，runner 記錄）🟢：

| 片 | 第一輪合成 | 調速／重判 |
|---|---|---|
| 九尾狐 | 2,486.9 s（含 60 s 閘門等待與 s04 的 1,026 s 干擾） | 16.2 s |
| cel | 1,798.1 s | 14.0 s |
| CoWoS | 1,989.8 s | 15.2 s |
| Short | 79.4 s | 3.7 s |

- 平均每段約 50–70 s，含 ASR 與重生。
- 晶片貓女聲 VoiceDesign 6 個 take：每個 16–21 s 生成。

## 7. 產物與閘門
- **preview**（manual-kit；gate_final 都沒有代核，所以標示「預覽版」）：
  - `output/cowos-chipcat/upload/manual/preview.html`
  - `output/chipcat-7722-launch/upload/manual/preview.html`
  - `output/yokai-kyubi-launch/upload/manual/preview.html`
  - `output/cel-ep1/upload/manual/preview.html`
  - 都在本 worktree 底下，gitignored。
- 配音標示是「VoxCPM2（本機合成語音）」。說明欄的 AI 揭露照現行邏輯：有 TTS 合成紀錄就寫「配音為合成語音」🟢（四份 preview 都用 grep 確認過有「VoxCPM2（本機合成語音）」）。
- 四片 QC：
  - CoWoS 0 error／1 warn（speech_check），角色在 28/28 張出現。
  - Short 0／0。
  - 九尾狐 0／2（speech_check、片長）。
  - cel 0／1（speech_check）。
- CoWoS 有一筆舊的 gate_final 核可（2026-10-15，「validation run only」，比 launch-fixes 還早），這次因為檔案改變已經失效，**需要重新審**。
- **我核可的閘門**（身分 `claude-channel-voices`，理由寫在各 run 的 `review/*.decision.json`）：
  - **gate_media ×3**：
    - 九尾狐、cel：`media_report` 和 launch-fixes 已核可版逐欄位比對，素材、motion、授權都相同，只差秒數。cel 的 s01 是同一支 Pexels 片段，從 slow 改成 loop。
    - CoWoS：s20 因為片段變長，自動換成另一支 Pexels 片段（32636373，夕陽工地吊車剪影）。我抽 3 格看過，沒有可讀文字或品牌。
  - **Short gate_script ×2**：
    - 第一次：`long_run_dir` 改指本 worktree。
    - 第二次：voice step 把實測秒數寫回 script.json，閘門指紋因此改變。
    - 兩次的旁白逐字都沒變（用 `--word-diff` 確認）。
- **gate_final ×4：等 Leon。** 指令：`python scripts/produce.py approve --run-dir output/<run> --gate final`（在本 worktree 執行）。
- **第一輪 media 的退化**（已修正）：
  - 第一次 media 沒帶 `CF_MLX_VIDEO_HOME`，九尾狐 s09、s13、s24a 從 parallax 快取退回 Ken Burns。我在核可前比對時發現，停掉之後補上 env（`/Users/lileon/.local/share/mlx-video`，和 REPORT-ai-motion 的做法相同）重跑，現在三張都用回快取。
  - 這個 env 仍然**沒有**寫進主 checkout 的 `.env`。建議加進去，不然下次也會發生。

## 8. 程式改動與測試
| commit | 內容 |
|---|---|
| `bc20c25` | VoxCPM2／Qwen3-TTS provider、worker、資源閘門、模型鎖、發音表、念錯檢查、QC `speech_check`、頻道 `voice.provider`／`reference`、指紋 |
| `bfba017` | 本機場景依序處理、只載入一次、場景之間暫停讓路 |
| `0c7e32b` | 九尾狐 `heard_as`、重判已存的轉回文字 |
| `1578499` | 晶片貓改 VoxCPM2＋女聲參考聲；runner 測試改用明確的 Fish 版晶片貓；參考檔不存在時不影響規劃 |
| `1e6557a` | 轉回逐字相同就停止重生；GAINAX／Netflix／MAPPA 的 `heard_as` |
| `092a73c` | `voice.tempo`（`audio/raw/` 存原始合成、atempo 產生場景檔、`tempo.json`） |
| `2eb1e91`、`fba42e5` | 晶片貓 tempo 1.15 與對應測試 |

- **新增測試**：`test_voice_speech_check.py` 27 個案例（含參數化）、`test_voice_local_providers.py` 19 支、`test_voice_tempo.py` 3 支（含真 ffmpeg 的往返測試）。
  - 另外改了：`test_production_runner.py`（Fish 版晶片貓）、`test_production_channels.py`（本機 provider 沒有 voice id）。
- **pytest 全套**：1 failed／1215 passed／1 skipped 🟢。那 1 支失敗是基準就失敗的 `test_multi_provider…returns_first_provider_results`。
- 偵測器的對照組：
  - 試驗已知的錯字（「母裏…走過寥婦」）CER 0.267，能抓到。
  - 「九尾湖」在加 `heard_as` 前會被抓、加之後放行（有測試）。
  - 閘門的等待與逾時都有測試。

## 9. 待 Leon 決定
1. gate_final ×4（看 preview）。
2. 九尾狐 10:42 超過上限：tempo 加到 ≈1.29、換一個比較快的參考 take，或放寬 `target_seconds`。
3. 九尾狐 s20 的「鳥」（以及 §3.3 表中其他 warn 段落）要聽。若確定念錯，加發音表條目，再對該段強制重生（`--force voice` 只會重做 identity 改變的段落）。
4. 念錯檢查要不要升級成拼音層級：要在 repo 或 TTS venv 裝 pypinyin。
5. `CF_MLX_VIDEO_HOME` 要不要寫進主 `.env`。
6. 觀察：scripted Short 的 voice step 會把秒數寫回 script.json，而 script.json 在 gate_script 的指紋裡，所以每次重配都要重新核可 gate_script。這是既有的設計問題，本輪沒有改 🟡。

## 10. 清理與副作用
- **worktree 外寫入**（都是任務或決策要求的）：
  - `~/.local/share/content-farm-voices/chipcat-female-ref.wav` 和 `.txt`。
  - `~/Downloads/voice-trial/chipcat-female/`：3 個 wav、README.md、trial.json、similarity.json。
  - `~/.cache/content-farm/local_tts.lock`：鎖檔，空檔。
- **TTS venv、模型**：沒有安裝或下載任何東西。
- **job tmp**（`~/.claude/jobs/59171c43/tmp/`）會隨 job 清除：
  - smoke 與發音試驗的 wav、VoiceDesign 的 6 個 take、佇列腳本。
- **`output/` 下的 4 個 run-dir**：gitignored 的交付物。另有 `audio/raw/`，是調速前的原始合成。
- **背景程序**：我自己停掉兩次 runner，都停在 media 或 render 之前或過程中，之後都已重跑完成。沒有殘留程序（`ps` 確認過）。
- **外部存取**：Fish 0 次；CoWoS s20 的新片段在 media_report 記為 `(cache)`，表示檔案來自本機快取；media 步驟這次有沒有打 Pexels 搜尋 API，沒有查證 🔴。沒有開瀏覽器、沒有上傳、沒有 push。
