"""Local cloning TTS (VoxCPM2 / Qwen3-TTS): provider, worker client, resource gate, channel wiring."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from content_farm.config import Settings
from content_farm.production import voice_source
from content_farm.production.channels import load_channel
from content_farm.production.steps import Context, RunOptions, steps_for
from content_farm.production.voice_choice import choose_voice
from content_farm.voice import local_clone
from content_farm.voice.factory import create_tts_provider, effective_tts_model, effective_voice_id
from content_farm.voice.local_clone import CloneReference
from content_farm.voice.local_worker import GateConfig, LocalWorkerError, snapshot_dir, wait_for_resources
from content_farm.voice.qwen3_tts import Qwen3TTSProvider
from content_farm.voice.voxcpm2 import VoxCPM2Provider


def _wav(path: Path, seconds: float = 0.2) -> Path:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * int(16000 * seconds))
    return path


class FakeWorker:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.loaded: list[tuple[str, dict]] = []
        self.closed = False

    async def ensure_loaded(self, op: str, **fields: str) -> None:
        self.loaded.append((op, fields))

    async def request(self, payload: dict) -> dict:
        self.requests.append(payload)
        _wav(Path(payload["out"]))
        return {"ok": True, "gen_s": 1.0, "audio_s": 0.2}

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def hub(tmp_path: Path) -> Path:
    snap = tmp_path / "hub" / "models--org--Vox" / "snapshots" / "abc"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}", encoding="utf-8")
    return tmp_path / "hub"


def test_snapshot_dir_finds_the_cached_model_and_never_downloads(hub: Path) -> None:
    assert snapshot_dir(str(hub), "org/Vox").name == "abc"
    with pytest.raises(LocalWorkerError, match="not found"):
        snapshot_dir(str(hub), "org/Missing")


@pytest.mark.asyncio
async def test_voxcpm2_clones_reference_with_seed_and_writes_mp3(tmp_path: Path, hub: Path) -> None:
    ref = CloneReference(_wav(tmp_path / "ref.wav"), "參考文字")
    worker = FakeWorker()
    provider = VoxCPM2Provider(python="py", hub_dir=str(hub), model="org/Vox", reference=ref, gate=GateConfig(),
                               seed=3, worker=worker)  # type: ignore[arg-type]
    out = tmp_path / "audio" / "scene_001.mp3"
    size = await provider.generate_speech_with_context("掃過蘆葦", output_path=out, previous_text="x", seed=11)
    assert size > 0 and out.is_file() and out.read_bytes()[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3")
    (load_op, fields), = worker.loaded
    assert load_op == "load_tts" and fields["kind"] == "voxcpm2" and fields["model_dir"].endswith("abc")
    req = worker.requests[0]
    assert (req["text"], req["ref_audio"], req["ref_text"], req["seed"]) == ("掃過蘆葦", str(ref.audio), "參考文字", 11)
    await provider.generate_speech("再一次", output_path=out)
    assert worker.requests[1]["seed"] == 3  # default seed when none is given
    await provider.aclose()
    assert worker.closed


@pytest.mark.asyncio
async def test_empty_text_is_rejected(tmp_path: Path, hub: Path) -> None:
    provider = Qwen3TTSProvider(python="py", hub_dir=str(hub), model="org/Vox", gate=GateConfig(),
                                reference=CloneReference(_wav(tmp_path / "r.wav"), "t"), worker=FakeWorker())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="empty"):
        await provider.generate_speech("  ", output_path=tmp_path / "x.mp3")


def test_reference_fingerprint_changes_with_clip_or_text(tmp_path: Path) -> None:
    clip = _wav(tmp_path / "a.wav")
    base = CloneReference(clip, "一").fingerprint()
    assert CloneReference(clip, "二").fingerprint() != base
    _wav(clip, seconds=0.3)
    assert CloneReference(clip, "一").fingerprint() != base
    with pytest.raises(ValueError):
        CloneReference(clip, " ")
    with pytest.raises(FileNotFoundError):
        CloneReference(tmp_path / "missing.wav", "一").fingerprint()


def _local_settings(test_settings: Settings, tmp_path: Path, provider: str) -> Settings:
    return test_settings.model_copy(update={
        "tts_provider": provider, "tts_ref_audio": str(_wav(tmp_path / "ref.wav")), "tts_ref_text": "參考"})


def test_factory_builds_local_providers_with_identity(test_settings: Settings, tmp_path: Path) -> None:
    vox = _local_settings(test_settings, tmp_path, "voxcpm2")
    assert isinstance(create_tts_provider(vox), VoxCPM2Provider)
    assert effective_tts_model(vox) == "mlx-community/VoxCPM2-8bit"
    assert effective_voice_id(vox).startswith("ref:")
    qwen = _local_settings(test_settings, tmp_path, "qwen3_tts")
    assert isinstance(create_tts_provider(qwen), Qwen3TTSProvider)
    assert "Qwen3-TTS" in effective_tts_model(qwen)
    with pytest.raises(ValueError, match="reference"):
        create_tts_provider(test_settings.model_copy(update={"tts_provider": "voxcpm2"}))


@pytest.mark.asyncio
async def test_resource_gate_waits_for_busy_processes_and_low_memory() -> None:
    busy = [[42], [], []]
    free = [80, 10, 60]
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    waited = await wait_for_resources(GateConfig(min_free_pct=25), probe_busy=lambda _: busy.pop(0),
                                      probe_free=lambda: free.pop(0), sleep=sleep)
    assert waited == 120 and len(slept) == 2  # busy pid, then 10% free, then open


@pytest.mark.asyncio
async def test_between_scenes_only_other_processes_count() -> None:
    def no_free_probe() -> int:
        raise AssertionError("memory is not probed between scenes")

    waited = await wait_for_resources(GateConfig(), probe_busy=lambda _: [], probe_free=no_free_probe,
                                      busy_only=True)
    assert waited == 0


@pytest.mark.asyncio
async def test_resource_gate_gives_up_after_max_wait() -> None:
    async def sleep(seconds: float) -> None:
        return None

    with pytest.raises(LocalWorkerError, match="still busy"):
        await wait_for_resources(GateConfig(max_wait_s=120), probe_busy=lambda _: [7],
                                 probe_free=lambda: 90, sleep=sleep)


@pytest.mark.parametrize(("code", "provider"), [("yokai", "voxcpm2"), ("cel", "voxcpm2"), ("offwork", "qwen3_tts")])
def test_channel_voices_follow_leons_choice(code: str, provider: str) -> None:
    voice = load_channel(code).voice
    assert voice.provider == provider and voice.voice_id_env is None
    assert voice.reference is not None and voice.reference.text.strip()


def test_chipcat_stays_on_fish() -> None:
    voice = load_channel("chipcat").voice
    assert voice.provider == "fish_audio" and voice.voice_id_env == "CF_CHIPCAT_VOICE_ID"


def test_local_provider_without_reference_is_rejected() -> None:
    base = load_channel("yokai")
    data = base.model_dump()
    data["voice"] = {"provider": "voxcpm2"}
    with pytest.raises(ValueError, match="reference"):
        type(base).model_validate(data)
    data["voice"] = {"provider": "piper", "voice_id_env": "CF_X_VOICE"}
    with pytest.raises(ValueError, match="unknown voice provider"):
        type(base).model_validate(data)


def _yokai_with_ref(tmp_path: Path, text: str = "參考文字") -> object:
    base = load_channel("yokai")
    ref = base.voice.reference.model_copy(update={"audio": str(_wav(tmp_path / "ref.wav")), "text": text})  # type: ignore[union-attr]
    return base.model_copy(update={"voice": base.voice.model_copy(update={"reference": ref})})


def test_voice_choice_passes_reference_and_pronunciation(tmp_path: Path) -> None:
    channel = _yokai_with_ref(tmp_path)
    choice = choose_voice(channel, tmp_path / "none.env", mock=False)  # type: ignore[arg-type]
    env = choice.env()
    assert env["CF_TTS_PROVIDER"] == "voxcpm2" and env["CF_TTS_REF_TEXT"] == "參考文字"
    assert env["CF_TTS_REF_AUDIO"].endswith("ref.wav") and env["CF_SPEECH_CHECK"] == "true"
    assert env["CF_PRONUNCIATION_FILE"].endswith("channels/shared/pronunciation.yaml")
    assert env["CF_CHANNEL_CODE"] == "yokai" and "CF_TTS_VOICE_ID" not in env
    described = choice.describe()
    assert "voxcpm2" in described and "ref:" in described and "pron=" in described
    other = choose_voice(_yokai_with_ref(tmp_path, "別的文字"), tmp_path / "none.env", mock=False)  # type: ignore[arg-type]
    assert other.describe() != described  # a new reference re-voices the video


def test_mock_voice_skips_reference_and_check(tmp_path: Path) -> None:
    env = choose_voice(load_channel("yokai"), tmp_path / "none.env", mock=True).env()
    assert env == {"CF_TTS_PROVIDER": "macos_say"}


def _voice_step(code: str, tmp_path: Path, **options: object):  # type: ignore[no-untyped-def]
    channel = load_channel(code)
    step = next(s for s in steps_for(channel) if s.name == "voice")
    return step, Context(channel, tmp_path, RunOptions(**options))  # type: ignore[arg-type]


def test_local_voice_is_free_but_takes_the_render_lock(tmp_path: Path) -> None:
    step, ctx = _voice_step("yokai", tmp_path)
    assert not step.paid(ctx) and step.heavy_if(ctx)
    step, ctx = _voice_step("chipcat", tmp_path)
    assert step.paid(ctx) and not step.heavy_if(ctx)
    step, ctx = _voice_step("yokai", tmp_path, mock_voice=True)
    assert not step.heavy_if(ctx)


def test_voice_source_names_local_provider_not_helpers(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "voice.log").write_text(
        "content_farm.voice.voxcpm2 INFO VoxCPM2 TTS (m): 10 chars\n"
        "content_farm.voice.local_worker INFO Local worker load_tts loaded\n"
        "content_farm.voice.checked_synthesis INFO Speech check scene_001.mp3 try 0\n", encoding="utf-8")
    assert voice_source.last_tts_provider(tmp_path) == "voxcpm2"
    assert "本機" in voice_source.provider_name("voxcpm2")
    assert not voice_source.uses_machine_voice(tmp_path)


def test_local_clone_logs_under_provider_module() -> None:
    assert VoxCPM2Provider.__module__ == "content_farm.voice.voxcpm2"
    assert local_clone.LocalCloneProvider.supports_seed
