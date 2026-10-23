"""Run-directory entry point for the audio mix (``scripts/audio_mix.py``, produce step ``mix``)."""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.audio_mix.cues import plan as plan_cues
from content_farm.audio_mix.mix import (MIX_DIR, RELEASE, credits_for, make_plan, master, mux, render_stems,
                                         report)
from content_farm.audio_mix.synth_bgm import with_synth_bgm
from content_farm.production.channels import Channel
from content_farm.retention.beats import lint, slide_beats
from content_farm.retention.timing import load_scenes, sentence_timeline


def source_video(run_dir: Path, channel: Channel) -> Path:
    """The picture to put the mix under: the host-composited final, else the draft (never release).

    A channel without a mascot overlay (``rig_ready: false``) never uses ``final.mp4`` when a draft
    exists: a final left over from an earlier run (cloned run-dir) would bring the old mascot back."""
    names = ("final.mp4", "draft.mp4") if channel.mascot.rig_ready else ("draft.mp4", "final.mp4")
    for name in names:
        path = run_dir / "assembly" / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"{run_dir}/assembly has no final.mp4 or draft.mp4")


def chapters_of(scenes) -> list[tuple[int, float, float]]:
    out: list[tuple[int, float, float]] = []
    for scene in scenes:
        if out and out[-1][0] == scene.chapter:
            out[-1] = (scene.chapter, out[-1][1], scene.end)
        else:
            out.append((scene.chapter, scene.start, scene.end))
    return out


def run_mix(run_dir: Path, channel: Channel) -> dict:
    if not channel.audio.enabled:
        raise ValueError(f"channel {channel.code} has audio.enabled: false")
    config = with_synth_bgm(channel.audio, run_dir / MIX_DIR / "bgm")
    video = source_video(run_dir, channel)
    scenes = load_scenes(run_dir)
    beats = lint(scenes, sentence_timeline(run_dir, scenes), slide_beats(run_dir))
    cues = plan_cues(scenes, beats.hooks, sfx=config.sfx)
    plan = make_plan(run_dir, config, video, chapters_of(scenes), cues)
    out_dir = run_dir / MIX_DIR
    stems = render_stems(video, plan, config, out_dir)
    stats = master(stems["mix"], out_dir / "master.wav", config)
    mux(video, out_dir / "master.wav", run_dir / RELEASE)
    credits = credits_for(config, plan.bgm, cues)
    data = report(plan, stats, credits)
    data["source_video"] = video.relative_to(run_dir).as_posix()
    (out_dir / "mix_report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "audio_credits.json").write_text(json.dumps(credits, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    return data
