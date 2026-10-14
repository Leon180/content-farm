"""macOS `say` TTS provider — free, local, for development and testing only.

Speech comes from the voices bundled with macOS, so it sounds robotic next to
Fish Audio / ElevenLabs. Use it to exercise the whole pipeline (whisper
alignment, timeline assembly) without spending money; do NOT publish videos
narrated with it.

External programs run via ``asyncio.create_subprocess_exec`` (no shell); the
narration text is always passed as a single argv element after ``--``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "Flo (Chinese (Taiwan))"

# One line of `say -v ?`: "<name, may contain spaces>  <locale>  # <sample>"
_VOICE_LINE = re.compile(r"^(?P<name>.+?)\s+(?P<locale>[a-z]{2,3}_[A-Za-z0-9]+)\s+#")


class MacSayError(RuntimeError):
    """The macOS `say` provider cannot run or a subprocess failed."""


def parse_voice_list(output: str) -> frozenset[str]:
    """Extract voice names from the output of ``say -v ?``."""
    names = (
        match.group("name").strip()
        for line in output.splitlines()
        if (match := _VOICE_LINE.match(line))
    )
    return frozenset(names)


class MacSayProvider:
    """TTS via macOS ``say`` → AIFF, converted to MP3 with ffmpeg."""

    def __init__(
        self,
        *,
        voice: str = DEFAULT_VOICE,
        rate: int | None = None,
        ffmpeg_path: str = "ffmpeg",
        say_path: str = "say",
    ) -> None:
        if rate is not None and rate <= 0:
            raise ValueError(f"CF_MACOS_SAY_RATE must be a positive integer, got {rate}")
        self._voice = voice
        self._rate = rate
        self._ffmpeg_path = ffmpeg_path
        self._say_path = say_path
        self._available_voices: frozenset[str] | None = None
        self._preflight_lock = asyncio.Lock()

    async def generate_speech(
        self,
        text: str,
        *,
        output_path: Path,
        voice_id: str | None = None,
    ) -> int:
        """Generate speech and save it as MP3. Returns bytes written.

        ``voice_id`` overrides the configured voice name for this call.
        """
        if not text.strip():
            raise ValueError("macos_say: cannot synthesize empty text")
        voice = voice_id or self._voice
        await self._preflight(voice)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="cf_macos_say_") as tmp:
            aiff_path = Path(tmp) / "speech.aiff"
            await _run(self._say_args(text, voice, aiff_path))
            await _run(self._ffmpeg_args(aiff_path, output_path))

        if not output_path.exists():
            raise MacSayError(f"macos_say: ffmpeg reported success but {output_path} is missing")
        byte_count = output_path.stat().st_size
        logger.info("macOS say TTS: %d bytes, %d chars -> %s", byte_count, len(text), output_path)
        return byte_count

    async def generate_speech_with_context(
        self,
        text: str,
        *,
        output_path: Path,
        previous_text: str | None = None,
        next_text: str | None = None,
        voice_id: str | None = None,
    ) -> int:
        """`say` has no continuity context; ignore neighbours."""
        return await self.generate_speech(text, output_path=output_path, voice_id=voice_id)

    def _say_args(self, text: str, voice: str, aiff_path: Path) -> list[str]:
        rate_args = ["-r", str(self._rate)] if self._rate is not None else []
        return [self._say_path, "-v", voice, *rate_args, "-o", str(aiff_path), "--", text]

    def _ffmpeg_args(self, aiff_path: Path, output_path: Path) -> list[str]:
        return [
            self._ffmpeg_path, "-loglevel", "error", "-y",
            "-i", str(aiff_path),
            "-codec:a", "libmp3lame", "-b:a", "128k",
            str(output_path),
        ]

    async def _preflight(self, voice: str) -> None:
        """Fail fast with an actionable message when the environment can't run `say`."""
        async with self._preflight_lock:
            if self._available_voices is None:
                _check_tools(self._say_path, self._ffmpeg_path)
                listing = await _run([self._say_path, "-v", "?"])
                self._available_voices = parse_voice_list(listing.decode("utf-8", "replace"))
        if voice not in self._available_voices:
            raise MacSayError(
                f"macos_say: voice {voice!r} is not installed. "
                "Run `say -v '?'` to list installed voices, set CF_MACOS_SAY_VOICE to one of them, "
                "or install it in System Settings > Accessibility > Spoken Content > "
                "System Voice > Manage Voices."
            )


def _check_tools(say_path: str, ffmpeg_path: str) -> None:
    if sys.platform != "darwin":
        raise MacSayError(
            f"macos_say only works on macOS (current platform: {sys.platform}). "
            "Set CF_TTS_PROVIDER to 'fish_audio' or 'elevenlabs' instead."
        )
    if shutil.which(say_path) is None:
        raise MacSayError(
            f"macos_say: `{say_path}` not found on PATH. It ships with macOS at /usr/bin/say; "
            "check that /usr/bin is on PATH."
        )
    if shutil.which(ffmpeg_path) is None:
        raise MacSayError(
            f"macos_say: ffmpeg not found at {ffmpeg_path!r}. "
            "Install it (`brew install ffmpeg`) or point CF_FFMPEG_PATH at the binary."
        )


async def _run(args: list[str]) -> bytes:
    """Run a subprocess without a shell; return stdout or raise MacSayError."""
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise MacSayError(f"macos_say: failed to start {args[0]!r}: {exc}") from exc
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        detail = stderr.decode("utf-8", "replace").strip() or "(no stderr)"
        raise MacSayError(
            f"macos_say: {Path(args[0]).name} exited with code {process.returncode}: {detail}"
        )
    return stdout
