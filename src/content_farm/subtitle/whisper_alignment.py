"""Whisper forced-alignment subtitle provider.

Uses ``stable-ts`` (which wraps Whisper) to align known narration text
to the audio file, producing accurate per-word timestamps.

Compared to the character-count estimation provider, this handles:
- Variable speaking rate within a scene
- Actual pauses in the audio
- Pronunciation_map mismatches (aligns against tts_text, displays narration)

Falls back to EstimationProvider if alignment fails (e.g. model not
available, audio corrupted).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from content_farm.subtitle.estimation import EstimationProvider
from content_farm.subtitle.line_wrap import wrap_text
from content_farm.subtitle.schemas import SubtitleSegment

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class WhisperAlignmentProvider:
    """Subtitle provider using Whisper forced alignment for accurate timing.

    Workflow per scene:
    1. Load stable-ts model (lazy, reused across scenes).
    2. Call ``model.align(audio_path, tts_text, language)`` to get
       word/character-level timestamps in audio-local seconds.
    3. Use the same chunking algorithm as EstimationProvider (break at
       punctuation, ~17 chars per subtitle line).
    4. Map each chunk's character range onto the aligned timings to
       derive start/end times.
    5. Subtitle text uses the original ``narration`` (not ``tts_text``),
       so pronunciation_map substitutions (骰子→篩子) don't appear.

    On any failure (model missing, alignment error, empty result) we
    fall back to EstimationProvider so the pipeline never crashes.
    """

    def __init__(
        self,
        *,
        model_size: str = "base",
        language: str = "zh",
        device: str = "cpu",
        compute_type: str = "int8",
        wrap_chars_per_line: int = 13,
    ) -> None:
        self._model_size = model_size
        self._language = language
        self._device = device
        self._compute_type = compute_type
        self._wrap_chars_per_line = wrap_chars_per_line
        self._model: Any = None
        self._model_load_lock = asyncio.Lock()
        self._fallback = EstimationProvider(
            wrap_chars_per_line=wrap_chars_per_line,
        )

    async def _load_model(self) -> Any:
        """Lazy-load the Whisper model on first use."""
        if self._model is not None:
            return self._model

        async with self._model_load_lock:
            if self._model is not None:
                return self._model

            logger.info(
                "Loading Whisper model (%s, device=%s, compute=%s) — first run downloads ~140MB",
                self._model_size, self._device, self._compute_type,
            )
            try:
                import stable_whisper  # type: ignore[import-not-found]
            except ImportError as exc:
                msg = (
                    "WhisperAlignmentProvider requires optional dependencies. "
                    "Install with: pip install -e '.[whisper]'"
                )
                raise RuntimeError(msg) from exc

            # stable-ts 2.17+ uses faster_whisper under the hood when loaded
            # via load_faster_whisper(). This is more memory-efficient than
            # the PyTorch-based load_model().
            loop = asyncio.get_event_loop()
            self._model = await loop.run_in_executor(
                None,
                lambda: stable_whisper.load_faster_whisper(
                    self._model_size,
                    device=self._device,
                    compute_type=self._compute_type,
                ),
            )
            logger.info("Whisper model loaded")
            return self._model

    async def generate_segments(
        self,
        text: str,
        *,
        duration_seconds: float,
        offset_seconds: float = 0.0,
        tts_text: str = "",
        audio_path: str = "",
    ) -> tuple[SubtitleSegment, ...]:
        """Align known text to audio, return timed subtitle segments."""
        if not text.strip():
            return ()

        # Required inputs for alignment
        if not audio_path or not tts_text:
            logger.warning(
                "WhisperAlignment missing audio_path or tts_text — falling back to estimation"
            )
            return await self._fallback.generate_segments(
                text,
                duration_seconds=duration_seconds,
                offset_seconds=offset_seconds,
            )

        try:
            char_timings = await self._align(audio_path, tts_text)
        except Exception:
            logger.exception(
                "Whisper alignment failed for %s — falling back to estimation",
                audio_path,
            )
            return await self._fallback.generate_segments(
                text,
                duration_seconds=duration_seconds,
                offset_seconds=offset_seconds,
            )

        if not char_timings:
            logger.warning(
                "Whisper alignment returned no timings — falling back to estimation"
            )
            return await self._fallback.generate_segments(
                text,
                duration_seconds=duration_seconds,
                offset_seconds=offset_seconds,
            )

        # Chunk the display text using the same algorithm as estimation.
        chunks = self._fallback._split_text(text)  # noqa: SLF001
        if not chunks:
            return ()

        # Map chunks (from `text`) onto char_timings (from `tts_text`).
        # Both should have similar length since pronunciation_map is
        # a 1-to-1 char substitution (骰→篩). We align by position.
        return self._map_chunks_to_timings(
            chunks=chunks,
            char_timings=char_timings,
            display_text=text,
            tts_text=tts_text,
            offset_seconds=offset_seconds,
            duration_seconds=duration_seconds,
        )

    async def _align(
        self, audio_path: str, tts_text: str,
    ) -> list[tuple[str, float, float]]:
        """Run stable-ts align and return list of (char, start, end) tuples."""
        model = await self._load_model()

        loop = asyncio.get_event_loop()

        def _do_align() -> Any:
            return model.align(
                audio_path,
                tts_text,
                language=self._language,
            )

        result = await loop.run_in_executor(None, _do_align)

        # Extract word-level (or for CJK, character-level) timings.
        # stable-ts WhisperResult exposes `.all_words()` / `.all_words_or_segments()`
        timings: list[tuple[str, float, float]] = []
        for segment in result.segments:
            words = getattr(segment, "words", None) or []
            for word in words:
                word_text = getattr(word, "word", "") or ""
                start = float(getattr(word, "start", 0.0))
                end = float(getattr(word, "end", start))
                # For Chinese, stable-ts typically returns multi-character
                # tokens; distribute evenly across the characters.
                cleaned = word_text.strip()
                if not cleaned:
                    continue
                if len(cleaned) == 1:
                    timings.append((cleaned, start, end))
                else:
                    per_char = (end - start) / len(cleaned)
                    for i, ch in enumerate(cleaned):
                        timings.append((
                            ch,
                            start + i * per_char,
                            start + (i + 1) * per_char,
                        ))
        return timings

    def _map_chunks_to_timings(
        self,
        *,
        chunks: list[str],
        char_timings: list[tuple[str, float, float]],
        display_text: str,
        tts_text: str,
        offset_seconds: float,
        duration_seconds: float,
    ) -> tuple[SubtitleSegment, ...]:
        """Map display-text chunks onto audio timings from tts_text alignment.

        We assume display_text and tts_text have similar lengths (pronunciation_map
        is typically 1-char -> 1-char). We use character position in `display_text`
        to index into `char_timings` proportionally.
        """
        # Strip whitespace from display text and map chunk positions.
        display_chars = [c for c in display_text if not c.isspace()]
        total_display_chars = len(display_chars)
        total_timing_chars = len(char_timings)

        if total_display_chars == 0 or total_timing_chars == 0:
            return ()

        # Ratio for mapping position-in-display to position-in-timings
        ratio = total_timing_chars / total_display_chars

        segments: list[SubtitleSegment] = []
        display_cursor = 0  # char index in display_text (non-whitespace)

        for i, chunk in enumerate(chunks):
            chunk_chars = [c for c in chunk if not c.isspace()]
            chunk_len = len(chunk_chars)
            if chunk_len == 0:
                continue

            start_idx = int(round(display_cursor * ratio))
            end_idx = int(round((display_cursor + chunk_len) * ratio)) - 1

            start_idx = max(0, min(start_idx, total_timing_chars - 1))
            end_idx = max(start_idx, min(end_idx, total_timing_chars - 1))

            start = char_timings[start_idx][1]  # start time of first char
            end = char_timings[end_idx][2]      # end time of last char

            segments.append(SubtitleSegment(
                index=i + 1,
                start_seconds=round(offset_seconds + start, 3),
                end_seconds=round(offset_seconds + end, 3),
                text=wrap_text(chunk.strip(), self._wrap_chars_per_line),
                scene_number=0,
            ))

            display_cursor += chunk_len

        # Clamp end of last segment to the scene duration (safety net)
        if segments:
            last = segments[-1]
            max_end = offset_seconds + duration_seconds
            if last.end_seconds > max_end:
                segments[-1] = SubtitleSegment(
                    index=last.index,
                    start_seconds=last.start_seconds,
                    end_seconds=round(max_end, 3),
                    text=last.text,
                    scene_number=last.scene_number,
                )

        from content_farm.subtitle.repair import repair_collapsed

        return repair_collapsed(segments, scene_start=offset_seconds, scene_end=offset_seconds + duration_seconds)
