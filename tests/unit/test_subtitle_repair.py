"""Collapsed forced-alignment cues are spread over the silent gap before them."""

from __future__ import annotations

from content_farm.subtitle.repair import repair_collapsed
from content_farm.subtitle.schemas import SubtitleSegment


def _seg(i: int, start: float, end: float, text: str) -> SubtitleSegment:
    return SubtitleSegment(index=i, start_seconds=start, end_seconds=end, text=text, scene_number=0)


def test_collapsed_tail_is_spread_back_over_the_gap() -> None:
    segments = (_seg(1, 228.2, 232.7, "問題出在晶片設計，加上封裝裡的材料熱脹冷縮不一致，"),
                _seg(2, 242.2, 242.5, "整片翹了起來。結果 10 月，黃仁勳親口說："),
                _seg(3, 242.5, 242.5, "設計瑕疵讓良率偏低，百分之百是輝達的錯。"),
                _seg(4, 242.5, 244.9, "客戶替代工廠扛錯，是不是很少見？"))
    fixed = repair_collapsed(segments, scene_start=217.7)
    assert fixed[0] == segments[0] and fixed[3] == segments[3]
    assert abs(fixed[1].start_seconds - 232.75) < 0.01
    assert abs(fixed[2].end_seconds - 242.5) < 0.01
    for seg in fixed[1:3]:
        chars = len(seg.text.replace(" ", ""))
        assert chars / (seg.end_seconds - seg.start_seconds) < 9


def test_normal_cues_are_untouched() -> None:
    segments = (_seg(1, 0.0, 3.0, "一二三四五六七八九十"), _seg(2, 3.2, 6.0, "一二三四五六七八"))
    assert repair_collapsed(segments, scene_start=0.0) == segments
