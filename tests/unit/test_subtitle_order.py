"""Quality v5 item 6 (ffmpeg-skill gotcha): subtitles are burned only after every upscale / crop / pad is done, so a
resize never blurs or moves the burned text. These tests pin the order in the code paths that burn subtitles."""

from __future__ import annotations

import inspect
import re

from content_farm.assembly import timeline_assembly
from content_farm.explainer import ffmpeg_ops
from content_farm.production import shorts_render, shorts_scripted_render
from content_farm.production.news import render as news_render


def test_long_form_assembly_normalises_and_concats_before_it_burns_subtitles() -> None:
    source = inspect.getsource(timeline_assembly.assemble_timeline) if hasattr(timeline_assembly, "assemble_timeline") \
        else inspect.getsource(timeline_assembly)
    order = [source.index(marker) for marker in ("_normalize", "_concat_clips(", "_merge_audio(", "_burn_subtitles(")]
    assert order == sorted(order)


def test_the_burn_step_itself_applies_no_scale() -> None:
    burn = inspect.getsource(timeline_assembly._burn_subtitles)          # noqa: SLF001
    assert "scale=" not in burn and "-vf" in burn and "ass=" in burn


def test_footage_and_wan_clips_are_fitted_to_1080p_in_the_media_step_not_after_assembly() -> None:
    for fn in (ffmpeg_ops.motion_loop, ffmpeg_ops.footage_to_clip, ffmpeg_ops.ken_burns):
        text = inspect.getsource(fn)
        assert "scale=" in text or "_cover(" in text or "cover" in text


def test_short_renderers_put_the_subtitle_filter_last_in_their_graph() -> None:
    for module in (shorts_render, shorts_scripted_render, news_render):
        graphs = re.findall(r'["\']([^"\']*ass=subs\.ass[^"\']*)["\']', inspect.getsource(module))
        assert graphs, f"{module.__name__}: no ass=subs.ass graph found"
        for graph in graphs:
            assert "scale=" not in graph.split("ass=subs.ass", 1)[1], f"{module.__name__}: a resize follows the subtitles"
