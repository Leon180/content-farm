"""Per-orientation subtitle line width (explainer proposal §7 risk 1).

The Shorts (portrait) path must keep the original 13-char wrap; only an
explicit LANDSCAPE script gets the wider landscape limit.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from content_farm.config import Settings
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.subtitle.estimation import EstimationProvider
from content_farm.subtitle.factory import create_subtitle_provider, max_chars_per_line_for
from content_farm.subtitle.line_wrap import wrap_text
from content_farm.types import Orientation
from content_farm.voice.generator import VoiceGenerator
from content_farm.voice.schemas import AudioSegment

_LONG_LINE = "台積電的毛利率之所以能維持在五成以上，關鍵不在單一製程，而是良率、產能利用率與先進封裝一起疊加的結果。"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setenv("CF_SUBTITLE_PROVIDER", "estimation")
    monkeypatch.delenv("CF_SUBTITLE_MAX_CHARS_PER_LINE", raising=False)
    monkeypatch.delenv("CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE", raising=False)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def _wrap_of(provider: object) -> int:
    assert isinstance(provider, EstimationProvider)
    return provider._wrap_chars_per_line  # noqa: SLF001


class TestMaxCharsPerLine:
    def test_defaults(self, settings: Settings) -> None:
        assert settings.subtitle_max_chars_per_line == 13
        assert settings.subtitle_max_chars_per_line_landscape == 24

    @pytest.mark.parametrize("orientation", [None, Orientation.PORTRAIT])
    def test_portrait_and_unset_keep_shorts_width(
        self, settings: Settings, orientation: Orientation | None,
    ) -> None:
        assert max_chars_per_line_for(settings, orientation) == 13

    def test_landscape_uses_landscape_width(self, settings: Settings) -> None:
        assert max_chars_per_line_for(settings, Orientation.LANDSCAPE) == 24

    def test_env_override_is_independent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("CF_SUBTITLE_MAX_CHARS_PER_LINE", "11")
        monkeypatch.setenv("CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE", "20")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert max_chars_per_line_for(s, Orientation.PORTRAIT) == 11
        assert max_chars_per_line_for(s, Orientation.LANDSCAPE) == 20


class TestFactory:
    def test_no_orientation_argument_is_backward_compatible(self, settings: Settings) -> None:
        # Old call sites pass only settings: must still produce the Shorts width.
        assert _wrap_of(create_subtitle_provider(settings)) == 13

    def test_landscape_provider(self, settings: Settings) -> None:
        provider = create_subtitle_provider(settings, Orientation.LANDSCAPE)
        assert _wrap_of(provider) == 24

    def test_shorts_wrap_output_unchanged(self, settings: Settings) -> None:
        # Behavioural proof: the portrait wrap is byte-identical to the pre-change
        # default (wrap_text(..., 13)), and landscape produces fewer lines.
        portrait = wrap_text(_LONG_LINE, max_chars_per_line_for(settings, Orientation.PORTRAIT))
        assert portrait == wrap_text(_LONG_LINE, 13)
        landscape = wrap_text(_LONG_LINE, max_chars_per_line_for(settings, Orientation.LANDSCAPE))
        assert landscape.count("\n") < portrait.count("\n")
        assert all(len(line) <= 24 + 4 for line in landscape.split("\n"))


def _script(orientation: Orientation | None) -> Script:
    scene = Scene(
        scene_number=1,
        title="t",
        narration=_LONG_LINE,
        visual_hint=VisualHint(description="d"),
        duration_seconds=10,
    )
    kwargs = {} if orientation is None else {"orientation": orientation}
    return Script(video_title="v", description="d", scenes=(scene,), **kwargs)


class TestVoiceGeneratorPassesOrientation:
    @pytest.mark.parametrize(
        ("orientation", "expected"),
        [(None, 13), (Orientation.PORTRAIT, 13), (Orientation.LANDSCAPE, 24)],
    )
    async def test_subtitles_use_script_orientation(
        self,
        settings: Settings,
        tmp_path: Path,
        orientation: Orientation | None,
        expected: int,
    ) -> None:
        gen = VoiceGenerator(tts=AsyncMock(), settings=settings, output_dir=tmp_path / "audio")
        seg = AudioSegment(
            scene_number=1, file_path=str(tmp_path / "a.mp3"), duration_seconds=10,
            character_count=len(_LONG_LINE), tts_text=_LONG_LINE,
        )
        captured: list[int] = []

        class _FakeSubtitleGenerator:
            def __init__(self, provider: object, *_: object, **__: object) -> None:
                captured.append(_wrap_of(provider))

            async def generate(self, _: object) -> None:
                return None

        with patch("content_farm.subtitle.generator.SubtitleGenerator", _FakeSubtitleGenerator):
            await gen._generate_subtitles(_script(orientation), [seg])  # noqa: SLF001

        assert captured == [expected]
