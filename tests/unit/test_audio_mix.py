"""Audio mix planning: SFX synthesis, cue spacing, BGM per chapter, ASS subtitle box."""

from __future__ import annotations

import wave

from content_farm.assembly.timeline_assembly import LANDSCAPE_PRESET, PORTRAIT_PRESET, _subtitle_colours_and_border
from content_farm.audio_mix.cues import SFX_MIN_SPACING, plan
from content_farm.audio_mix.mix import bgm_segments
from content_farm.audio_mix.sfx import KINDS, ensure_sfx
from content_farm.production.channels import AudioMix, AudioTrack
from content_farm.retention.beats import Hook
from content_farm.retention.timing import Scene
from content_farm.subtitle.line_wrap import wrap_text


def test_sfx_files_are_written_once(tmp_path) -> None:
    paths = ensure_sfx(tmp_path)
    assert set(paths) == set(KINDS)
    with wave.open(str(paths["ding"])) as w:
        assert w.getframerate() == 48000 and w.getnframes() > 10000
    mtime = paths["pop"].stat().st_mtime
    assert ensure_sfx(tmp_path)["pop"].stat().st_mtime == mtime


def _scenes() -> list[Scene]:
    return [Scene(1, "s01", 1, 0, 40, ""), Scene(2, "s02", 1, 40, 80, ""), Scene(3, "s03", 2, 80, 120, "")]


def test_cues_space_sfx_and_add_chapter_stinger() -> None:
    hooks = [Hook(5, "reversal", "s01", "但", 8), Hook(9, "joke", "s01", "罐罐", 10),
             Hook(30, "question", "s01", "？", 31), Hook(79, "tease", "s02", "接下來", 80)]
    cues = plan(_scenes(), hooks)
    stingers = [c for c in cues if c.kind == "stinger"]
    assert [round(c.t, 1) for c in stingers] == [79.6]
    sfx = [c for c in cues if c.kind != "stinger"]
    assert all(b.t - a.t >= SFX_MIN_SPACING for a, b in zip(sfx, sfx[1:]))
    assert sfx[0].kind == "ding" and sfx[0].t == 8           # reversal lands at sentence end
    assert all(abs(c.t - 79.6) >= 4 for c in sfx)            # nothing on top of the stinger
    assert plan(_scenes(), hooks, sfx=False) == stingers


def test_bgm_segments_follow_chapter_assignment() -> None:
    main = AudioTrack(path="a.wav", title="main", source="x", license="MIT")
    alt = AudioTrack(path="b.wav", title="alt", source="x", license="MIT", chapters=(2,))
    segments = bgm_segments(AudioMix(enabled=True, bgm=(main, alt)), [(1, 0, 50), (2, 50, 90), (3, 90, 120)])
    assert [(t.title, a, b) for t, a, b in segments] == [("main", 0, 50), ("alt", 50, 90), ("main", 90, 120)]


def test_landscape_subtitles_are_bigger_with_a_box() -> None:
    assert 5.0 <= 100 * LANDSCAPE_PRESET.subtitle_font_size / LANDSCAPE_PRESET.height <= 6.0
    assert ",3,10,0" in _subtitle_colours_and_border(LANDSCAPE_PRESET)
    assert ",1,3,1" in _subtitle_colours_and_border(PORTRAIT_PRESET)   # Shorts keep the outline


def test_wrap_prefers_word_boundary_over_hard_cut() -> None:
    lines = wrap_text("台積電的先進封裝產能還在持續擴張中", 10).split("\n")
    assert lines[0].endswith("的") or lines[1][0] in "是在和與跟就也都把被從到而但卻還要會能讓"
