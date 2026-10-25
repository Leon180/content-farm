"""Semantic ranking of footage candidates against the narration (quality v5 item 5).

Keyword matching says a clip's page *mentions* "squid"; it cannot tell that the sentence being spoken is about a squid
losing a tentacle in a fight. A CLIP-style model embeds the spoken sentence and each candidate's description into one
space, and the closest candidate wins among the ones that already passed the licence / no-faces screen and the keyword
match. (The retrieval-by-CLIP idea is OpenMontage's; the code is ours.)

The embedder is local and offline. Supported weights (licence checked 2026-10 on each model card; record the one you use):

* ``sentence-transformers/clip-ViT-B-32-multilingual-v1`` - Apache-2.0; text tower for 50+ languages incl. Chinese,
  aligned to OpenAI CLIP ViT-B/32, so a Chinese narration sentence can be compared with English clip descriptions.
* ``openai/clip-vit-base-patch32`` - MIT (English only).

Set ``CF_CLIP_MODEL_DIR`` to a local copy of the weights and install ``sentence-transformers`` to switch it on; without
them :func:`from_env` returns None and the keyword order stays (nothing is downloaded by this code). Candidate
descriptions are embedded as text (the providers give no frames before the download; frame embedding is the same
interface, ``embed_images``, for a later step that has the file).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from content_farm.explainer.footage.models import FootageCandidate

MODEL_LICENSES = {
    "sentence-transformers/clip-ViT-B-32-multilingual-v1": ("Apache-2.0", "https://huggingface.co/sentence-transformers/clip-ViT-B-32-multilingual-v1"),
    "openai/clip-vit-base-patch32": ("MIT", "https://huggingface.co/openai/clip-vit-base-patch32"),
}
ENV_DIR = "CF_CLIP_MODEL_DIR"
ENV_MODEL_ID = "CF_CLIP_MODEL_ID"            # which of MODEL_LICENSES the directory holds (recorded with each ranking)
TOP_N = 6                                     # only the best keyword matches are re-ordered
MIN_MARGIN = 0.02                             # a semantic lead smaller than this keeps the keyword order


class ClipUnavailable(RuntimeError):
    """The local model cannot be used; the keyword ranking stays."""


class TextEmbedder(Protocol):
    model_id: str

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """(n, d) float array, any scale (rows are normalised here)."""
        ...


@dataclass(frozen=True)
class Ranked:
    candidate: FootageCandidate
    score: float


def _unit(rows: np.ndarray) -> np.ndarray:
    rows = np.asarray(rows, dtype=np.float32)
    return rows / np.maximum(np.linalg.norm(rows, axis=1, keepdims=True), 1e-9)


def candidate_description(c: FootageCandidate) -> str:
    return " ".join(f"{c.title}. {c.description} {c.tags}".split())[:400]


def score(sentence: str, candidates: list[FootageCandidate], embedder: TextEmbedder) -> list[Ranked]:
    """Cosine similarity of the sentence to each candidate's description, best first (stable on ties)."""
    if not candidates or not sentence.strip():
        return [Ranked(c, 0.0) for c in candidates]
    vectors = _unit(embedder.embed_texts([sentence, *map(candidate_description, candidates)]))
    sims = vectors[1:] @ vectors[0]
    order = sorted(range(len(candidates)), key=lambda i: -float(sims[i]))
    return [Ranked(candidates[i], float(sims[i])) for i in order]


def rerank(candidates: list[FootageCandidate], sentence: str, embedder: TextEmbedder,
           *, top_n: int = TOP_N, margin: float = MIN_MARGIN) -> tuple[list[FootageCandidate], dict]:
    """Move the semantically closest of the first ``top_n`` candidates to the front; the rest keep their order.

    Returns the new order and a record (model, licence, scores, whether the order changed) for the sidecar / report."""
    head, tail = candidates[:top_n], candidates[top_n:]
    if len(head) < 2:
        return candidates, {"model": embedder.model_id, "changed": False, "reason": "fewer than two candidates"}
    ranked = score(sentence, head, embedder)
    first_score = next(r.score for r in ranked if r.candidate is head[0])
    best = ranked[0]
    scores = {r.candidate.provider_id: round(r.score, 4) for r in ranked}
    licence = MODEL_LICENSES.get(embedder.model_id, ("unknown", ""))[0]
    record = {"model": embedder.model_id, "model_license": licence, "scores": scores}
    if best.candidate is head[0] or best.score - first_score < margin:
        return candidates, {**record, "changed": False, "reason": "keyword order kept (no clear semantic lead)"}
    reordered = [best.candidate, *(c for c in head if c is not best.candidate), *tail]
    return reordered, {**record, "changed": True, "picked": best.candidate.provider_id,
                       "was_first": head[0].provider_id}


class SentenceTransformersEmbedder:
    """The local CLIP-family text tower through ``sentence-transformers`` (imported lazily)."""

    def __init__(self, model_dir: Path, model_id: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer   # noqa: PLC0415
        except ImportError as exc:                                   # pragma: no cover - depends on the machine
            raise ClipUnavailable("sentence-transformers is not installed") from exc
        self.model_id = model_id
        self._model = SentenceTransformer(str(model_dir), device="cpu")

    def embed_texts(self, texts: list[str]) -> np.ndarray:           # pragma: no cover - needs the weights
        return np.asarray(self._model.encode(texts, convert_to_numpy=True))


def from_env(env: Mapping[str, str] = os.environ,
             factory: Callable[[Path, str], TextEmbedder] = SentenceTransformersEmbedder) -> TextEmbedder | None:
    """The configured embedder, or None when ``CF_CLIP_MODEL_DIR`` is unset / missing (keyword ranking stays)."""
    directory = env.get(ENV_DIR, "").strip()
    if not directory:
        return None
    path = Path(directory).expanduser()
    if not path.is_dir():
        return None
    model_id = env.get(ENV_MODEL_ID, "sentence-transformers/clip-ViT-B-32-multilingual-v1")
    if model_id not in MODEL_LICENSES:
        raise ClipUnavailable(f"{ENV_MODEL_ID}={model_id!r} is not a checked model; known: {', '.join(MODEL_LICENSES)}")
    try:
        return factory(path, model_id)
    except ClipUnavailable:
        return None


def with_embedder(embedder: TextEmbedder | None) -> Callable[[list[FootageCandidate], str], tuple[list[FootageCandidate], dict]] | None:
    """A ``FootageClient`` ranker bound to ``embedder`` (None stays None)."""
    if embedder is None:
        return None
    return lambda candidates, sentence: rerank(candidates, sentence, embedder)


__all__ = ["ClipUnavailable", "MODEL_LICENSES", "Ranked", "from_env", "rerank", "score", "with_embedder"]
