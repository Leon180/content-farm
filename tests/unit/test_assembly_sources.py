"""Tests for source credits subtitle generation."""

from __future__ import annotations

from content_farm.assembly.sources import (
    build_source_srt,
    sources_duration,
)


class TestBuildSourceSrt:
    def test_single_source(self) -> None:
        srt = build_source_srt(("Wikipedia — Airplane window",))
        assert "【參考來源】" in srt
        assert "Wikipedia — Airplane window" in srt

    def test_multiple_sources(self) -> None:
        sources = ("來源A", "來源B", "來源C")
        srt = build_source_srt(sources)
        assert srt.count("-->") == 4  # 1 header + 3 sources

    def test_segment_numbering(self) -> None:
        srt = build_source_srt(("A", "B"))
        lines = srt.strip().split("\n")
        # First segment index = 1
        assert lines[0] == "1"
        # Find second segment
        assert "2\n" in srt
        assert "3\n" in srt

    def test_empty_sources(self) -> None:
        srt = build_source_srt(())
        # Only header
        assert "【參考來源】" in srt


class TestSourcesDuration:
    def test_empty(self) -> None:
        assert sources_duration(()) == 0.0

    def test_single_source(self) -> None:
        d = sources_duration(("one",))
        assert d > 0
        # header(2) + 1*3 + tail(1) = 6
        assert d == 6.0

    def test_multiple_sources(self) -> None:
        d = sources_duration(("a", "b", "c"))
        # header(2) + 3*3 + tail(1) = 12
        assert d == 12.0
