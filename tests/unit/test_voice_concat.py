"""Tests for voice concat — mocks subprocess to verify FFmpeg command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from content_farm.voice.concat import concat_audio_files


def _mock_process(returncode: int = 0, stderr: bytes = b"") -> AsyncMock:
    proc = AsyncMock()
    proc.communicate.return_value = (b"", stderr)
    proc.returncode = returncode
    return proc


@pytest.mark.asyncio
async def test_concat_creates_output(tmp_path: Path) -> None:
    """concat_audio_files should invoke ffmpeg concat demuxer."""
    seg1 = tmp_path / "scene_001.mp3"
    seg2 = tmp_path / "scene_002.mp3"
    seg1.write_bytes(b"fake_mp3_1")
    seg2.write_bytes(b"fake_mp3_2")
    output = tmp_path / "full.mp3"

    mock_proc = _mock_process()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await concat_audio_files([seg1, seg2], output)

    assert result == output
    # Verify ffmpeg was called with concat demuxer flags
    call_args = mock_exec.call_args[0]
    assert "ffmpeg" in call_args[0]
    assert "-f" in call_args
    assert "concat" in call_args


@pytest.mark.asyncio
async def test_concat_raises_on_empty() -> None:
    """concat_audio_files should raise ValueError for empty list."""
    with pytest.raises(ValueError, match="No audio segments"):
        await concat_audio_files([], Path("/tmp/out.mp3"))


@pytest.mark.asyncio
async def test_concat_raises_on_ffmpeg_failure(tmp_path: Path) -> None:
    """concat_audio_files should raise RuntimeError on non-zero exit."""
    seg = tmp_path / "scene_001.mp3"
    seg.write_bytes(b"fake")
    output = tmp_path / "full.mp3"

    mock_proc = _mock_process(returncode=1, stderr=b"error msg")
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(RuntimeError, match="FFmpeg concat failed"):
            await concat_audio_files([seg], output)
