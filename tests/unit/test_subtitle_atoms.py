"""Numbers stay with their units and Latin/number words stay whole in subtitles."""

from __future__ import annotations

import pytest

from content_farm.subtitle.atoms import broken_atoms, is_safe_break, protected_spans
from content_farm.subtitle.estimation import EstimationProvider
from content_farm.subtitle.line_wrap import wrap_text


def atoms(text: str) -> list[str]:
    return [text[s:e] for s, e in protected_spans(text)]


class TestAtoms:
    @pytest.mark.parametrize("atom", [
        "3 奈米", "59%", "2026 年", "CoWoS-L", "HBM3E", "3.2–3.5 萬片", "1,000", "830 平方毫米",
        "171.4 億元", "US$ 1 萬", "第 3 代", "AP7", "Q2",
    ])
    def test_atom_is_found_whole(self, atom: str) -> None:
        assert atom in atoms(f"他說{atom}以上")

    def test_plain_chinese_has_no_atoms(self) -> None:
        assert atoms("卡住全世界的是時間差，不是技術差。") == []

    def test_unit_needs_a_number(self) -> None:
        # "CoWoS 年" is not a thing; only a digit glues the following unit
        assert atoms("CoWoS 年") == ["CoWoS"]

    def test_break_inside_is_unsafe_at_edges_safe(self) -> None:
        text = "在 2025 年大約"
        assert not is_safe_break(text, text.index(" 年") + 1)  # between "2025 " and "年"
        assert not is_safe_break(text, text.index("25"))       # inside 2025
        assert is_safe_break(text, text.index("2025"))
        assert is_safe_break(text, text.index("大"))

    def test_broken_atoms_detects_a_split_and_ignores_word_boundaries(self) -> None:
        text = "先進封裝在 2025 年大約占 10%。CoWoS HBM 都缺"
        assert broken_atoms(text, ["先進封裝在 2025", "年大約占 10%。CoWoS HBM 都缺"]) == ("2025 年",)
        assert broken_atoms(text, ["先進封裝在 2025 年大約占 10%。CoWoS", "HBM 都缺"]) == ()

    def test_broken_atoms_rejects_pieces_of_other_text(self) -> None:
        with pytest.raises(ValueError):
            broken_atoms("一二三", ["一二", "四"])


# Real lines from the CoWoS run that broke as "2025 / 年" at 20 chars per line.
REAL = [
    "先進封裝在 2025 年大約占台積電營收的 10%。",
    "台灣的基板廠欣興，2026 年把資本支出提高到 340 億元以上，",
    "從 2024 年底約 3.5 萬片，兩年內長到 13 萬片以上。",
    "Hopper 用的是 CoWoS-S，Blackwell 主要改用 CoWoS-L，",
    "HBM3E 疊了十二層，3 奈米的 GPU 旁邊要放八疊，頻寬才夠",
]


class TestWrapKeepsAtoms:
    @pytest.mark.parametrize("width", [13, 20, 24])  # Shorts, explainer, landscape default
    @pytest.mark.parametrize("text", REAL)
    def test_no_atom_split(self, text: str, width: int) -> None:
        lines = wrap_text(text, width).split("\n")
        assert broken_atoms(text, lines) == ()

    @pytest.mark.parametrize("width", [13, 20])
    @pytest.mark.parametrize("text", REAL)
    def test_lines_stay_within_the_soft_limit(self, text: str, width: int) -> None:
        assert all(len(line) <= width + 4 for line in wrap_text(text, width).split("\n"))

    def test_regression_2025_year(self) -> None:
        # before: "先進封裝在 2025" / "年大約占台積電營收的 10%。"
        assert wrap_text(REAL[0], 20).split("\n") == ["先進封裝在 2025 年大約占台積電營收", "的 10%。"]

    def test_hard_break_moves_before_a_word(self) -> None:
        # no punctuation or space before 13: the cut must not land inside CoWoS
        text = "一二三四五六七八九十CoWoS一二三四五"
        lines = wrap_text(text, 13).split("\n")
        assert lines[0] == "一二三四五六七八九十" and broken_atoms(text, lines) == ()

    def test_word_longer_than_the_line_stays_whole(self) -> None:
        text = "看看semiconductorpackaging這個字"
        assert "semiconductorpackaging" in wrap_text(text, 13).split("\n")

    def test_comma_inside_a_number_is_not_a_break(self) -> None:
        text = "一二三四五六七八九十每月 1,000 片的產能"
        lines = wrap_text(text, 13).split("\n")
        assert broken_atoms(text, lines) == ()

    def test_plain_chinese_unchanged_behaviour(self) -> None:
        # control: no atoms → identical to the old algorithm's choices
        assert wrap_text("覺得錄音裡的自己很陌生，很奇怪不舒服", 13).split("\n")[0].endswith("，")
        assert all(len(x) <= 13 for x in wrap_text("一二三四五六七八九十" * 2, 13).split("\n"))


class TestCueSplitKeepsAtoms:
    def test_decimal_point_is_not_a_cue_break(self) -> None:
        provider = EstimationProvider(max_chars=12, min_chars=5)
        text = "二零二四年底的月產能大約3.2到3.5萬片之間再往上"
        chunks = provider._split_text(text)  # noqa: SLF001
        assert broken_atoms(text, chunks) == ()

    @pytest.mark.parametrize("text", REAL)
    def test_real_lines(self, text: str) -> None:
        chunks = EstimationProvider()._split_text(text * 2)  # noqa: SLF001
        assert broken_atoms(text * 2, chunks) == ()
