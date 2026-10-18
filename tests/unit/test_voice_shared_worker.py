"""voice_batch: one shared local TTS worker (one model load) across providers in a process."""

from __future__ import annotations

from pathlib import Path

import pytest

from content_farm.voice import local_clone
from content_farm.voice.local_clone import CloneReference
from content_farm.voice.local_worker import GateConfig
from content_farm.voice.qwen3_tts import Qwen3TTSProvider
from content_farm.voice.voxcpm2 import VoxCPM2Provider


def _provider(cls, tmp_path: Path, name: str):
    ref = CloneReference(tmp_path / f"{name}.wav", "參考")
    return cls(python="py", hub_dir=str(tmp_path), model="org/M", reference=ref, gate=GateConfig())


@pytest.mark.asyncio
async def test_shared_worker_reused_and_closed_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(local_clone.SHARED_ENV, "1")
    closed = []
    a = _provider(VoxCPM2Provider, tmp_path, "a")
    b = _provider(Qwen3TTSProvider, tmp_path, "b")
    assert a.worker is b.worker
    monkeypatch.setattr(a.worker, "close", lambda: closed.append(1) or _done())
    await a.aclose()
    assert closed == []
    assert await local_clone.close_shared_workers() == 1 and closed == [1]


async def _done() -> None:
    return None


def test_without_flag_each_provider_has_its_own_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(local_clone.SHARED_ENV, raising=False)
    assert _provider(VoxCPM2Provider, tmp_path, "a").worker is not _provider(VoxCPM2Provider, tmp_path, "b").worker
