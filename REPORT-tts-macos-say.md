# REPORT — 免費本機 TTS provider `macos_say`

## TL;DR
- 新增 `CF_TTS_PROVIDER=macos_say`（macOS `say` → aiff → ffmpeg → mp3），免費、不需 API key，**只供開發與測試，不可用於發布**。🟢
- pytest：733 passed、1 failed，失敗的就是基準既有的 `test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results`，沒有新增失敗；新測試 21 個（含 1 個真的呼叫 `say` 的整合測試，本機有跑、沒被 skip）。🟢
- 實跑 explainer-tsmc 整條管線（deck_to_script → render_slides → voice → slides_to_visual → assembly_timeline）：`draft.mp4` 長 124.06 s，1920×1080，blackdetect 0 段（對照組有偵測到），字幕 35 段。🟢
- 分支 `feat/tts-macos-say` 是在 `eeff1ab` 上多 3 個 commit；`feat/explainer-mvp` 目前仍停在 `eeff1ab`，可以 fast-forward 合併。🟢（以 2026-10-14 當下的狀態為準）

## 改了什麼

| 檔案 | 內容 |
|---|---|
| `src/content_farm/voice/macos_say.py`（新） | `MacSayProvider`，實作 `generate_speech`／`generate_speech_with_context`（後者忽略前後文）。用 `asyncio.create_subprocess_exec` 呼叫外部程式，不經 shell；文字放在 `--` 之後，作為單一 argv 元素傳入，所以開頭是 `-` 的文字也不會被當成選項。暫存的 aiff 放在 `tempfile.TemporaryDirectory`。ffmpeg 參數：`-codec:a libmp3lame -b:a 128k` |
| 同上：預檢 | 第一次合成前（有 lock，結果會快取）依序檢查：`sys.platform == "darwin"`、`shutil.which(say)`、`shutil.which(ffmpeg_path)`，再跑 `say -v ?` 確認指定的語音存在。每一種錯誤都會拋 `MacSayError`，訊息說明缺什麼、怎麼補。**語音存在性一定要自己檢查**：實測 `say -v "Nope Voice" -o x.aiff hi` 會回 exit 0，然後默默改用預設語音（產出 0.42 s 的音檔） |
| 同上：其他錯誤 | 空白文字拋 `ValueError`；`rate <= 0` 拋 `ValueError`；子程序非 0 結束時，錯誤訊息附上 stderr；無法啟動（`OSError`）也會轉成 `MacSayError` |
| `voice/factory.py` | 新增 `"macos_say"` 分支，不需要 API key；未知 provider 的錯誤訊息補列 `macos_say` |
| `config.py` | `macos_say_voice`（預設 `Flo (Chinese (Taiwan))`）、`macos_say_rate: int \| None`（`gt=0`）；`tts_provider` 註解註明「免費，只供開發測試，不可發布」 |
| `.env.example` | `CF_TTS_PROVIDER` 的選項加上 `macos_say`；新增 `CF_MACOS_SAY_VOICE`（含括號，所以加了引號）。`CF_MACOS_SAY_RATE` 先註解掉，因為空字串對 `int \| None` 會驗證失敗。已實測用 `Settings(_env_file='.env.example')` 讀出 `'Flo (Chinese (Taiwan))'`、`None` |
| `tests/unit/test_macos_say.py`（新） | 21 個測試，見下 |
| `.claude/skills/voice/SKILL.md` | 新增「Free dry run」段落：環境變數、免費跑完整條 explainer 的指令、發布前要改用 Fish Audio 重跑 voice，並用 `slides_to_visual.py --replace` 重排 |
| `REPORT-explainer-mvp.md` | 在「端到端試跑」段落補上免費試跑的方式 |

## 測試結果 🟢

```
PYTHONPATH=<worktree>/src .venv/bin/python -m pytest -q
1 failed, 733 passed, 1 warning in 12.32s
FAILED tests/unit/test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results[asyncio]
```

已確認 import 的是 worktree 的程式碼：`content_farm.voice.macos_say.__file__` 指向 `.../worktrees/cf-tts-say/src/...`。

`test_macos_say.py` 的涵蓋範圍：
- 解析 `say -v ?`：名稱可含空白和巢狀括號（`Flo (Chinese (Taiwan))`），也涵蓋 `ar_001` 這種 locale；垃圾行會被忽略。
- argv：文字含 `$(rm -rf ~);` 時仍是 `--` 之後的單一參數；`-o` 指向 `.aiff`，ffmpeg 的 `-i` 就是同一個檔；`CF_FFMPEG_PATH` 有被使用；合成完暫存目錄已刪除；`-r` 只有在設定時才出現；`voice_id` 會覆寫語音；語音清單只查一次。
- 錯誤路徑：非 macOS、找不到 `say`、找不到 ffmpeg、語音不存在（而且不會進到合成步驟）、`say` 非 0 結束、ffmpeg 非 0 結束、執行檔無法啟動、空白文字、`rate=0`。
- factory：預設值、讀取 voice／rate／ffmpeg 設定、不需要 API key、`CF_MACOS_SAY_RATE=0` 會被 Settings 拒絕。
- 整合測試 `test_real_say_produces_mp3`：真的呼叫 `say` 和 ffmpeg，再用 ffprobe 確認輸出是 mp3、長度在 0.3–10 s 之間。條件是 macOS、有 `say`、有 ffmpeg、而且預設語音已安裝，否則 skipif。本機有實際執行，結果是 27 passed、0 skipped（含既有的 `test_voice_factory.py`）。

## 試跑結果 🟢

Run dir：`output/explainer-tsmc-say/`（在 gitignore 裡，沒有 commit）。來源是 `docs/examples/explainer-tsmc/deck.json` 的複本。

環境：`CF_TTS_PROVIDER=macos_say`、`CF_ANTHROPIC_API_KEY=dummy-unused`、Fish／ElevenLabs key 留空，worktree 裡沒有 `.env`。這樣如果誤觸付費 API，會直接失敗，不會被扣款。

| 步驟 | 結果 |
|---|---|
| deck_to_script | 6 scenes／3 chapters；3 條預期中的 lint 警告（張數、片長、`draft_data`） |
| render_slides | 6 張，2.1 s，contact sheet 有產出 |
| voice | 6 段 mp3（scene_001 長 15.39 s），合併成 `full.mp3` 124.06 s；whisper 對齊後 35 段字幕、共 123.8 s；`script.json` 的時長已用實測值回寫 |
| slides_to_visual | `Placed 6 slides from audio durations; ends at 01:46.790~02:03.749` |
| assembly_timeline | `assembly/draft.mp4`，h264 1920×1080 30 fps + aac，**124.061 s** |
| blackdetect（`d=0.1:pix_th=0.10`） | **0 段**。對照組：用相同參數跑 1 s 的 lavfi 黑畫面，會輸出 `black_start:0 black_end:0.96`，證明偵測器有效 |

`.srt` 的 `-->` 行數是 35 行，和 log 對得上。

唯一的外部網路請求是 faster-whisper 到 huggingface 查模型版本（`GET .../faster-whisper-base/revision/main` 回 200），免費，而且是既有行為。沒有呼叫 Fish Audio、ElevenLabs、Claude API。

沒有做的：沒有用肉眼看 `draft.mp4` 的字幕排版和語音品質（🔴）。

## 怎麼併回 `feat/explainer-mvp`

```
eeff1ab (feat/explainer-mvp)
  └─ c156b63 feat(voice): add free macos_say TTS provider ...
  └─ 5f31a6e docs(voice): document free CF_TTS_PROVIDER=macos_say dry run ...
  └─ <本報告的 commit>
```

2026-10-14 記錄時，`git branch -v` 顯示 `feat/explainer-mvp` 指向 `eeff1ab`，也就是本分支的 base，所以可以 fast-forward：

```bash
# 在 feat/explainer-mvp 所在的 worktree（.claude/worktrees/cf-explainer-mvp）
git merge --ff-only feat/tts-macos-say
```

如果在那之前 `feat/explainer-mvp` 又有新的 commit，`--ff-only` 會失敗；這時改用 `git rebase feat/explainer-mvp`（在本分支上做），或做一般 merge。改動的檔案集中在 voice、config、`.env.example`、SKILL 和兩份 REPORT，可能衝突的只有 `config.py` 的 Voice 區塊和 `REPORT-explainer-mvp.md` 的端到端段落。

## 清理與副作用
- 新的本機分支：`feat/tts-macos-say`（交付物，保留）。worktree 原本所在的分支 `worktree-cf-tts-say` 沒有動。
- `output/explainer-tsmc-say/`：試跑產物，在 gitignore 裡，保留給人工檢查；不需要時可以刪。
- `$CLAUDE_JOB_DIR/tmp/t.aiff`、`t2.aiff`：測 `say` 行為用的檔案，job 刪除時會一起清掉。
- 整合測試的輸出放在 pytest 的 `tmp_path`。
- 沒有 push；沒有動 main、`chore/wip-baseline-2026-10`、`feat/explainer-mvp`，也沒有動那個 worktree；沒有 commit `.env`、`output/`、`data/curriculum_map/`。
