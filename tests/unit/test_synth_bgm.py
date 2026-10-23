"""Synthesized BGM: deterministic, seamless loop, wired in as the channel's bed with self-made credits."""

from __future__ import annotations

import numpy as np
import pytest

from content_farm.audio_mix.mix import credits_for
from content_farm.audio_mix.sfx import RATE
from content_farm.audio_mix.synth_bgm import LOOP_SECONDS, wafu, with_synth_bgm
from content_farm.production.channels import AudioMix, AudioTrack, load_channel


@pytest.fixture(scope="module")
def bed() -> np.ndarray:
    return wafu()


def test_wafu_is_deterministic_and_the_right_length(bed) -> None:
    assert len(bed) == int(LOOP_SECONDS * RATE)
    assert np.array_equal(bed, wafu())
    assert 0.99 <= float(np.max(np.abs(bed))) <= 1.0


def test_wafu_loops_without_a_seam(bed) -> None:
    window = int(0.05 * RATE)
    typical = float(np.sqrt(np.mean(bed[:window] ** 2)))
    jump = abs(float(bed[-1] - bed[0]))
    assert typical > 0.01
    assert jump < 0.25 * float(np.max(np.abs(bed)))       # a free-running splice would jump by ~the peak
    step = float(np.max(np.abs(np.diff(bed[: RATE]))))
    assert jump < 4 * step                                  # no bigger than the normal sample-to-sample move


def test_synth_bgm_becomes_the_bed_and_is_credited_as_self_made(tmp_path) -> None:
    config = with_synth_bgm(AudioMix(enabled=True, synth_bgm="wafu"), tmp_path)
    assert [t.title for t in config.bgm] == ["合成配樂（wafu）"]
    assert (tmp_path / "wafu.wav").is_file()
    entries = credits_for(config, [{"title": config.bgm[0].title}], [])["entries"]
    assert entries[0]["kind"] == "bgm" and "自製" in entries[0]["license"]


def test_real_bgm_files_win_over_the_synth_preset(tmp_path) -> None:
    track = AudioTrack(path="a.wav", title="main", source="x", license="MIT")
    config = AudioMix(enabled=True, bgm=(track,), synth_bgm="wafu")
    assert with_synth_bgm(config, tmp_path) is config
    assert not (tmp_path / "wafu.wav").exists()
    off = AudioMix(enabled=True)
    assert with_synth_bgm(off, tmp_path) is off


def test_a_channel_without_a_mascot_never_mixes_under_a_leftover_final(tmp_path) -> None:
    from content_farm.audio_mix.run import source_video

    (tmp_path / "assembly").mkdir()
    for name in ("draft.mp4", "final.mp4"):
        (tmp_path / "assembly" / name).write_bytes(b"x")
    yokai = load_channel("yokai")
    assert not yokai.mascot.rig_ready
    assert source_video(tmp_path, yokai).name == "draft.mp4"    # a cloned run's old final.mp4 carries the frog
    with_rig = yokai.model_copy(update={"mascot": yokai.mascot.model_copy(update={"rig_ready": True})})
    assert source_video(tmp_path, with_rig).name == "final.mp4"


def test_yokai_mixes_a_synth_bed_and_keeps_the_voice_level() -> None:
    audio = load_channel("yokai").audio
    assert audio.enabled and audio.synth_bgm == "wafu" and not audio.bgm
    assert audio.voice_lufs == audio.master_lufs        # no loudness lift: the voice keeps its level
    assert not load_channel("yokai").mascot.rig_ready


@pytest.mark.parametrize("style", ["studio", "pulse"])
def test_v4_styles_are_deterministic_seamless_and_wired_in(style, tmp_path) -> None:
    from content_farm.audio_mix import synth_bgm

    bed = synth_bgm.PRESETS[style]()
    assert len(bed) == int(LOOP_SECONDS * RATE) and np.array_equal(bed, synth_bgm.PRESETS[style]())
    step = float(np.max(np.abs(np.diff(bed[: RATE]))))
    assert abs(float(bed[-1] - bed[0])) < 4 * step and float(np.sqrt(np.mean(bed[: int(0.05 * RATE)] ** 2))) > 0.003
    config = with_synth_bgm(AudioMix(enabled=True, synth_bgm=style), tmp_path)
    assert [t.title for t in config.bgm] == [f"合成配樂（{style}）"]


def test_long_channels_each_have_one_local_style_that_can_be_switched_off() -> None:
    assert {c: load_channel(c).audio.synth_bgm for c in ("yokai", "cel", "technews")} == {
        "yokai": "wafu", "cel": "studio", "technews": "pulse"}
    assert all(load_channel(c).audio.enabled for c in ("yokai", "cel", "technews"))
