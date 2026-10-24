"""The step list each pipeline runs, in order.

Kinds:
- ``agent``: produced by a Claude skill or a person (``/article``, ``/deck``);
  the runner only checks the outputs exist and runs ``verify``.
- ``cmd``: a script in ``scripts/``; skipped when it already ran on the same
  inputs (fingerprint) and its outputs are still there.
- ``internal``: Python in this package (policy, QC, upload metadata).
- ``gate``: stops until ``produce.py approve`` records a decision whose
  fingerprint still matches the reviewed artifacts.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from content_farm.production.channels import LOCAL_TTS_PROVIDERS, Channel, Gate, Pipeline
from content_farm.production.shorts_cut import SOURCE_FILE as SHORT_SOURCE_FILE
from content_farm.production.shorts_cut import is_short_cut
from content_farm.production.voice_choice import VoiceChoice, choose_voice, env_file_defaults

REPO_ROOT = Path(__file__).resolve().parents[3]
EXPLAINER_SUBTITLE_MAX = "14"  # 64 px subtitles (v3): ≤ 18 chars ≈ 1170 px clears the mascot column
# production/news file names (kept literal here: news imports steps-adjacent modules, not the reverse)
NEWS_ITEM_FILE = "news_short.json"
NEWS_SCRIPT_FILE = "news_script.json"
NEWS_WEEKLY_FILE = "news_weekly.json"
FABLE_FILE = "fable.json"      # production/fable/model.py (same literal; model imports nothing from here)


@dataclass(frozen=True)
class RunOptions:
    mock_voice: bool = False      # macOS `say` instead of paid TTS
    allow_paid: bool = False      # required for paid TTS
    no_stock: bool = False
    env_file: Path = REPO_ROOT / ".env"
    mascot_workers: int = 3       # tiled GPU capture: 3 lanes drew CoWoS v3 (15.3k frames) in 113 s
    python: str = sys.executable
    panels: bool = True           # gates opened by agent review panels (review_panels.yaml)
    auto_agents: bool = False     # run producer agents (claude -p) for agent steps / rework
    competitors: Path | None = None   # homepage feeds for the title & thumbnail panel
    review_tier: str = ""         # "opus:high" lifts every reviewer (comparison runs only)
    budget_usd: float | None = None   # cloud-lane allowance for this video (review.budget); None = file / env / config
    review_client: Callable | None = None   # tests inject a fake; None = claude -p subprocesses


@dataclass(frozen=True)
class Context:
    channel: Channel
    run_dir: Path
    options: RunOptions


@dataclass(frozen=True)
class Command:
    argv: tuple[str, ...]
    env: dict[str, str] = field(default_factory=dict)

    def full_env(self) -> dict[str, str]:
        src = str(REPO_ROOT / "src")
        path = os.environ.get("PYTHONPATH", "")
        return {**os.environ, "PYTHONPATH": f"{src}:{path}" if path else src, **self.env}


@dataclass(frozen=True)
class Step:
    name: str
    kind: str                                   # agent | cmd | internal | gate
    title: str                                  # zh-TW, shown in status and review pages
    outputs: tuple[str, ...] = ()               # globs; all must match for "done"
    inputs: tuple[str, ...] = ()                # globs; change => re-run
    command: Callable[[Context], Command] | None = None
    verify: Callable[[Context], Command] | None = None
    gate: Gate | None = None
    artifacts: tuple[str, ...] = ()             # what the reviewer looks at (gate fingerprint)
    hint: str = ""                              # what to do when an agent step has no output
    paid: Callable[[Context], bool] = lambda ctx: False
    heavy: bool = False                         # takes the machine-wide render lock
    heavy_if: Callable[[Context], bool] = lambda ctx: False   # heavy only for some settings (local TTS)
    applies: Callable[[Channel], bool] = lambda channel: True
    # Settings that change the output without touching any input file (e.g. the TTS
    # voice); folded into the fingerprint and logged when the step runs.
    identity: Callable[[Context], str] | None = None
    # Cheap check before queueing for the machine: False = nothing to do (every output is already there), so the step
    # is marked done without taking a slot. A step that waited 17 minutes behind another video's GPU job to print
    # "nothing to generate" is what this prevents (yokai-kyubi-v3 2026-10-23). An error counts as "has work".
    has_work: Callable[[Context], bool] | None = None


def _py(ctx: Context, script: str, *args: str, env: dict[str, str] | None = None) -> Command:
    return Command((ctx.options.python, str(REPO_ROOT / "scripts" / script), *args), env or {})


def _illustrate_pending(ctx: Context) -> bool:
    """Is any ai_image slide still missing its image (the same test ``scripts/illustrate.py`` makes)?"""
    from content_farm.explainer.deck import load_deck
    from content_farm.explainer.illustrate import Settings, missing_images

    deck_path = ctx.run_dir / "deck.json"
    if not deck_path.is_file():
        return True
    config = ctx.channel.ai_illustration
    try:
        deck = load_deck(deck_path)
        return bool(missing_images(deck, ctx.run_dir, Settings(config.model, config.style_prefix, config.seed,
                                                              config.width, config.height)))
    except (OSError, ValueError, KeyError):
        return True


def _run_dir(ctx: Context) -> str:
    return str(ctx.run_dir)


def _host_args(ctx: Context) -> tuple[str, ...]:
    """The mascot step draws the vector rig unless the channel uses a PNGtuber pack."""
    mascot = ctx.channel.mascot
    if mascot.host != "pngtuber":
        return ()
    profile = ("--motion-profile", mascot.motion_profile) if mascot.motion_profile != "legacy" else ()
    return ("--pngtuber", mascot.ref, *profile)


def voice_choice(ctx: Context) -> VoiceChoice:
    return choose_voice(ctx.channel, ctx.options.env_file, mock=ctx.options.mock_voice)


PAID_TTS = ("fish_audio", "elevenlabs")


def _voice_paid(ctx: Context) -> bool:
    return not ctx.options.mock_voice and ctx.channel.voice.provider in PAID_TTS


def _voice_local(ctx: Context) -> bool:
    """A local TTS model needs the machine to itself: run it under the render lock."""
    return not ctx.options.mock_voice and ctx.channel.voice.provider in LOCAL_TTS_PROVIDERS


VOICE_SPOKEN_FILE = "audio/voice_spoken.json"   # the spoken key the last successful voice run voiced


def voice_spoken_key(ctx: Context) -> str:
    """What the voice step depends on, spoken words only (orchestrator 2026-10-19): every slide's narration
    and sentence ids, the scene narration, the deck's and the pronunciation table's mappings and the voice
    itself. Screen edits — titles, bullets, an AI image's prompt — leave it unchanged, so they never re-voice
    (deck.json / script.json as a whole also carry those)."""
    import hashlib
    import json

    def load(name: str) -> dict:
        path = ctx.run_dir / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    deck, script = load("deck.json"), load("script.json")
    slides = [[s.get("id"), s.get("narration"), s.get("sentence_ids")]
              for sec in deck.get("sections", []) for s in sec.get("slides", [])]
    choice = voice_choice(ctx)
    pron = Path(choice.env().get("CF_PRONUNCIATION_FILE", "") or "/nonexistent")
    view = {"slides": slides, "deck_pron": deck.get("pronunciation_map"),
            "scenes": [sc.get("narration") for sc in script.get("scenes", [])],
            "script_pron": script.get("pronunciation_map"),
            "pron_table": hashlib.sha256(pron.read_bytes()).hexdigest() if pron.is_file() else "",
            "voice": choice.describe()}
    digest = hashlib.sha256(json.dumps(view, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"{choice.describe()} spoken={digest}"


def voice_nothing_to_synthesize(ctx: Context) -> bool:
    """The last successful voice run voiced exactly these words with this voice: the step will only
    re-time and re-align (no TTS model loads), so it must not queue for the model's memory."""
    import json

    path = ctx.run_dir / VOICE_SPOKEN_FILE
    if not path.is_file():
        return False
    return json.loads(path.read_text(encoding="utf-8")).get("key") == voice_spoken_key(ctx)


def _voice_env(ctx: Context) -> dict[str, str]:
    env = {"CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE": EXPLAINER_SUBTITLE_MAX}
    if ctx.options.mock_voice:
        env["CF_TTS_PROVIDER"] = "macos_say"
        env.setdefault("CF_ANTHROPIC_API_KEY", os.environ.get("CF_ANTHROPIC_API_KEY", "dummy-unused"))
        return env
    choice = voice_choice(ctx)
    return {**env_file_defaults(ctx.options.env_file), **env, **choice.env()}


def _media_args(ctx: Context) -> tuple[str, ...]:
    args = ["--run-dir", _run_dir(ctx), "--brand", ctx.channel.brand, "--replace",
            "--require-measured", "--env-file", str(ctx.options.env_file)]
    if ctx.options.no_stock or not (ctx.channel.media.stock or ctx.channel.media.stock_video):
        args.append("--no-stock")
    return tuple(args)


THUMB_SPECS = ("titles.json", "thumbnail.json", "thumbnail_variants.json")


def _gate_enabled(gate: Gate) -> Callable[[Channel], bool]:
    return lambda channel: channel.gate_enabled(gate)


EXPLAINER_STEPS: tuple[Step, ...] = (
    Step("topic", "agent", "選題候選（8–12 題）", outputs=("topics/candidates.json",),
         hint="選題 agent 寫 topics/candidates.json（produce.py run --auto-agents 會自動呼叫）"),
    Step("gate_topic", "gate", "選題評審", gate=Gate.TOPIC, artifacts=("topics/candidates.json",),
         applies=_gate_enabled(Gate.TOPIC)),
    Step("article", "agent", "研究與文章", outputs=("article.md", "sources.json"),
         verify=lambda c: _py(c, "check_article.py", "--run-dir", _run_dir(c)),
         hint="在 run-dir 跑 /article <題目>（Claude skill，會上網查資料）"),
    Step("gate_article", "gate", "文章審稿", gate=Gate.ARTICLE,
         artifacts=("article.md", "sources.json"), applies=_gate_enabled(Gate.ARTICLE)),
    Step("deck", "agent", "簡報大綱與講稿", outputs=("deck.json",),
         verify=lambda c: _py(c, "deck_to_script.py", "--run-dir", _run_dir(c), "--strict"),
         hint="跑 /deck-outline 再 /deck（會產生 deck.json）"),
    Step("policy", "internal", "頻道素材政策與頻道規則（開場、片尾、觀點段、角色）", inputs=("deck.json",)),
    Step("slides", "cmd", "渲染投影片（頻道品牌）", outputs=("slides/contact_sheet.png",),
         inputs=("deck.json",),
         command=lambda c: _py(c, "render_slides.py", "--run-dir", _run_dir(c), "--brand", c.channel.brand)),
    Step("gate_deck", "gate", "deck 審稿", gate=Gate.DECK,
         artifacts=("deck.json", "slides/contact_sheet.png"), applies=_gate_enabled(Gate.DECK)),
    # 事實段（Leon 7afa95870a4e＝A）：結構段（gate_deck）過了才到這裡；跟著 deck 閘門啟用
    Step("gate_deck_facts", "gate", "講稿事實查核", gate=Gate.DECK_FACTS,
         artifacts=("deck.json",), applies=_gate_enabled(Gate.DECK)),
    Step("thumbnail_spec", "agent", "標題 5–6 個＋縮圖 3 款文案", outputs=THUMB_SPECS,
         hint="寫 titles.json、thumbnail.json、thumbnail_variants.json（承諾＝前 60 秒的講稿原句），見 /deck 縮圖規則"),
    Step("thumbnail", "cmd", "頻道縮圖（角色／畫作＋大字）", outputs=("thumbnails/thumbnail.png",),
         inputs=("thumbnail.json", "assets/artwork/*"),
         command=lambda c: _py(c, "make_thumbnail.py", "--run-dir", _run_dir(c), "--channel", c.channel.code)),
    Step("thumbnail_variants", "cmd", "縮圖 A/B/C（YouTube 測試與比較）", outputs=("thumbnails/variant_*.jpg",),
         inputs=("thumbnail_variants.json", "assets/artwork/*"),
         command=lambda c: _py(c, "make_thumbnail.py", "--run-dir", _run_dir(c), "--channel", c.channel.code,
                               "--variants")),
    Step("gate_title", "gate", "標題與縮圖評審", gate=Gate.TITLE,
         artifacts=("titles.json", "thumbnail.json", "thumbnail_variants.json", "thumbnails/variant_*.jpg"),
         applies=_gate_enabled(Gate.TITLE)),
    Step("voice", "cmd", "配音＋字幕對齊", outputs=("audio/scene_*.mp3", "subtitles/subtitles.srt"),
         inputs=(),   # spoken words only (voice_spoken_key): screen and image-prompt edits never re-voice
         command=lambda c: _py(c, "run_stage.py", "--stage", "voice", "--run-dir", _run_dir(c),
                               env=_voice_env(c)),
         paid=_voice_paid, heavy_if=_voice_local, identity=voice_spoken_key),
    Step("illustrate", "cmd", "AI 插圖（本機模型，一次一張）", inputs=("deck.json",),
         command=lambda c: _py(c, "illustrate.py", "--run-dir", _run_dir(c), "--channel", c.channel.code,
                               "--env-file", str(c.options.env_file)),
         heavy=True, applies=lambda channel: channel.media.ai_image, has_work=lambda c: _illustrate_pending(c),
         identity=lambda c: c.channel.ai_illustration.model_dump_json()),
    Step("media", "cmd", "B-roll／動態投影片／AI 圖", outputs=("credits.json", "media/contact_sheet.png"),
         # assets/ai_motion/*: a Wan clip baked overnight (scripts/ai_motion.py bake) re-runs media.
         inputs=("deck.json", "audio/scene_*.mp3", "slides/slide_*.png", "assets/ai_images/*",
                 "assets/ai_motion/*.wan.*", "assets/artwork/*"),
         command=lambda c: _py(c, "media_to_visual.py", *_media_args(c)), heavy=True),
    Step("gate_media", "gate", "B-roll／AI 圖／授權審核", gate=Gate.MEDIA,
         artifacts=("media/media_report.json", "credits.json", "media/contact_sheet.png",
                    "assets/ai_images/*", "assets/artwork/*"),
         applies=_gate_enabled(Gate.MEDIA)),
    Step("assembly", "cmd", "合成（字幕燒入）", outputs=("assembly/draft.mp4",),
         inputs=("visual/*", "audio/scene_*.mp3", "subtitles/subtitles.srt"),
         command=lambda c: _py(c, "run_stage.py", "--stage", "assembly_timeline", "--run-dir",
                               _run_dir(c), env=_voice_env(c)),
         heavy=True),
    Step("mascot", "cmd", "角色疊加", outputs=("assembly/final.mp4",),
         inputs=("assembly/draft.mp4", "deck.json", "subtitles/subtitles.srt"),
         command=lambda c: _py(c, "mascot_overlay.py", "--run-dir", _run_dir(c),
                               "--workers", str(c.options.mascot_workers), *_host_args(c)),
         # no identity: one would change the fingerprint of every finished chipcat run and re-render it
         heavy=True, applies=lambda channel: channel.mascot.rig_ready),
    Step("mix", "cmd", "配樂、轉場音、音效、母帶（-14 LUFS）", outputs=("assembly/release.mp4",),
         inputs=("assembly/final.mp4", "assembly/draft.mp4", "deck.json", "script.json"),
         command=lambda c: _py(c, "audio_mix.py", "--run-dir", _run_dir(c), "--channel", c.channel.code),
         identity=lambda c: c.channel.audio.model_dump_json(),
         heavy=True, applies=lambda channel: channel.audio.enabled),
    Step("qc", "internal", "自動品質檢查", outputs=("qc/qc_report.json",),
         inputs=("assembly/*.mp4", "credits.json", "subtitles/subtitles.srt", "deck.json", "thumbnail.json",
                 "thumbnails/thumbnail.png", "audio/speech_check.json")),
    Step("gate_final", "gate", "成片審看", gate=Gate.FINAL,
         artifacts=("assembly/release.mp4", "assembly/final.mp4", "assembly/draft.mp4", "qc/qc_report.json")),
    Step("package", "internal", "上傳資料（標題、說明、章節、授權、AI 揭露、排程）",
         outputs=("upload/youtube_meta.json",),
         inputs=("script.json", "credits.json", "assembly/*.mp4", "production.schedule.json")),
)

SHORTS_SKIT_STEPS: tuple[Step, ...] = (
    Step("topic", "agent", "冷笑話選題候選（8–10 題）", outputs=("topics/candidates.json",),
         hint="選題 agent 寫 topics/candidates.json（produce.py run --auto-agents 會自動呼叫）"),
    Step("gate_topic", "gate", "選題評審", gate=Gate.TOPIC, artifacts=("topics/candidates.json",),
         applies=_gate_enabled(Gate.TOPIC)),
    Step("skit_script", "agent", "冷笑話劇本（鋪陳→停 0.6 秒→笑點→收尾）", outputs=("script.json",),
         verify=lambda c: _py(c, "check_skit.py", "--run-dir", _run_dir(c)),
         hint="跑 /skit-script（讀 topic.json 的 chosen[0] → 寫 script.json；produce.py run --auto-agents 會自動呼叫）"),
    Step("gate_script", "gate", "劇本審稿", gate=Gate.SCRIPT, artifacts=("script.json",),
         applies=_gate_enabled(Gate.SCRIPT)),
    Step("voice", "cmd", "配音＋字幕對齊", outputs=("audio/scene_*.mp3", "subtitles/subtitles.srt"),
         inputs=("script.json",),
         command=lambda c: _py(c, "run_stage.py", "--stage", "voice", "--run-dir", _run_dir(c),
                               env=_voice_env(c) | {"CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE": "24"}),
         paid=_voice_paid, heavy_if=_voice_local, identity=lambda c: voice_choice(c).describe()),
    Step("skit_render", "agent", "角色小劇場渲染", outputs=("assembly/final.mp4",),
         hint="直式角色小劇場渲染器尚未實作（roadmap R4）；先手動放 assembly/final.mp4"),
    Step("qc", "internal", "自動品質檢查", outputs=("qc/qc_report.json",),
         inputs=("assembly/*.mp4", "subtitles/subtitles.srt", "audio/speech_check.json")),
    Step("gate_final", "gate", "成片審看", gate=Gate.FINAL,
         artifacts=("assembly/final.mp4", "qc/qc_report.json")),
    Step("package", "internal", "上傳資料", outputs=("upload/youtube_meta.json",),
         inputs=("script.json", "assembly/*.mp4", "production.schedule.json")),
)


# A Short cut from an approved long run (roadmap R5): any channel, chosen by the
# run-dir holding ``short_source.json`` (written by ``produce.py short-from-long``).
# The long run's article/deck/media gates already covered every spoken word and
# asset, so only the final gate remains. The long run lives outside this
# run-dir, so the runner cannot see it change: re-cut with ``--force cut``.
SHORTS_CUT_STEPS: tuple[Step, ...] = (
    Step("cut", "cmd", "從長片切直式 Shorts（字幕重排、片頭片尾）",
         outputs=("assembly/final.mp4", "script.json", "subtitles/subtitles.srt"),
         inputs=(SHORT_SOURCE_FILE,),
         command=lambda c: _py(c, "short_from_long.py", "--run-dir", _run_dir(c)), heavy=True),
    Step("qc", "internal", "自動品質檢查", outputs=("qc/qc_report.json",),
         inputs=("assembly/*.mp4", "subtitles/subtitles.srt", "audio/speech_check.json")),
    Step("gate_final", "gate", "成片審看", gate=Gate.FINAL,
         artifacts=("assembly/final.mp4", "qc/qc_report.json")),
    Step("package", "internal", "上傳資料（#Shorts）", outputs=("upload/youtube_meta.json",),
         inputs=("script.json", "assembly/*.mp4", "production.schedule.json")),
)


# A scripted Short (short_source.json has ``beats``): its own narration, voiced with the
# channel voice, one animated page per beat (policy review 2026-10, C2). New spoken words
# need their own review, so it stops at the script gate before paying for TTS.
SHORTS_SCRIPTED_STEPS: tuple[Step, ...] = (
    Step("short_script", "internal", "Short 講稿（beats → script.json）", outputs=("script.json",),
         inputs=(SHORT_SOURCE_FILE,)),
    Step("gate_script", "gate", "Short 講稿審稿", gate=Gate.SCRIPT, artifacts=(SHORT_SOURCE_FILE, "script.json")),
    Step("voice", "cmd", "配音＋字幕對齊", outputs=("audio/scene_*.mp3", "subtitles/subtitles.srt"),
         inputs=("script.json",),
         command=lambda c: _py(c, "run_stage.py", "--stage", "voice", "--run-dir", _run_dir(c),
                               env=_voice_env(c)),
         paid=_voice_paid, heavy_if=_voice_local, identity=lambda c: voice_choice(c).describe()),
    Step("cut", "cmd", "直式 Short（每拍一頁動畫＋角色＋字幕）", outputs=("assembly/final.mp4",),
         inputs=(SHORT_SOURCE_FILE, "audio/scene_*.mp3"),
         command=lambda c: _py(c, "short_from_long.py", "--run-dir", _run_dir(c)), heavy=True),
    Step("qc", "internal", "自動品質檢查", outputs=("qc/qc_report.json",),
         inputs=("assembly/*.mp4", "subtitles/subtitles.srt", "audio/speech_check.json")),
    Step("gate_final", "gate", "成片審看", gate=Gate.FINAL,
         artifacts=("assembly/final.mp4", "qc/qc_report.json")),
    Step("package", "internal", "上傳資料（#Shorts）", outputs=("upload/youtube_meta.json",),
         inputs=("script.json", "assembly/*.mp4", "production.schedule.json")),
)


# An HN 快報 Short (production/news; ``produce.py news daily --pick``): any channel with a
# ``series.hn`` block, chosen by the run-dir holding ``news_short.json``. The script is
# written by /news-short after reading the original page; lint enforces the five beats,
# sources with read time, and the original-commentary beat. One gate: the final watch.
NEWS_SHORT_STEPS: tuple[Step, ...] = (
    Step("news_script", "agent", "HN 快報稿（讀原文後寫五段）", outputs=(NEWS_SCRIPT_FILE,),
         verify=lambda c: _py(c, "news.py", "lint", "--run-dir", _run_dir(c)),
         hint="跑 /news-short（讀 news_short.json 的原文快取 → 寫 news_script.json）"),
    # Entertainment channels (series.news.claims_audit): every factual sentence needs a sourced claim; what has none
    # is an error that gets ONE automatic fix (delete / rewrite as 「據…報導」), then the run goes on without a re-check.
    Step("fact_audit", "cmd", "事實出處查核（無出處＝錯誤，自動修一次）", outputs=("review/fact_audit.json",),
         inputs=(NEWS_SCRIPT_FILE, NEWS_ITEM_FILE),
         command=lambda c: _py(c, "news.py", "audit", "--run-dir", _run_dir(c)),
         applies=lambda channel: _claims_audit(channel)),
    Step("news_prepare", "cmd", "稿 → script.json（五段＝五個場景）", outputs=("script.json", "voice_text.json"),
         inputs=(NEWS_SCRIPT_FILE,),
         command=lambda c: _py(c, "news.py", "prepare", "--run-dir", _run_dir(c))),
    # Channels with a ``series.news`` block (technews; Leon 2026-10-23) also get the script panel
    # (stage shorts_script) before any voice is made; chipcat's ``series.hn`` keeps its original flow.
    Step("gate_script", "gate", "腳本評審（Shorts）", gate=Gate.SCRIPT, artifacts=("script.json",),
         applies=lambda channel: "news" in channel.series),
    Step("voice", "cmd", "配音＋字幕對齊", outputs=("audio/scene_*.mp3", "subtitles/subtitles.srt"),
         inputs=("voice_text.json",),  # spoken words only: screen edits never re-voice
         command=lambda c: _py(c, "run_stage.py", "--stage", "voice", "--run-dir", _run_dir(c),
                               env=_voice_env(c)),
         paid=_voice_paid, heavy_if=_voice_local, identity=lambda c: voice_choice(c).describe()),
    Step("news_render", "cmd", "直式頁面（來源卡／角色）＋字幕燒入",
         outputs=("assembly/final.mp4", "thumbnails/thumbnail.png", "credits.json"),
         inputs=(NEWS_SCRIPT_FILE, "script.json", "audio/scene_*.mp3", "subtitles/subtitles.srt"),
         command=lambda c: _py(c, "news.py", "render", "--run-dir", _run_dir(c)), heavy=True),
    Step("qc", "internal", "自動品質檢查", outputs=("qc/qc_report.json",),
         inputs=("assembly/*.mp4", "credits.json", "subtitles/subtitles.srt")),
    Step("gate_final", "gate", "成片審看", gate=Gate.FINAL,
         artifacts=("assembly/final.mp4", NEWS_SCRIPT_FILE, "qc/qc_report.json")),
    Step("package", "internal", "上傳資料（#Shorts、來源、排程）", outputs=("upload/youtube_meta.json",),
         inputs=("script.json", "credits.json", "assembly/*.mp4", "production.schedule.json")),
)


# 寓言學堂 (channel ``fable``, Leon 2026-10-24 bc217c0643ef = A): Shorts (9:16) and mid-length (16:9) videos from
# one ``fable.json``. Topics are picked by hand (topic.json); two reviews only — the script panel (judged once, fixes
# applied once) and the concept-facts check (confidence >= 0.5 counts; one automatic fix).
FABLE_STEPS: tuple[Step, ...] = (
    Step("fable_topic", "agent", "題目（概念、領域、長度）", outputs=("topic.json",),
         hint="寫 topic.json：{\"chosen\":[{\"concept\":…,\"domain\":…,\"format\":\"short|mid\",\"premise\":…}]}"),
    Step("fable_script", "agent", "寓言腳本（hook → 寓言 → 揭曉 → 解釋 → 應用）", outputs=(FABLE_FILE,),
         verify=lambda c: _py(c, "fable.py", "lint", "--run-dir", _run_dir(c)),
         hint="跑 /fable-script（讀 topic.json 的 chosen[0] → 寫 fable.json；produce.py run --auto-agents 會自動呼叫）"),
    Step("fable_prepare", "cmd", "fable.json → script.json（一個 beat＝一個場景）", outputs=("script.json", "voice_text.json"),
         inputs=(FABLE_FILE,), command=lambda c: _py(c, "fable.py", "prepare", "--run-dir", _run_dir(c))),
    Step("gate_script", "gate", "腳本評審（猜到時間點、揭曉驚喜）", gate=Gate.SCRIPT, artifacts=("script.json",),
         applies=_gate_enabled(Gate.SCRIPT)),
    Step("gate_facts", "gate", "概念正確性查核", gate=Gate.DECK_FACTS, artifacts=("script.json",),
         applies=_gate_enabled(Gate.DECK_FACTS)),
    Step("voice", "cmd", "配音＋字幕對齊", outputs=("audio/scene_*.mp3", "subtitles/subtitles.srt"),
         inputs=("voice_text.json",),
         command=lambda c: _py(c, "run_stage.py", "--stage", "voice", "--run-dir", _run_dir(c),
                               env=_voice_env(c) | {"CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE": "22"}),
         paid=_voice_paid, heavy_if=_voice_local, identity=voice_spoken_key),
    Step("fable_images", "cmd", "繪本插圖（本機模型，一次一張）＋視差動態", outputs=("assets/fable/clips.json",),
         inputs=(FABLE_FILE,), heavy=True,
         command=lambda c: _py(c, "fable.py", "images", "--run-dir", _run_dir(c), "--env-file", str(c.options.env_file)),
         identity=lambda c: c.channel.ai_illustration.model_dump_json()),
    Step("fable_render", "cmd", "合成（繪本→概念圖解轉場、字幕燒入）",
         outputs=("assembly/final.mp4", "thumbnails/thumbnail.png", "credits.json"),
         inputs=(FABLE_FILE, "script.json", "audio/scene_*.mp3", "subtitles/subtitles.srt", "assets/fable/clips.json"),
         command=lambda c: _py(c, "fable.py", "render", "--run-dir", _run_dir(c)), heavy=True),
    Step("mix", "cmd", "配樂、轉場音、母帶", outputs=("assembly/release.mp4",),
         inputs=("assembly/final.mp4", "script.json"),
         command=lambda c: _py(c, "audio_mix.py", "--run-dir", _run_dir(c), "--channel", c.channel.code),
         identity=lambda c: c.channel.audio.model_dump_json(), heavy=True, applies=lambda channel: channel.audio.enabled),
    Step("qc", "internal", "自動品質檢查", outputs=("qc/qc_report.json",),
         inputs=("assembly/*.mp4", "credits.json", "subtitles/subtitles.srt", "audio/speech_check.json")),
    Step("gate_final", "gate", "成片審看", gate=Gate.FINAL,
         artifacts=("assembly/release.mp4", "assembly/final.mp4", "qc/qc_report.json"), applies=_gate_enabled(Gate.FINAL)),
    Step("package", "internal", "上傳資料（標題、說明、授權、AI 揭露、排程）", outputs=("upload/youtube_meta.json",),
         inputs=("script.json", "credits.json", "assembly/*.mp4", "production.schedule.json")),
)


def _claims_audit(channel: Channel) -> bool:
    return bool((channel.series.get("news") or {}).get("claims_audit"))


def news_weekly_steps(channel: Channel) -> tuple[Step, ...]:
    """The weekly HN roll-up: /news-weekly writes deck.json from weekly_plan.md (no article
    stage — each story was read and approved as a Short), then the explainer steps."""
    head = (
        Step("deck", "agent", "週整理簡報與講稿（每則一章）", outputs=("deck.json",),
             verify=lambda c: _py(c, "deck_to_script.py", "--run-dir", _run_dir(c), "--strict"),
             hint="跑 /news-weekly（讀 weekly_plan.md → 寫 deck.json）"),
        Step("weekly_check", "cmd", "每則一章＋引用讀過的原文", inputs=("deck.json", NEWS_WEEKLY_FILE),
             command=lambda c: _py(c, "news.py", "weekly-check", "--run-dir", _run_dir(c))),
    )
    tail = tuple(s for s in EXPLAINER_STEPS if s.name not in (*TOPIC_STEPS, "article", "gate_article", "deck"))
    return tuple(step for step in (*head, *tail) if step.applies(channel))


def steps_for(channel: Channel, run_dir: Path | None = None) -> tuple[Step, ...]:
    if is_short_cut(run_dir):
        from content_farm.production.shorts_cut import load_spec

        return SHORTS_SCRIPTED_STEPS if load_spec(run_dir).scripted else SHORTS_CUT_STEPS
    if run_dir is not None and (run_dir / NEWS_ITEM_FILE).is_file():
        return tuple(step for step in NEWS_SHORT_STEPS if step.applies(channel))
    if run_dir is not None and (run_dir / NEWS_WEEKLY_FILE).is_file():
        return news_weekly_steps(channel)
    steps = {Pipeline.EXPLAINER: EXPLAINER_STEPS, Pipeline.SHORTS_SKIT: SHORTS_SKIT_STEPS,
             Pipeline.FABLE: FABLE_STEPS}[channel.pipeline]
    legacy = _topic_chosen_elsewhere(run_dir)
    return tuple(step for step in steps if step.applies(channel) and not (legacy and step.name in TOPIC_STEPS))


TOPIC_STEPS = ("topic", "gate_topic")


def _topic_chosen_elsewhere(run_dir: Path | None) -> bool:
    """A run started before the topic panel (article already there, no topics/): skip the topic steps."""
    return run_dir is not None and (run_dir / "article.md").is_file() and not (run_dir / "topics").is_dir()


def step_names(channel: Channel, run_dir: Path | None = None) -> tuple[str, ...]:
    return tuple(step.name for step in steps_for(channel, run_dir))
