"""Synthesize a scene, read it back with whisper, re-generate on a misread.

Up to ``speech_check_retries`` re-generations (each with another seed when the
provider takes one; Fish Audio just samples again). The best take — fewest
missing key terms, then lowest CER — is kept; if none passes, the scene is
flagged ``warn`` in ``audio/speech_check.json`` and QC lists it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from content_farm.config import Settings
from content_farm.voice.local_worker import LocalWorker, snapshot_dir
from content_farm.voice.pronunciation import KeyTerm
from content_farm.voice.protocol import TTSProvider
from content_farm.voice.speech_check import Attempt, SceneCheck, build_aliases, choose, evaluate

logger = logging.getLogger(__name__)

CHECK_FILE = "speech_check.json"
SEED_STEP = 7919


class CheckedSynthesizer:
    def __init__(self, tts: TTSProvider, settings: Settings, terms: tuple[KeyTerm, ...],
                 worker: LocalWorker | None = None, mapping: dict[str, str] | None = None) -> None:
        from content_farm.voice.factory import gate_config

        self._tts = tts
        self._terms = terms
        self._aliases = build_aliases(terms, mapping)
        self._max_cer = settings.speech_check_max_cer
        self._retries = settings.speech_check_retries
        self._base_seed = settings.tts_seed
        self._asr_dir = str(snapshot_dir(settings.asr_hub_dir, settings.asr_model))
        shared = getattr(tts, "worker", None)
        self._worker = worker or shared or LocalWorker(settings.local_tts_python, gate_config(settings))
        self._owns_worker = worker is None and shared is None

    def _seed(self, attempt: int) -> int | None:
        return self._base_seed + attempt * SEED_STEP if getattr(self._tts, "supports_seed", False) else None

    async def transcribe(self, path: Path) -> str:
        await self._worker.ensure_loaded("load_asr", model_dir=self._asr_dir)
        reply = await self._worker.request({"op": "asr", "file": str(path)})
        return str(reply.get("text", ""))

    async def _attempt(self, index: int, *, narration: str, tts_text: str, path: Path,
                       previous_text: str | None, next_text: str | None, voice_id: str | None) -> Attempt:
        seed = self._seed(index)
        kwargs = {"seed": seed} if seed is not None else {}
        await self._tts.generate_speech_with_context(
            text=tts_text, output_path=path, previous_text=previous_text, next_text=next_text,
            voice_id=voice_id, **kwargs)
        return evaluate(narration, await self.transcribe(path), self._terms, seed, self._aliases)

    async def synthesize(self, *, narration: str, tts_text: str, output_path: Path,
                         previous_text: str | None = None, next_text: str | None = None,
                         voice_id: str | None = None) -> SceneCheck:
        attempts: list[Attempt] = []
        paths: list[Path] = []
        for index in range(self._retries + 1):
            path = output_path.with_name(f"{output_path.stem}.try{index}{output_path.suffix}")
            attempt = await self._attempt(index, narration=narration, tts_text=tts_text, path=path,
                                          previous_text=previous_text, next_text=next_text, voice_id=voice_id)
            attempts.append(attempt)
            paths.append(path)
            logger.info("Speech check %s try %d: CER %.3f missing %s", output_path.name, index, attempt.cer,
                        list(attempt.missing) or "-")
            if attempt.passes(self._max_cer):
                break
        chosen = choose(tuple(attempts))
        paths[chosen].replace(output_path)
        for index, path in enumerate(paths):
            if index != chosen:
                path.unlink(missing_ok=True)
        check = SceneCheck(tuple(attempts), chosen, self._max_cer)
        if check.status != "ok":
            logger.warning("Speech check %s still fails after %d tries (CER %.3f, missing %s); kept best take",
                           output_path.name, len(attempts), check.best.cer, list(check.best.missing))
        return check

    async def aclose(self) -> None:
        if self._owns_worker:
            await self._worker.close()


def load_checks(audio_dir: Path) -> dict[str, dict]:
    path = audio_dir / CHECK_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Ignoring unreadable %s", path)
        return {}
    return data if isinstance(data, dict) else {}


def record_check(audio_dir: Path, filename: str, record: dict) -> None:
    path = audio_dir / CHECK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    updated = {**load_checks(audio_dir), filename: record}
    path.write_text(json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
