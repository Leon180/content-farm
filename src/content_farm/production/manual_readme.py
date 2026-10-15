"""``upload/manual/README.md``: the YouTube Studio upload checklist, in Studio's order."""

from __future__ import annotations

from pathlib import Path

from content_farm.production.manual_kit import (
    CATEGORY_NAMES,
    TAGS_MAX_CHARS,
    TITLE_MAX,
    KitInfo,
    human_duration,
    human_size,
)

MACHINE_VOICE_BANNER = "> ⚠️ **暫用機器聲（macOS say），待換 Fish Audio 後重出。這一版不要公開。**\n"


def _status_lines(info: KitInfo) -> list[str]:
    qc = ("未跑" if info.qc_errors is None
          else f"{info.qc_errors} error / {info.qc_warnings} warn")
    meta_src = ("`upload/youtube_meta.json`（package 步驟）" if info.meta_from_package
                else "manual-kit 臨時生成（成片閘門尚未核可，package 未跑）")
    return [
        f"- 目標頻道：**{info.channel_name}**（`{info.channel_code}`，{info.channel_line}）",
        f"- 影片檔：`{info.video_abs}`",
        f"- 片長 {human_duration(info.duration_seconds)}・檔案 {human_size(info.size_bytes)}",
        f"- 配音：{'macOS say（暫用）' if info.machine_voice else 'Fish Audio'}・QC：{qc}",
        f"- metadata 來源：{meta_src}",
        "- 本機預覽：`preview.html`（上傳前先用瀏覽器開一次）",
    ]


def _warnings(info: KitInfo) -> list[str]:
    meta = info.meta
    notes = []
    if len(meta["title"]) > TITLE_MAX:
        notes.append(f"- 標題 {len(meta['title'])} 字，超過 {TITLE_MAX}，要先縮短。")
    tags_len = len(",".join(meta.get("tags") or []))
    if tags_len > TAGS_MAX_CHARS:
        notes.append(f"- 標籤合計 {tags_len} 字元，超過 {TAGS_MAX_CHARS}，要刪幾個。")
    if info.qc_errors:
        notes.append(f"- QC 有 {info.qc_errors} 個 error，見 `qc/qc_report.json`。")
    return notes


def _visibility(meta: dict) -> str:
    if meta.get("publish_at"):
        return f"「排定時間」：{meta['publish_at']}（先設私人，排程到點自動公開）"
    return f"「{ {'private': '私人', 'unlisted': '不公開', 'public': '公開'}.get(meta.get('privacy_status'), '私人') }」"


def _synthetic(meta: dict, machine_voice: bool) -> str:
    if meta.get("contains_synthetic_media"):
        voice = "macOS 合成語音" if machine_voice else "Fish Audio 合成語音"
        return (f"勾 **「是」**。理由：旁白是{voice}，頻道設定 `ai_disclosure: true`，"
                "與 youtube_meta.json 的 `contains_synthetic_media: true` 一致。"
                "本片畫面是投影片與 stock，沒有冒充真人或真實事件；"
                "YouTube 是否要求這類內容一定要揭露，未對照官方條文（🟡），目前採保守做法。")
    return "勾 **「否」**（頻道設定 `ai_disclosure: false`）。"


def build_readme(info: KitInfo, kit_abs: Path, has_subs: bool) -> str:
    meta = info.meta
    category = CATEGORY_NAMES.get(str(meta.get("category_id")), str(meta.get("category_id")))
    chapters = meta.get("chapters") or []
    lines = [
        *([MACHINE_VOICE_BANNER] if info.machine_voice else []),
        f"# 手動上傳包：{meta['title']}",
        "",
        *_status_lines(info),
        "",
        *(["## 先處理", *_warnings(info), ""] if _warnings(info) else []),
        "## YouTube Studio 步驟",
        "",
        f"1. 右上角切換到頻道 **{info.channel_name}**（不是其他三個品牌頻道）。",
        "2. 「建立」→「上傳影片」，選檔：",
        f"   `{info.video_abs}`",
        "3. **詳細資訊**",
        f"   - 標題：貼 `title.txt`（{len(meta['title'])} 字）",
        "   - 說明：貼 `description.txt`（含章節、參考資料、素材授權、AI 揭露）",
        f"   - 縮圖：上傳 `thumbnail.png`（1280×720）。{info.thumbnail_note}",
        f"   - 播放清單：「{info.channel_line}」（沒有就新建）",
        "   - 觀眾：**「否，這不是為兒童打造的內容」**",
        "   - 展開「顯示更多」：",
        f"     - 變造或合成內容：{_synthetic(meta, info.machine_voice)}",
        "     - 標籤：貼 `tags.txt`",
        "     - 語言與字幕認證：影片語言 **中文（台灣）**",
        f"     - 類別：**{category}**",
        "4. **影片元素**",
        ("   - 字幕：上傳 `subtitles.srt`，語言 **中文（台灣）**。"
         "注意畫面已燒入字幕，CC 預設關閉，觀眾自行開啟才會疊兩層。" if has_subs
         else "   - 字幕：這支片沒有 srt。"),
        "   - 片尾畫面：最後 20 秒放「訂閱」＋「最新上傳的影片」。",
        "   - 資訊卡：在下方章節的轉折點各放一張，指向本頻道相關影片或播放清單。",
        "5. **檢查**：等版權與廣告適合度檢查跑完，有 Content ID 聲明就先停，回報 orchestrator。",
        f"6. **瀏覽權限**：{_visibility(meta)}",
        "",
        "## 章節（已在說明欄內）",
        "",
        *([f"- {c['timestamp']} {c['title']}" for c in chapters] or ["- （無）"]),
        "",
        "## 檔案",
        "",
        f"`{kit_abs}/`：title.txt、description.txt、tags.txt、thumbnail.png、"
        + ("subtitles.srt、subtitles.vtt、" if has_subs else "") + "preview.html",
        "",
    ]
    return "\n".join(lines)
