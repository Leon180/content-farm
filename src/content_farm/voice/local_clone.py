"""Shared base for local voice-cloning TTS (VoxCPM2, Qwen3-TTS Base).

Each provider clones the channel's reference clip (``voice.reference`` in the
channel yaml: audio path + its exact transcript). Synthesis runs in the local
worker (``local_worker.LocalWorker``); the WAV it writes is encoded to MP3 here
so downstream stages see the same files as with Fish Audio.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from content_farm.voice.local_worker import GateConfig, LocalWorker, LocalWorkerError, snapshot_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CloneReference:
    audio: Path
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("voice reference text must not be empty (CF_TTS_REF_TEXT)")

    def fingerprint(self) -> str:
        """Hash of the clip's bytes and transcript: a different clip or text is a different voice."""
        if not self.audio.is_file():
            raise FileNotFoundError(f"voice reference audio not found: {self.audio} (CF_TTS_REF_AUDIO)")
        digest = hashlib.sha256(self.audio.read_bytes())
        digest.update(self.text.encode("utf-8"))
        return digest.hexdigest()[:12]


class LocalCloneProvider:
    """TTS through a local cloning model. ``kind`` names the worker's model family."""

    kind = ""
    display = ""
    supports_seed = True

    def __init__(
        self,
        *,
        python: str,
        hub_dir: str,
        model: str,
        reference: CloneReference,
        gate: GateConfig,
        ffmpeg_path: str = "ffmpeg",
        seed: int = 1,
        worker: LocalWorker | None = None,
    ) -> None:
        self._hub_dir = hub_dir
        self._model = model
        self._reference = reference
        self._ffmpeg = ffmpeg_path
        self._seed = seed
        self.worker = worker or LocalWorker(python, gate)

    @property
    def model(self) -> str:
        return self._model

    async def generate_speech(
        self,
        text: str,
        *,
        output_path: Path,
        voice_id: str | None = None,
        seed: int | None = None,
        prompt: tuple[Path, str] | None = None,
    ) -> int:
        """Synthesize ``text`` in the reference voice; writes MP3. ``voice_id`` is ignored
        (the reference clip is the voice). ``prompt`` = (audio, its text) to continue from
        (VoxCPM2 only; sentence-window re-voicing)."""
        if not text.strip():
            raise ValueError(f"{self.kind}: cannot synthesize empty text")
        model_dir = str(snapshot_dir(self._hub_dir, self._model))
        await self.worker.ensure_loaded("load_tts", kind=self.kind, model_dir=model_dir)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"cf_{self.kind}_") as tmp:
            wav = Path(tmp) / "speech.wav"
            reply = await self.worker.request({
                "op": "synth", "text": text, "ref_audio": str(self._reference.audio),
                "ref_text": self._reference.text, "seed": self._seed if seed is None else seed, "out": str(wav),
                **({"prompt_audio": str(prompt[0]), "prompt_text": prompt[1]} if prompt else {})})
            await _encode_mp3(self._ffmpeg, wav, output_path)
        byte_count = output_path.stat().st_size
        # Logged under the provider's own module (voice_source reads the provider from voice.log).
        logging.getLogger(type(self).__module__).info("%s TTS (%s): %d chars, %.1fs audio in %.1fs, seed %s -> %s", self.display, self._model,
                    len(text), reply.get("audio_s", 0), reply.get("gen_s", 0),
                    self._seed if seed is None else seed, output_path)
        return byte_count

    async def generate_speech_with_context(
        self,
        text: str,
        *,
        output_path: Path,
        previous_text: str | None = None,
        next_text: str | None = None,
        voice_id: str | None = None,
        seed: int | None = None,
    ) -> int:
        """No continuity context: each scene is cloned from the same reference clip."""
        return await self.generate_speech(text, output_path=output_path, voice_id=voice_id, seed=seed)

    async def aclose(self) -> None:
        await self.worker.close()


async def _encode_mp3(ffmpeg: str, wav: Path, output_path: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        ffmpeg, "-loglevel", "error", "-y", "-i", str(wav), "-ar", "44100", "-ac", "1",
        "-codec:a", "libmp3lame", "-b:a", "192k", str(output_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not output_path.is_file():
        detail = stderr.decode("utf-8", "replace").strip() or "(no stderr)"
        raise LocalWorkerError(f"ffmpeg could not encode {wav.name} to MP3: {detail}")
