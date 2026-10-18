"""Seam acceptance helpers (scripts/seam_check.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seam_check.py"


def _module():
    spec = importlib.util.spec_from_file_location("seam_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tone(seconds: float, sr: int = 48_000) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_hard_cut_is_a_click_a_faded_join_is_not():
    seam = _module()
    a = _tone(0.5)
    hard = np.concatenate([a[:12_011], np.zeros(4800, np.float32), a])   # cut mid-wave
    ramp = np.linspace(1, 0, 576, dtype=np.float32)
    soft = np.concatenate([a[:12_011] * np.concatenate([np.ones(12_011 - 576, np.float32), ramp]),
                           np.zeros(4800, np.float32), a * np.concatenate([ramp[::-1], np.ones(a.size - 576, np.float32)])])
    assert any(abs(t - 12_011 / 48_000) < 0.01 for t in seam.clicks(hard))
    assert seam.clicks(soft) == []


def test_subtitle_offsets_within_one_frame(tmp_path):
    seam = _module()
    a, b, c = tmp_path / "a.srt", tmp_path / "b.srt", tmp_path / "c.srt"
    a.write_text("1\n00:00:01,000 --> 00:00:02,000\n甲\n\n2\n00:00:02,500 --> 00:00:03,000\n乙\n", encoding="utf-8")
    b.write_text("1\n00:00:01,020 --> 00:00:02,000\n甲\n\n2\n00:00:02,500 --> 00:00:03,030\n乙\n", encoding="utf-8")
    c.write_text("1\n00:00:01,100 --> 00:00:02,000\n甲\n\n2\n00:00:02,500 --> 00:00:03,000\n乙\n", encoding="utf-8")
    assert seam.subtitle_check(a, b)["ok"]
    assert not seam.subtitle_check(a, c)["ok"]
