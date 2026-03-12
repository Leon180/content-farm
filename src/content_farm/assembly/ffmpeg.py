"""FFmpeg-based VideoComposer implementation."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from content_farm.assembly.schemas import AssemblySettings

logger = logging.getLogger(__name__)


class FFmpegComposer:
    """Composes video using the FFmpeg CLI binary."""

    def __init__(
        self,
        render_settings: AssemblySettings | None = None,
        ffmpeg_path: str = "ffmpeg",
        ffprobe_path: str = "ffprobe",
    ) -> None:
        self._s = render_settings or AssemblySettings()
        self._ffmpeg = ffmpeg_path
        self._ffprobe = ffprobe_path

    # ------------------------------------------------------------------
    # Public API (matches VideoComposer protocol)
    # ------------------------------------------------------------------

    async def compose_scene(
        self,
        *,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        target_duration: float,
    ) -> Path:
        """Combine one video clip + one audio clip into a composed scene."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        vf = (
            f"scale={self._s.width}:{self._s.height}"
            ":force_original_aspect_ratio=decrease,"
            f"pad={self._s.width}:{self._s.height}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps={self._s.fps}"
        )

        args = [
            "-y",
            "-stream_loop", "-1",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-t", f"{target_duration:.2f}",
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", self._s.preset,
            "-crf", str(self._s.crf),
            "-c:a", "aac",
            "-b:a", self._s.audio_bitrate,
            "-pix_fmt", self._s.pixel_format,
            "-shortest",
            "-movflags", "+faststart",
            str(output_path),
        ]

        await self._run_ffmpeg(args)
        return output_path

    async def concatenate(
        self,
        *,
        scene_paths: tuple[Path, ...],
        output_path: Path,
        transitions: tuple[str, ...] = (),
    ) -> Path:
        """Concatenate composed scenes using FFmpeg concat demuxer."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if transitions and any(t != "cut" for t in transitions):
            logger.warning(
                "Non-cut transitions not yet supported, falling back to cut"
            )

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        )
        try:
            for path in scene_paths:
                tmp.write(f"file '{path.resolve()}'\n")
            tmp.flush()
            tmp.close()

            args = [
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", tmp.name,
                "-c", "copy",
                "-movflags", "+faststart",
                str(output_path),
            ]

            await self._run_ffmpeg(args)
        finally:
            Path(tmp.name).unlink(missing_ok=True)

        return output_path

    async def generate_placeholder(
        self,
        *,
        output_path: Path,
        duration: float,
    ) -> Path:
        """Generate a black placeholder video with silence (C-3)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        args = [
            "-y",
            "-f", "lavfi", "-i",
            f"color=c=black:s={self._s.width}x{self._s.height}:r={self._s.fps}:d={duration:.2f}",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", f"{duration:.2f}",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac",
            "-pix_fmt", self._s.pixel_format,
            str(output_path),
        ]
        await self._run_ffmpeg(args)
        return output_path

    async def final_render(
        self,
        *,
        video_path: Path,
        output_path: Path,
        background_music_path: Path | None = None,
        music_volume: float = 0.15,
        subtitle_path: Path | None = None,
    ) -> Path:
        """Final render: burn-in subtitles via drawtext, optional background music.

        Uses FFmpeg ``drawtext`` filters (no libass needed) to bake
        SRT subtitles directly into the video frames.
        """
        from content_farm.assembly.drawtext import build_drawtext_filter

        output_path.parent.mkdir(parents=True, exist_ok=True)

        has_music = background_music_path is not None
        has_subs = subtitle_path is not None

        # Simple copy if nothing to mix
        if not has_music and not has_subs:
            args = [
                "-y",
                "-i", str(video_path),
                "-c", "copy",
                "-movflags", "+faststart",
                str(output_path),
            ]
            await self._run_ffmpeg(args)
            return output_path

        # Build drawtext filter string from SRT
        drawtext_vf = ""
        if has_subs:
            drawtext_vf = build_drawtext_filter(subtitle_path)

        args = ["-y", "-i", str(video_path)]

        if has_music:
            args.extend(["-i", str(background_music_path)])

        # --- filter_complex when music (optionally with drawtext) ---
        if has_music:
            video_chain = "[0:v]" + drawtext_vf + "[vout];" if drawtext_vf else ""
            audio_chain = (
                f"[0:a]volume=1.0[narration];"
                f"[1:a]volume={music_volume:.2f},"
                f"aloop=loop=-1:size=2000000000[music];"
                f"[narration][music]amix=inputs=2:duration=first[aout]"
            )
            fc_content = video_chain + audio_chain

            # Write to file to avoid filter-graph escaping issues
            fc_file = output_path.parent / f".fc_{output_path.stem}.txt"
            fc_file.write_text(fc_content, encoding="utf-8")
            args.extend(["-filter_complex_script", str(fc_file)])

            if drawtext_vf:
                args.extend(["-map", "[vout]", "-map", "[aout]"])
            else:
                args.extend(["-map", "0:v", "-map", "[aout]"])

            args.extend([
                "-c:v", "libx264",
                "-preset", self._s.preset,
                "-crf", str(self._s.crf),
                "-c:a", "aac",
                "-b:a", self._s.audio_bitrate,
                "-pix_fmt", self._s.pixel_format,
            ])
        elif drawtext_vf:
            # Subs only — write filter to file to avoid escaping issues
            vf_file = output_path.parent / f".vf_{output_path.stem}.txt"
            vf_file.write_text(drawtext_vf, encoding="utf-8")
            args.extend([
                "-filter_script:v", str(vf_file),
                "-c:v", "libx264",
                "-preset", self._s.preset,
                "-crf", str(self._s.crf),
                "-c:a", "copy",
                "-pix_fmt", self._s.pixel_format,
            ])

        args.extend(["-movflags", "+faststart", str(output_path)])
        await self._run_ffmpeg(args)
        return output_path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_ffmpeg(self, args: list[str]) -> None:
        """Run an FFmpeg command, raising on failure."""
        cmd = [self._ffmpeg, *args]
        logger.debug("FFmpeg command: %s", " ".join(cmd))

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            detail = stderr.decode(errors="replace")[-500:]
            raise RuntimeError(
                f"FFmpeg failed (exit {process.returncode}): {detail}"
            )
