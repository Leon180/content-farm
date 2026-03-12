"""Tests for FFmpegComposer — mocks subprocess to verify command construction."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from content_farm.assembly.ffmpeg import FFmpegComposer
from content_farm.assembly.schemas import AssemblySettings


@pytest.fixture
def composer() -> FFmpegComposer:
    return FFmpegComposer(
        render_settings=AssemblySettings(preset="fast", crf=20),
        ffmpeg_path="ffmpeg",
    )


def _mock_process(returncode: int = 0, stderr: bytes = b"", stdout: bytes = b"") -> AsyncMock:
    """Create a mock async process."""
    proc = AsyncMock()
    proc.communicate.return_value = (stdout, stderr)
    proc.returncode = returncode
    return proc


def _probe_stdout(duration: float) -> bytes:
    """Build fake ffprobe JSON stdout."""
    import json
    return json.dumps({"format": {"duration": str(duration)}}).encode()


@pytest.mark.asyncio
async def test_compose_scene_loops_short_video(
    composer: FFmpegComposer, tmp_path: Path,
) -> None:
    """When video is shorter than audio, it should loop."""
    video = tmp_path / "input.mp4"
    audio = tmp_path / "input.mp3"
    output = tmp_path / "output.mp4"
    video.touch()
    audio.touch()

    # Probe returns 5s video, target is 15.5s → should loop
    probe_proc = _mock_process(stdout=_probe_stdout(5.0))
    ffmpeg_proc = _mock_process()

    with patch("asyncio.create_subprocess_exec", side_effect=[probe_proc, ffmpeg_proc]) as mock_exec:
        result = await composer.compose_scene(
            video_path=video,
            audio_path=audio,
            output_path=output,
            target_duration=15.5,
        )

    assert result == output
    args = mock_exec.call_args[0]
    assert args[0] == "ffmpeg"
    assert "-stream_loop" in args
    assert "-map" in args
    assert "0:v:0" in args
    assert "1:a:0" in args
    assert "15.50" in args
    assert "libx264" in args
    assert "fast" in args
    assert "20" in args
    # No speed-up (video < audio)
    assert "setpts=PTS" in str(args)


@pytest.mark.asyncio
async def test_compose_scene_speeds_up_long_video(
    composer: FFmpegComposer, tmp_path: Path,
) -> None:
    """When video is longer than audio, it should speed up."""
    video = tmp_path / "input.mp4"
    audio = tmp_path / "input.mp3"
    output = tmp_path / "output.mp4"
    video.touch()
    audio.touch()

    # Probe returns 30s video, target is 15s → should speed up 2x
    probe_proc = _mock_process(stdout=_probe_stdout(30.0))
    ffmpeg_proc = _mock_process()

    with patch("asyncio.create_subprocess_exec", side_effect=[probe_proc, ffmpeg_proc]) as mock_exec:
        await composer.compose_scene(
            video_path=video,
            audio_path=audio,
            output_path=output,
            target_duration=15.0,
        )

    args = mock_exec.call_args[0]
    # Should NOT loop (video is longer)
    assert "-stream_loop" not in args
    # Should have speed-up in vf
    vf_str = str(args)
    assert "setpts=PTS/2.0000" in vf_str


@pytest.mark.asyncio
async def test_concatenate_creates_concat_file(
    composer: FFmpegComposer, tmp_path: Path,
) -> None:
    scene1 = tmp_path / "s1.mp4"
    scene2 = tmp_path / "s2.mp4"
    output = tmp_path / "concat.mp4"
    scene1.touch()
    scene2.touch()

    mock_proc = _mock_process()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await composer.concatenate(
            scene_paths=(scene1, scene2),
            output_path=output,
        )

    assert result == output
    args = mock_exec.call_args[0]
    assert "-f" in args
    assert "concat" in args
    assert "-c" in args
    assert "copy" in args


@pytest.mark.asyncio
async def test_final_render_copy_when_no_extras(
    composer: FFmpegComposer, tmp_path: Path,
) -> None:
    video = tmp_path / "concat.mp4"
    output = tmp_path / "final.mp4"
    video.touch()

    mock_proc = _mock_process()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        await composer.final_render(
            video_path=video,
            output_path=output,
        )

    args = mock_exec.call_args[0]
    assert "-c" in args
    assert "copy" in args
    # Should NOT have libx264 when just copying
    assert "libx264" not in args


@pytest.mark.asyncio
async def test_final_render_with_background_music(
    composer: FFmpegComposer, tmp_path: Path,
) -> None:
    video = tmp_path / "concat.mp4"
    music = tmp_path / "music.mp3"
    output = tmp_path / "final.mp4"
    video.touch()
    music.touch()

    mock_proc = _mock_process()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        await composer.final_render(
            video_path=video,
            output_path=output,
            background_music_path=music,
            music_volume=0.2,
        )

    args = mock_exec.call_args[0]
    args_list = list(args)
    assert "-filter_complex_script" in args_list
    fc_idx = args_list.index("-filter_complex_script")
    fc_file = Path(args_list[fc_idx + 1])
    filter_str = fc_file.read_text(encoding="utf-8")
    assert "amix" in filter_str
    assert "volume=0.20" in filter_str


@pytest.mark.asyncio
async def test_final_render_with_subtitles(
    composer: FFmpegComposer, tmp_path: Path,
) -> None:
    video = tmp_path / "concat.mp4"
    subs = tmp_path / "subs.srt"
    output = tmp_path / "final.mp4"
    video.touch()
    # Write a real SRT so drawtext parser has content
    subs.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nHello\n\n",
        encoding="utf-8",
    )

    mock_proc = _mock_process()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        await composer.final_render(
            video_path=video,
            output_path=output,
            subtitle_path=subs,
        )

    args = mock_exec.call_args[0]
    args_list = list(args)
    # Burns subtitles via filter_script (drawtext written to file)
    assert "-filter_script:v" in args_list
    # Must re-encode video for drawtext
    assert "libx264" in args_list
    # Audio should be copied (no music)
    ca_idx = args_list.index("-c:a")
    assert args_list[ca_idx + 1] == "copy"


@pytest.mark.asyncio
async def test_final_render_with_music_and_subtitles(
    composer: FFmpegComposer, tmp_path: Path,
) -> None:
    video = tmp_path / "concat.mp4"
    music = tmp_path / "music.mp3"
    subs = tmp_path / "subs.srt"
    output = tmp_path / "final.mp4"
    video.touch()
    music.touch()
    subs.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nTest\n\n",
        encoding="utf-8",
    )

    mock_proc = _mock_process()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        await composer.final_render(
            video_path=video,
            output_path=output,
            background_music_path=music,
            subtitle_path=subs,
        )

    args = mock_exec.call_args[0]
    args_list = list(args)
    # Filter written to file via -filter_complex_script
    assert "-filter_complex_script" in args_list
    # Verify the script file was written with drawtext + amix
    fc_idx = args_list.index("-filter_complex_script")
    fc_file = Path(args_list[fc_idx + 1])
    fc_content = fc_file.read_text(encoding="utf-8")
    assert "drawtext=" in fc_content
    assert "amix" in fc_content
    assert "[vout]" in fc_content


@pytest.mark.asyncio
async def test_ffmpeg_failure_raises(
    composer: FFmpegComposer, tmp_path: Path,
) -> None:
    video = tmp_path / "input.mp4"
    audio = tmp_path / "input.mp3"
    output = tmp_path / "output.mp4"
    video.touch()
    audio.touch()

    mock_proc = _mock_process(returncode=1, stderr=b"Error: invalid input")

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(RuntimeError, match="FFmpeg failed"):
            await composer.compose_scene(
                video_path=video,
                audio_path=audio,
                output_path=output,
                target_duration=10.0,
            )
