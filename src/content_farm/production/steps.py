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

from content_farm.production.channels import Channel, Gate, Pipeline
from content_farm.production.shorts_cut import SOURCE_FILE as SHORT_SOURCE_FILE
from content_farm.production.shorts_cut import is_short_cut
from content_farm.production.voice_choice import VoiceChoice, choose_voice, env_file_defaults

REPO_ROOT = Path(__file__).resolve().parents[3]
EXPLAINER_SUBTITLE_MAX = "20"  # keeps landscape subtitles clear of the mascot (REPORT-explainer-v2 §3)


@dataclass(frozen=True)
class RunOptions:
    mock_voice: bool = False      # macOS `say` instead of paid TTS
    allow_paid: bool = False      # required for paid TTS
    no_stock: bool = False
    env_file: Path = REPO_ROOT / ".env"
    mascot_workers: int = 2
    python: str = sys.executable


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
    applies: Callable[[Channel], bool] = lambda channel: True
    # Settings that change the output without touching any input file (e.g. the TTS
    # voice); folded into the fingerprint and logged when the step runs.
    identity: Callable[[Context], str] | None = None


def _py(ctx: Context, script: str, *args: str, env: dict[str, str] | None = None) -> Command:
    return Command((ctx.options.python, str(REPO_ROOT / "scripts" / script), *args), env or {})


def _run_dir(ctx: Context) -> str:
    return str(ctx.run_dir)


def voice_choice(ctx: Context) -> VoiceChoice:
    return choose_voice(ctx.channel, ctx.options.env_file, mock=ctx.options.mock_voice)


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
    if ctx.options.no_stock or not ctx.channel.media.stock:
        args.append("--no-stock")
    return tuple(args)


def _gate_enabled(gate: Gate) -> Callable[[Channel], bool]:
    return lambda channel: channel.gate_enabled(gate)


EXPLAINER_STEPS: tuple[Step, ...] = (
    Step("article", "agent", "研究與文章", outputs=("article.md", "sources.json"),
         verify=lambda c: _py(c, "check_article.py", "--run-dir", _run_dir(c)),
         hint="在 run-dir 跑 /article <題目>（Claude skill，會上網查資料）"),
    Step("gate_article", "gate", "文章審稿", gate=Gate.ARTICLE,
         artifacts=("article.md", "sources.json"), applies=_gate_enabled(Gate.ARTICLE)),
    Step("deck", "agent", "簡報大綱與講稿", outputs=("deck.json",),
         verify=lambda c: _py(c, "deck_to_script.py", "--run-dir", _run_dir(c), "--strict"),
         hint="跑 /deck-outline 再 /deck（會產生 deck.json）"),
    Step("thumbnail_spec", "agent", "縮圖文案與主視覺", outputs=("thumbnail.json",),
         hint="寫 thumbnail.json：角色／畫作＋≤10 字大字＋promise（前 60 秒兌現的講稿原句），見 /deck 縮圖規則"),
    Step("policy", "internal", "頻道素材政策與頻道規則（開場、片尾、觀點段、角色）", inputs=("deck.json",)),
    Step("slides", "cmd", "渲染投影片（頻道品牌）", outputs=("slides/contact_sheet.png",),
         inputs=("deck.json",),
         command=lambda c: _py(c, "render_slides.py", "--run-dir", _run_dir(c), "--brand", c.channel.brand)),
    Step("gate_deck", "gate", "deck 審稿", gate=Gate.DECK,
         artifacts=("deck.json", "slides/contact_sheet.png"), applies=_gate_enabled(Gate.DECK)),
    Step("voice", "cmd", "配音＋字幕對齊", outputs=("audio/scene_*.mp3", "subtitles/subtitles.srt"),
         inputs=("deck.json", "script.json"),
         command=lambda c: _py(c, "run_stage.py", "--stage", "voice", "--run-dir", _run_dir(c),
                               env=_voice_env(c)),
         paid=lambda c: not c.options.mock_voice, identity=lambda c: voice_choice(c).describe()),
    Step("illustrate", "cmd", "AI 插圖（本機模型，一次一張）", inputs=("deck.json",),
         command=lambda c: _py(c, "illustrate.py", "--run-dir", _run_dir(c), "--channel", c.channel.code,
                               "--env-file", str(c.options.env_file)),
         heavy=True, applies=lambda channel: channel.media.ai_image,
         identity=lambda c: c.channel.ai_illustration.model_dump_json()),
    Step("media", "cmd", "B-roll／動態投影片／AI 圖", outputs=("credits.json", "media/contact_sheet.png"),
         inputs=("deck.json", "audio/scene_*.mp3", "slides/slide_*.png", "assets/ai_images/*",
                 "assets/artwork/*"),
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
                               "--workers", str(c.options.mascot_workers)),
         heavy=True, applies=lambda channel: channel.mascot.rig_ready),
    Step("thumbnail", "cmd", "頻道縮圖（角色／畫作＋大字）", outputs=("thumbnails/thumbnail.png",),
         inputs=("thumbnail.json", "assets/artwork/*", "assets/ai_images/*"),
         command=lambda c: _py(c, "make_thumbnail.py", "--run-dir", _run_dir(c), "--channel", c.channel.code)),
    Step("qc", "internal", "自動品質檢查", outputs=("qc/qc_report.json",),
         inputs=("assembly/*.mp4", "credits.json", "subtitles/subtitles.srt", "deck.json", "thumbnail.json",
                 "thumbnails/thumbnail.png")),
    Step("gate_final", "gate", "成片審看", gate=Gate.FINAL,
         artifacts=("assembly/final.mp4", "assembly/draft.mp4", "qc/qc_report.json")),
    Step("package", "internal", "上傳資料（標題、說明、章節、授權、AI 揭露、排程）",
         outputs=("upload/youtube_meta.json",),
         inputs=("script.json", "credits.json", "assembly/*.mp4", "production.schedule.json")),
)

SHORTS_SKIT_STEPS: tuple[Step, ...] = (
    Step("skit_script", "agent", "冷笑話劇本", outputs=("script.json",),
         hint="寫 script.json（鋪陳→停頓→笑點，20–50 秒）；skit skill 尚未建立，見 roadmap"),
    Step("gate_script", "gate", "劇本審稿", gate=Gate.SCRIPT, artifacts=("script.json",),
         applies=_gate_enabled(Gate.SCRIPT)),
    Step("voice", "cmd", "配音＋字幕對齊", outputs=("audio/scene_*.mp3", "subtitles/subtitles.srt"),
         inputs=("script.json",),
         command=lambda c: _py(c, "run_stage.py", "--stage", "voice", "--run-dir", _run_dir(c),
                               env=_voice_env(c) | {"CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE": "24"}),
         paid=lambda c: not c.options.mock_voice, identity=lambda c: voice_choice(c).describe()),
    Step("skit_render", "agent", "角色小劇場渲染", outputs=("assembly/final.mp4",),
         hint="直式角色小劇場渲染器尚未實作（roadmap R4）；先手動放 assembly/final.mp4"),
    Step("qc", "internal", "自動品質檢查", outputs=("qc/qc_report.json",),
         inputs=("assembly/*.mp4", "subtitles/subtitles.srt")),
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
         inputs=("assembly/*.mp4", "subtitles/subtitles.srt")),
    Step("gate_final", "gate", "成片審看", gate=Gate.FINAL,
         artifacts=("assembly/final.mp4", "qc/qc_report.json")),
    Step("package", "internal", "上傳資料（#Shorts）", outputs=("upload/youtube_meta.json",),
         inputs=("script.json", "assembly/*.mp4", "production.schedule.json")),
)


def steps_for(channel: Channel, run_dir: Path | None = None) -> tuple[Step, ...]:
    if is_short_cut(run_dir):
        return SHORTS_CUT_STEPS
    steps = {Pipeline.EXPLAINER: EXPLAINER_STEPS, Pipeline.SHORTS_SKIT: SHORTS_SKIT_STEPS}[channel.pipeline]
    return tuple(step for step in steps if step.applies(channel))


def step_names(channel: Channel, run_dir: Path | None = None) -> tuple[str, ...]:
    return tuple(step.name for step in steps_for(channel, run_dir))
