"""Sentence-window splice on synthetic takes (voice.splice)."""

from __future__ import annotations

import numpy as np
import pytest

from content_farm.voice.splice import SR, SpliceError, seam_jump, sentence_cuts, splice, voiced_span


def _tone(seconds: float, hz: float, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def _gap(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.float32)


def _take() -> np.ndarray:
    # 3 "sentences": 1.0 s, 2.0 s, 1.0 s of speech, 0.3 s pauses, 0.2 s lead/tail
    return np.concatenate([_gap(0.2), _tone(1.0, 200), _gap(0.3), _tone(2.0, 220), _gap(0.3),
                           _tone(1.0, 210), _gap(0.2)])


def test_cuts_land_in_the_pauses():
    cuts = sentence_cuts(_take(), [5, 10, 5])
    assert cuts[0] == 0.0 and cuts[-1] == pytest.approx(5.0, abs=0.01)
    assert cuts[1] == pytest.approx(1.35, abs=0.03)
    assert cuts[2] == pytest.approx(3.65, abs=0.03)


def test_too_few_pauses_raise():
    with pytest.raises(SpliceError):
        sentence_cuts(np.concatenate([_gap(0.2), _tone(3.0, 200), _gap(0.2)]), [3, 3])


def test_splice_keeps_neighbours_and_pause_lengths():
    old = _take()
    cuts = sentence_cuts(old, [5, 10, 5])
    new = np.concatenate([_gap(0.4), _tone(1.5, 330), _gap(0.5)])   # rewritten middle sentence
    out = splice(old, cuts, 1, 1, new)
    assert len(out) / SR == pytest.approx(5.0 - 0.5, abs=0.02)        # 2.0 s sentence became 1.5 s
    assert np.allclose(out[: int(1.2 * SR)], old[: int(1.2 * SR)], atol=1e-6)   # sentence 1 untouched
    assert np.allclose(out[-int(1.2 * SR):], old[-int(1.2 * SR):], atol=1e-6)   # sentence 3 untouched
    lo, hi = voiced_span(out[int(cuts[1] * SR): int((cuts[1] + 1.5 + 0.3) * SR)])
    assert lo == pytest.approx(0.15, abs=0.02)                         # half-pause before kept


def test_seam_metrics_see_a_pitch_jump():
    same = seam_jump(_take(), 1.35)
    jumped = np.concatenate([_gap(0.2), _tone(1.0, 200), _gap(0.3), _tone(1.0, 300), _gap(0.2)])
    big = seam_jump(jumped, 1.35)
    assert same.pitch_semitones == pytest.approx(12 * np.log2(220 / 200), abs=0.3)
    assert big.pitch_semitones == pytest.approx(12 * np.log2(300 / 200), abs=0.5)
    assert big.loudness_db < 0.5
