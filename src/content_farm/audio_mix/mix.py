"""Mix the narrated video with a BGM bed, stingers and SFX, then master to the loudness target.

Pass 1 (one ffmpeg run) writes three stems — voice (gain-matched to ``voice_lufs``), BGM
(looped, levelled to ``voice_lufs - bgm_under_voice_db + duck_db`` and side-chain ducked by the
voice), effects — plus their sum. Pass 2 masters the sum with loudnorm (two-pass, linear when
possible) to ``master_lufs`` / ``true_peak_db`` and muxes it with the untouched picture.

Outputs (``audio/mix/``): ``voice.wav``, ``bgm.wav``, ``fx.wav``, ``mix.wav``, ``master.wav``,
``mix_report.json``, ``audio_credits.json``; video: ``assembly/release.mp4``.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from content_farm.audio_mix.cues import Cue
from content_farm.audio_mix.sfx import ensure_sfx
from content_farm.production.channels import AudioMix, AudioTrack
from content_farm.retention.audio_probe import loudness

MIX_DIR = Path("audio") / "mix"
RELEASE = Path("assembly") / "release.mp4"
SFX_UNDER_VOICE_DB = 9.0      # effects sit between the bed and the voice
STINGER_UNDER_VOICE_DB = 6.0
SFX_MAX_BOOST_DB = 6.0
PRE_MASTER_LIMIT = 0.6        # -4.4 dBFS peak limiter: leaves room for the ~+2 dB master gain + TP overshoot, so loudnorm stays linear
_LOUDNORM_JSON = re.compile(r"\{\s*\"input_i\".*?\}", re.DOTALL)


@dataclass(frozen=True)
class MixPlan:
    duration: float
    voice_gain_db: float
    bgm: list[dict]               # [{path, gain_db, start, end, title}]
    cues: list[Cue]
    cue_files: dict[str, Path]
    cue_gain_db: dict[str, float]


def _run(cmd: list[str], timeout: int = 3600) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {result.stderr[-600:]}")
    return result.stderr


def _expand(path: str) -> Path:
    return Path(path).expanduser()


def bgm_segments(config: AudioMix, chapters: list[tuple[int, float, float]]) -> list[tuple[AudioTrack, float, float]]:
    """Which bed plays under which chapter: a track listing the chapter wins, else the first
    unrestricted track. Consecutive chapters with the same track merge into one segment."""
    default = next((t for t in config.bgm if not t.chapters), config.bgm[0] if config.bgm else None)
    segments: list[tuple[AudioTrack, float, float]] = []
    for number, start, end in chapters:
        track = next((t for t in config.bgm if number in t.chapters), default)
        if track is None:
            continue
        if segments and segments[-1][0] is track and abs(segments[-1][2] - start) < 0.01:
            segments[-1] = (track, segments[-1][1], end)
        else:
            segments.append((track, start, end))
    return segments


def make_plan(run_dir: Path, config: AudioMix, video: Path, chapters: list[tuple[int, float, float]],
              cues: list[Cue]) -> MixPlan:
    voice = loudness(video)
    duration = round(len(voice.momentary) / 10.0, 2)
    bed_target = config.voice_lufs - config.bgm_under_voice_db + config.duck_db
    beds = []
    for track, start, end in bgm_segments(config, chapters):
        path = _expand(track.path)
        if not path.is_file():
            raise FileNotFoundError(f"BGM file missing: {path}")
        level = loudness(path).integrated
        beds.append({"path": str(path), "gain_db": round(bed_target - level, 2), "start": start, "end": end,
                     "title": track.title})
    files = ensure_sfx(run_dir / MIX_DIR / "sfx")
    if config.stinger is not None:
        files = {**files, "stinger": _expand(config.stinger.path)}
    gains = {}
    for kind, path in files.items():
        under = STINGER_UNDER_VOICE_DB if kind == "stinger" else SFX_UNDER_VOICE_DB
        # SFX are shorter than the 400 ms integration window: level them by their loudest
        # momentary reading, and never boost by more than SFX_MAX_BOOST_DB
        level = float(loudness(path).momentary.max())
        gains[kind] = round(min(config.voice_lufs - under - level, SFX_MAX_BOOST_DB), 2)
    return MixPlan(duration, round(config.voice_lufs - voice.integrated, 2), beds, cues, files, gains)


def _filter_graph(plan: MixPlan, config: AudioMix) -> tuple[list[str], str]:
    """ffmpeg inputs after the video, and the filter graph producing [voice] [bgm] [fx] [mix]."""
    inputs: list[str] = []
    parts = [f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={plan.voice_gain_db}dB,"
             f"asplit=3[voice][vsc][vmix]"]
    beds = []
    for k, bed in enumerate(plan.bgm):
        inputs += ["-stream_loop", "-1", "-i", bed["path"]]
        length = bed["end"] - bed["start"]
        fade_out = max(length - 2.5, 0)
        parts.append(f"[{k + 1}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                     f"atrim=0:{length:.3f},asetpts=PTS-STARTPTS,volume={bed['gain_db']}dB,"
                     f"afade=t=in:d=1.5,afade=t=out:st={fade_out:.3f}:d=2.5,"
                     f"adelay={int(bed['start'] * 1000)}:all=1[bed{k}]")
        beds.append(f"[bed{k}]")
    bed_inputs = len(plan.bgm)
    if beds:
        parts.append(f"{''.join(beds)}amix=inputs={len(beds)}:normalize=0:duration=longest,"
                     f"apad=whole_dur={plan.duration:.3f},atrim=0:{plan.duration:.3f}[bedsum]")
        ratio = max(10 ** (config.duck_db / 20), 1.0)
        parts.append(f"[bedsum][vsc]sidechaincompress=threshold=0.015:ratio={min(ratio * 2, 20):.1f}:"
                     f"attack=60:release=700:knee=4[bgm]")
    else:
        parts.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{plan.duration:.3f}[bgm_silent]")
        parts.append("[vsc]anullsink")
        parts.append("[bgm_silent]anull[bgm]")
    fx = []
    file_index: dict[str, int] = {}
    for k, cue in enumerate(plan.cues):
        if cue.kind not in file_index:
            file_index[cue.kind] = bed_inputs + len(file_index) + 1
            inputs += ["-i", str(plan.cue_files[cue.kind])]
        parts.append(f"[{file_index[cue.kind]}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                     f"volume={plan.cue_gain_db[cue.kind]}dB,adelay={int(cue.t * 1000)}:all=1[fx{k}]")
        fx.append(f"[fx{k}]")
    if fx:
        parts.append(f"{''.join(fx)}amix=inputs={len(fx)}:normalize=0:duration=longest,"
                     f"apad=whole_dur={plan.duration:.3f},atrim=0:{plan.duration:.3f}[fxsum]")
    else:
        parts.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{plan.duration:.3f}[fxsum]")
    parts.append("[bgm]asplit=2[bgm_out][bgm_mix]")
    parts.append("[fxsum]asplit=2[fx_out][fx_mix]")
    parts.append("[vmix][bgm_mix][fx_mix]amix=inputs=3:normalize=0:duration=first,"
                 f"alimiter=limit={PRE_MASTER_LIMIT}:attack=5:release=60:level=disabled[mix]")
    return inputs, ";".join(parts)


def render_stems(video: Path, plan: MixPlan, config: AudioMix, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs, graph = _filter_graph(plan, config)
    paths = {name: out_dir / f"{name}.wav" for name in ("voice", "bgm", "fx", "mix")}
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), *inputs,
           "-filter_complex", graph,
           "-map", "[voice]", str(paths["voice"]), "-map", "[bgm_out]", str(paths["bgm"]),
           "-map", "[fx_out]", str(paths["fx"]), "-map", "[mix]", str(paths["mix"])]
    _run(cmd)
    return paths


def master(mix: Path, out: Path, config: AudioMix) -> dict:
    """Two-pass loudnorm; returns the measured second-pass stats."""
    target = f"I={config.master_lufs}:TP={config.true_peak_db}:LRA=11"
    first = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(mix), "-af",
                  f"loudnorm={target}:print_format=json", "-f", "null", "-"])
    found = _LOUDNORM_JSON.search(first)
    if not found:
        raise RuntimeError("loudnorm pass 1 printed no JSON")
    m = json.loads(found.group(0))
    second = (f"loudnorm={target}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
              f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
              f"offset={m['target_offset']}:linear=true:print_format=json")
    log = _run(["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(mix), "-af", second,
                "-ar", "48000", str(out)])
    found = _LOUDNORM_JSON.search(log)
    return json.loads(found.group(0)) if found else {}


def mux(video: Path, audio: Path, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-i", str(audio),
          "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
          "-shortest", "-movflags", "+faststart", str(out)])
    return out


def credits_for(config: AudioMix, used_bgm: list[dict], used_cues: list[Cue]) -> dict:
    entries = []
    titles = {bed["title"] for bed in used_bgm}
    for track in config.bgm:
        if track.title in titles:
            entries.append({"kind": "bgm", **{k: v for k, v in track.model_dump().items() if k != "chapters"}})
    kinds = {c.kind for c in used_cues}
    if config.stinger is not None and "stinger" in kinds:
        entries.append({"kind": "stinger", **config.stinger.model_dump(exclude={"chapters"})})
    synth = sorted(k for k in kinds if config.stinger is None or k != "stinger")
    if synth:
        entries.append({"kind": "sfx", "title": "、".join(synth), "source": "本頻道以程式合成（numpy）",
                        "license": "自製，無第三方素材", "path": "audio/mix/sfx/"})
    lines = [e["attribution"] for e in entries if e.get("attribution")]
    return {"entries": entries, "description_text": "\n".join(lines)}


def report(plan: MixPlan, stats: dict, credits: dict) -> dict:
    return {"duration": plan.duration, "voice_gain_db": plan.voice_gain_db, "bgm": plan.bgm,
            "cues": [asdict(c) for c in plan.cues], "cue_gain_db": plan.cue_gain_db,
            "master": stats, "credits": credits}
