"""Semantic footage ranking (quality v5 item 5), with a fake embedder: no weights, no network."""

from __future__ import annotations

import numpy as np
import pytest

from content_farm.explainer.footage import clip_rank
from content_farm.explainer.footage.client import FootageClient
from content_farm.explainer.footage.models import FootageCandidate

MODEL = "sentence-transformers/clip-ViT-B-32-multilingual-v1"


class Fake:
    """Texts embed to a bag of three concept axes: squid, ship, sky."""

    model_id = MODEL
    AXES = ("squid", "ship", "sky")

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        return np.array([[float(word in text.lower()) + 0.01 for word in self.AXES] for text in texts])


def _cand(pid: str, title: str, **kw) -> FootageCandidate:
    base = dict(provider="nasa", provider_id=pid, title=title, page_url=f"https://x/{pid}", download_url="https://x/v.mp4",
                width=1920, height=1080, duration=30.0, author="a", author_url="", license_name="PD", license_url="")
    return FootageCandidate(**{**base, **kw})


def test_the_closest_description_to_the_sentence_moves_first() -> None:
    cands = [_cand("1", "ship at sea"), _cand("2", "giant squid in the deep"), _cand("3", "clouds in the sky")]
    order, record = clip_rank.rerank(cands, "the squid pulled the line", Fake())
    assert [c.provider_id for c in order] == ["2", "1", "3"]
    assert record["changed"] and record["picked"] == "2" and record["model_license"] == "Apache-2.0"


def test_without_a_clear_lead_the_keyword_order_stays() -> None:
    cands = [_cand("1", "squid near a ship"), _cand("2", "squid near a ship too")]
    order, record = clip_rank.rerank(cands, "a squid", Fake())
    assert [c.provider_id for c in order] == ["1", "2"] and record["changed"] is False


def test_only_the_top_n_are_reordered_and_the_tail_is_untouched() -> None:
    cands = [_cand(str(i), "ship") for i in range(4)] + [_cand("9", "squid")]
    order, _ = clip_rank.rerank(cands, "squid", Fake(), top_n=4)
    assert [c.provider_id for c in order][-1] == "9"


def test_from_env_is_off_without_weights_and_rejects_an_unchecked_model(tmp_path) -> None:
    assert clip_rank.from_env({}) is None
    assert clip_rank.from_env({clip_rank.ENV_DIR: str(tmp_path / "missing")}) is None
    with pytest.raises(clip_rank.ClipUnavailable):
        clip_rank.from_env({clip_rank.ENV_DIR: str(tmp_path), clip_rank.ENV_MODEL_ID: "some/gpl-model"})
    got = clip_rank.from_env({clip_rank.ENV_DIR: str(tmp_path)}, factory=lambda _p, _m: Fake())
    assert got is not None and clip_rank.with_embedder(None) is None


def test_every_supported_model_has_a_recorded_open_licence() -> None:
    assert {lic for lic, _ in clip_rank.MODEL_LICENSES.values()} <= {"Apache-2.0", "MIT"}


def test_the_footage_client_uses_the_ranker_and_survives_it_failing(tmp_path) -> None:
    cands = [_cand("1", "ship at sea"), _cand("2", "giant squid")]
    client = FootageClient(cache_dir=tmp_path, ranker=clip_rank.with_embedder(Fake()))
    order, record = client._semantic(cands, "squid")   # noqa: SLF001
    assert order[0].provider_id == "2" and record["changed"]
    assert client._semantic(cands, "") == (cands, None)  # noqa: SLF001  (no sentence: nothing to rank by)

    def boom(_c, _s):
        raise RuntimeError("weights corrupt")

    broken = FootageClient(cache_dir=tmp_path, ranker=boom)
    order, record = broken._semantic(cands, "squid")   # noqa: SLF001
    assert order == cands and record["changed"] is False and any("clip rank skipped" in r for r in broken.refusals)
