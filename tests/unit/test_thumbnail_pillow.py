"""Tests for PillowProvider — thumbnail rendering."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image, ImageDraw, ImageFont

from content_farm.thumbnail.pillow_provider import (
    PillowProvider,
    _create_gradient,
    _measure_text,
    _parse_hex,
    _wrap_text_by_pixel,
)
from content_farm.thumbnail.schemas import ThumbnailSettings


class TestParseHex:
    def test_standard_color(self) -> None:
        assert _parse_hex("#FF0000") == (255, 0, 0)

    def test_without_hash(self) -> None:
        assert _parse_hex("00FF00") == (0, 255, 0)

    def test_mixed_case(self) -> None:
        assert _parse_hex("#aaBBcc") == (170, 187, 204)

    def test_black(self) -> None:
        assert _parse_hex("#000000") == (0, 0, 0)

    def test_white(self) -> None:
        assert _parse_hex("#FFFFFF") == (255, 255, 255)


def _make_draw() -> tuple[Image.Image, ImageDraw.Draw, ImageFont.ImageFont]:
    """Create a dummy draw context for pixel-based wrap tests."""
    img = Image.new("RGB", (1280, 720))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    return img, draw, font


class TestWrapTextByPixel:
    def test_short_text_no_wrap(self) -> None:
        _, draw, font = _make_draw()
        result = _wrap_text_by_pixel("短標題", font, draw, max_width=1200)
        assert result == ["短標題"]

    def test_empty_text(self) -> None:
        _, draw, font = _make_draw()
        assert _wrap_text_by_pixel("", font, draw, max_width=1200) == []

    def test_long_text_wraps(self) -> None:
        _, draw, font = _make_draw()
        text = "這是一個非常非常長的中文影片標題需要被換行顯示在縮圖上面才行"
        # Use a narrow width to force wrapping
        lines = _wrap_text_by_pixel(text, font, draw, max_width=80)
        assert len(lines) >= 2
        # All chars preserved
        assert "".join(lines) == text

    def test_prefers_punctuation_break(self) -> None:
        _, draw, font = _make_draw()
        text = "前半段的文字內容，後半段的文字內容繼續"
        # Width that fits ~10 chars but not all
        char_w = _measure_text(draw, "字", font)
        lines = _wrap_text_by_pixel(text, font, draw, max_width=char_w * 10)
        assert len(lines) >= 2
        assert "，" in lines[0]

    def test_single_line_fits(self) -> None:
        _, draw, font = _make_draw()
        text = "短"
        result = _wrap_text_by_pixel(text, font, draw, max_width=9999)
        assert result == ["短"]


class TestCreateGradient:
    def test_correct_dimensions(self) -> None:
        s = ThumbnailSettings(width=1280, height=720)
        img = _create_gradient(s)
        assert img.size == (1280, 720)
        assert img.mode == "RGB"

    def test_custom_dimensions(self) -> None:
        s = ThumbnailSettings(width=640, height=360)
        img = _create_gradient(s)
        assert img.size == (640, 360)

    def test_top_bottom_colors_differ(self) -> None:
        s = ThumbnailSettings(
            background_color="#FF0000",
            gradient_end_color="#0000FF",
        )
        img = _create_gradient(s)
        top_pixel = img.getpixel((0, 0))
        bottom_pixel = img.getpixel((0, 719))
        assert top_pixel[0] > top_pixel[2]      # more red at top
        assert bottom_pixel[2] > bottom_pixel[0]  # more blue at bottom


class TestPillowProviderRender:
    @pytest.mark.asyncio
    async def test_render_gradient_produces_jpeg(self, tmp_path: Path) -> None:
        provider = PillowProvider()
        output = tmp_path / "thumb.jpg"
        s = ThumbnailSettings(font_size=20)  # small for speed

        file_size = await provider.render(
            title="測試標題",
            output_path=output,
            settings=s,
        )

        assert output.exists()
        assert file_size > 0
        img = Image.open(output)
        assert img.size == (1280, 720)
        assert img.format == "JPEG"

    @pytest.mark.asyncio
    async def test_render_with_missing_video_falls_back(
        self, tmp_path: Path,
    ) -> None:
        provider = PillowProvider()
        output = tmp_path / "thumb.jpg"
        fake_video = tmp_path / "nonexistent.mp4"

        file_size = await provider.render(
            title="Fallback",
            output_path=output,
            video_path=fake_video,
            settings=ThumbnailSettings(font_size=20),
        )

        assert output.exists()
        assert file_size > 0

    @pytest.mark.asyncio
    async def test_render_creates_output_directory(
        self, tmp_path: Path,
    ) -> None:
        provider = PillowProvider()
        output = tmp_path / "subdir" / "deep" / "thumb.jpg"

        await provider.render(
            title="Test",
            output_path=output,
            settings=ThumbnailSettings(font_size=20),
        )

        assert output.exists()

    @pytest.mark.asyncio
    async def test_render_with_mocked_keyframe(self, tmp_path: Path) -> None:
        """Test keyframe path by mocking FFmpeg subprocess."""
        provider = PillowProvider()
        output = tmp_path / "thumb.jpg"

        # Create a fake video file
        video = tmp_path / "video.mp4"
        video.touch()

        # Mock the keyframe extraction to return a gradient
        with patch.object(
            provider, "_extract_keyframe",
            return_value=_create_gradient(ThumbnailSettings()),
        ):
            file_size = await provider.render(
                title="Keyframe Test",
                output_path=output,
                video_path=video,
                settings=ThumbnailSettings(font_size=20),
            )

        assert output.exists()
        assert file_size > 0

    @pytest.mark.asyncio
    async def test_render_under_2mb(self, tmp_path: Path) -> None:
        """YouTube thumbnail limit is 2MB."""
        provider = PillowProvider()
        output = tmp_path / "thumb.jpg"

        file_size = await provider.render(
            title="YouTube限制測試",
            output_path=output,
            settings=ThumbnailSettings(quality=85),
        )

        assert file_size < 2 * 1024 * 1024  # under 2MB
