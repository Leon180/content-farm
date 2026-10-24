"""Read-back check (whisper → CER / key terms), pronunciation table, retry loop."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.config import Settings
from content_farm.production.qc import speech_check_findings
from content_farm.voice import checked_synthesis
from content_farm.voice.checked_synthesis import CheckedSynthesizer, load_checks, record_check
from content_farm.voice.pronunciation import KeyTerm, load_table, merged_map, table_fingerprint
from content_farm.voice.speech_check import build_aliases, cer, missing_terms, normalize, number_to_zh

REPO_TABLE = Path(__file__).resolve().parents[2] / "channels" / "shared" / "pronunciation.yaml"
COWOS = KeyTerm("CoWoS", ("扣窩斯", "扣窩絲"))


@pytest.mark.parametrize(("value", "spoken"), [
    (0, "零"), (10, "十"), (12, "十二"), (20, "二十"), (105, "一百零五"), (7722, "七千七百二十二"),
    (10005, "一萬零五"), (100000, "十萬"), (120000000, "一億二千萬"),
])
def test_numbers_are_spelled_as_read(value: int, spoken: str) -> None:
    assert number_to_zh(value) == spoken


def test_normalize_unifies_variants_numbers_and_punctuation() -> None:
    assert normalize("臺積電的 7,722 mm²，約 8.8 公分") == normalize("台積電的七千七百二十二mm2約八點八公分")
    assert normalize("2024 年，60%") == "二零二四年百分之六十"
    assert normalize("霧裏") == normalize("霧裡")


def test_cer_counts_misread_characters() -> None:
    reference = "霧裡傳來九條尾巴掃過蘆葦的聲音。"
    assert cer(reference, "霧裏傳來九條尾巴掃過蘆葦的聲音") == 0
    misread = cer(reference, "母裏傳來九條尾巴走過寥婦的聲音")  # the trial's VoxCPM2 misread
    assert misread == pytest.approx(4 / 15)
    assert misread > 0.12


def test_pronunciation_spelling_heard_back_counts_as_the_display_word() -> None:
    aliases = build_aliases((COWOS,), {"蘆葦": "盧偉", "霧": "務"})
    assert cer("台積電的 CoWoS 產能。", "臺積電的扣窩絲產能", aliases) == 0
    assert cer("掃過蘆葦", "掃過盧偉", aliases) == 0
    assert cer("任務", "任務", aliases) == 0  # single-character spellings are not mapped back


def test_key_term_heard_as_homophone_passes_but_misread_fails() -> None:
    reference = "台積電的 CoWoS 產能。"
    assert missing_terms(reference, "臺積電的扣窩絲產能", (COWOS,)) == ()
    assert missing_terms(reference, "臺積電的CoWoS產能", (COWOS,)) == ()
    assert missing_terms(reference, "臺積電的Coors產能", (COWOS,)) == ("CoWoS",)
    assert missing_terms("沒有這個詞", "沒有這個詞", (COWOS,)) == ()  # only terms the scene says


def test_a_key_term_said_twice_but_heard_once_is_missing() -> None:
    eagle = KeyTerm("鷹", ())
    assert missing_terms("貓頭鷹說鷹最聰明", "貓頭鷹說鷹最聰明", (eagle,)) == ()
    assert missing_terms("貓頭鷹說鷹最聰明", "貓頭旗說鷹最聰明", (eagle,)) == ("鷹",)  # one of two heard
    assert missing_terms("貓頭鷹先認定了答案", "貓頭起先認定了答案", (eagle,)) == ("鷹",)


def _write_table(path: Path) -> Path:
    path.write_text(
        "shared: {TSMC: T S M C}\n"
        "providers:\n  voxcpm2: {蘆葦: 盧偉, TSMC: 台積}\n  fish_audio: {}\n"
        "channels:\n  yokai: {蘆葦: 蘆偉}\n"
        "key_terms:\n  - display: CoWoS\n    heard_as: [扣窩斯]\n", encoding="utf-8")
    return path


def test_table_merge_order_shared_provider_channel_script(tmp_path: Path) -> None:
    path = _write_table(tmp_path / "p.yaml")
    assert load_table(path, provider="fish_audio").mapping == {"TSMC": "T S M C"}
    assert load_table(path, provider="voxcpm2").mapping == {"TSMC": "台積", "蘆葦": "盧偉"}
    yokai = load_table(path, provider="voxcpm2", channel="yokai")
    assert yokai.mapping["蘆葦"] == "蘆偉"
    assert merged_map(yokai, {"蘆葦": "爐葦"})["蘆葦"] == "爐葦"  # the script's own map wins
    assert yokai.key_terms == (KeyTerm("CoWoS", ("扣窩斯",)),)


def test_table_fingerprint_follows_only_the_entries_in_use(tmp_path: Path) -> None:
    path = _write_table(tmp_path / "p.yaml")
    fish, vox = (table_fingerprint(path, provider=p) for p in ("fish_audio", "voxcpm2"))
    assert fish != vox
    path.write_text(path.read_text(encoding="utf-8").replace("盧偉", "廬偉"), encoding="utf-8")
    assert table_fingerprint(path, provider="fish_audio") == fish
    assert table_fingerprint(path, provider="voxcpm2") != vox


@pytest.mark.parametrize("bad", ["shared: [a, b]\n", "shared: {a: ''}\n", "key_terms: [{heard_as: [x]}]\n"])
def test_malformed_table_is_rejected(tmp_path: Path, bad: str) -> None:
    path = tmp_path / "p.yaml"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError):
        load_table(path, provider="voxcpm2")


def test_repo_table_loads_for_every_provider() -> None:
    for provider in ("fish_audio", "voxcpm2", "qwen3_tts", "elevenlabs"):
        load_table(REPO_TABLE, provider=provider, channel="yokai")
    vox = load_table(REPO_TABLE, provider="voxcpm2")
    assert vox.mapping["蘆葦"] == "盧偉" and vox.mapping["CoWoS"] == "扣窩斯"
    assert load_table(REPO_TABLE, provider="qwen3_tts").mapping["員工"] == "原工"


class FakeTTS:
    """Writes a marker file; the fake worker 'hears' whatever the queue says for each try."""
    supports_seed = True

    def __init__(self) -> None:
        self.seeds: list[int | None] = []
        self.texts: list[str] = []

    async def generate_speech_with_context(self, text: str, *, output_path: Path, previous_text=None,
                                           next_text=None, voice_id=None, seed=None) -> int:
        self.seeds.append(seed)
        self.texts.append(text)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"take {len(self.seeds) - 1}", encoding="utf-8")
        return 6


class FakeWorker:
    def __init__(self, heard: list[str]) -> None:
        self.heard = heard
        self.closed = False

    async def ensure_loaded(self, op: str, **fields: str) -> None:
        assert op == "load_asr"

    async def request(self, payload: dict) -> dict:
        assert payload["op"] == "asr" and Path(payload["file"]).is_file()
        return {"ok": True, "text": self.heard.pop(0)}

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def check_settings(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr(checked_synthesis, "snapshot_dir", lambda hub, repo: Path("/asr"))
    return test_settings.model_copy(update={"speech_check_retries": 3, "tts_seed": 5})


async def _synth(settings: Settings, heard: list[str], out: Path) -> tuple:
    tts, worker = FakeTTS(), FakeWorker(heard)
    checker = CheckedSynthesizer(tts, settings, (COWOS,), worker=worker)  # type: ignore[arg-type]
    check = await checker.synthesize(narration="台積電的 CoWoS 產能。", tts_text="台積電的扣窩斯產能。",
                                     output_path=out)
    return check, tts, worker


@pytest.mark.asyncio
async def test_misread_is_regenerated_with_new_seed_until_it_passes(check_settings: Settings, tmp_path: Path) -> None:
    out = tmp_path / "scene_001.mp3"
    check, tts, _ = await _synth(check_settings, ["臺積電的Coors產能", "臺積電的扣窩絲產能"], out)
    assert check.status == "ok" and len(check.attempts) == 2
    assert tts.seeds == [5, 5 + checked_synthesis.SEED_STEP]
    assert tts.texts == ["台積電的扣窩斯產能。"] * 2  # TTS gets the pronunciation text
    assert out.read_text(encoding="utf-8") == "take 1"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["scene_001.mp3"]  # other takes removed


@pytest.mark.asyncio
async def test_still_failing_keeps_best_take_and_warns(check_settings: Settings, tmp_path: Path) -> None:
    out = tmp_path / "scene_001.mp3"
    heard = ["臺積電的Coors產能", "臺積電的扣窩絲產什麼", "臺積電Coors", "臺積電的Cosal產能"]
    check, tts, _ = await _synth(check_settings, heard, out)
    assert len(tts.seeds) == 4  # first try + 3 re-generations, no more
    assert check.status == "warn" and check.chosen == 1  # the only take with the key term
    assert out.read_text(encoding="utf-8") == "take 1"
    record = check.to_json()
    assert record["regenerations"] == 3 and record["missing_terms"] == [] and record["cer"] > 0.12


def test_reassess_rejudges_stored_transcript_without_resynthesis(check_settings: Settings) -> None:
    fox = KeyTerm("九尾狐", ("九尾湖",))
    worker = FakeWorker([])  # any request would pop from an empty list and fail
    checker = CheckedSynthesizer(FakeTTS(), check_settings, (fox,), worker=worker)  # type: ignore[arg-type]
    stale = {"status": "warn", "cer": 0.09, "missing_terms": ["九尾狐"], "seed": 5, "regenerations": 3,
             "hypothesis": "左邊是我們熟悉的九尾湖，右邊是最早的原典"}
    updated = checker.reassess("左邊是我們熟悉的九尾狐，右邊是最早的原典。", stale)
    assert updated["status"] == "ok" and updated["missing_terms"] == [] and updated["cer"] == 0
    assert updated["regenerations"] == 3  # the history of how the take was made is kept
    assert checker.reassess("x", {"status": "ok"}) == {"status": "ok"}  # nothing to re-judge


@pytest.mark.asyncio
async def test_identical_read_back_stops_retrying(check_settings: Settings, tmp_path: Path) -> None:
    """Whisper writing 網飛 for Netflix on every seed is not fixed by another seed."""
    out = tmp_path / "scene_001.mp3"
    check, tts, _ = await _synth(check_settings, ["臺積電的Coors產能", "臺積電的Coors產能。"], out)
    assert len(tts.seeds) == 2 and check.status == "warn"


@pytest.mark.asyncio
async def test_shared_worker_is_not_closed_by_checker(check_settings: Settings) -> None:
    worker = FakeWorker([])
    checker = CheckedSynthesizer(FakeTTS(), check_settings, (), worker=worker)  # type: ignore[arg-type]
    await checker.aclose()
    assert not worker.closed


def test_check_records_merge_and_feed_qc(tmp_path: Path) -> None:
    audio = tmp_path / "audio"
    audio.mkdir()
    for n in (1, 2):
        (audio / f"scene_00{n}.mp3").write_bytes(b"x")
    ok = {"status": "ok", "cer": 0.03, "missing_terms": [], "regenerations": 1}
    record_check(audio, "scene_001.mp3", ok)
    assert speech_check_findings(tmp_path)[0].level == "ok"
    record_check(audio, "scene_002.mp3", {"status": "warn", "cer": 0.2, "missing_terms": ["CoWoS"],
                                          "regenerations": 3})
    record_check(audio, "scene_009.mp3", {"status": "warn", "cer": 0.9, "missing_terms": [], "regenerations": 3})
    assert set(load_checks(audio)) == {"scene_001.mp3", "scene_002.mp3", "scene_009.mp3"}
    (finding,) = speech_check_findings(tmp_path)
    assert finding.level == "warn" and "scene_002.mp3" in finding.message and "CoWoS" in finding.message
    assert "scene_009" not in finding.message  # stale entry for a scene no longer in the video
    assert "4 re-generation" in finding.message


@pytest.mark.asyncio
async def test_generator_applies_table_to_tts_only_and_records_checks(
    check_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    from content_farm.script_gen.schemas import Scene, Script, VisualHint
    from content_farm.voice import generator as generator_mod
    from content_farm.voice.generator import VoiceGenerator

    monkeypatch.setattr(generator_mod, "_get_audio_duration", AsyncMock(return_value=1.0))
    tts = FakeTTS()
    tts.worker = FakeWorker(["霧裏傳來九條尾巴掃過蘆葦的聲音"])  # type: ignore[attr-defined]
    settings = check_settings.model_copy(update={
        "tts_provider": "fish_audio", "pronunciation_file": str(_write_table(tmp_path / "p.yaml")),
        "channel_code": "cel", "speech_check": True})
    script = Script(video_title="t", description="d", language="zh-TW", total_duration_seconds=5, scenes=(
        Scene(scene_number=1, title="a", narration="霧裡傳來九條尾巴掃過蘆葦的聲音。TSMC",
              visual_hint=VisualHint(description="x"), duration_seconds=5),))
    tts.worker.heard = ["霧裏傳來九條尾巴掃過蘆葦的聲音TSMC"]  # type: ignore[attr-defined]
    gen = VoiceGenerator(tts=tts, settings=settings, output_dir=tmp_path / "audio")  # type: ignore[arg-type]
    gen._concat_full_audio = AsyncMock(return_value=tmp_path / "full.mp3")  # type: ignore[method-assign]
    gen._generate_subtitles = AsyncMock(return_value=tmp_path / "s.srt")  # type: ignore[method-assign]
    artifact = await gen.generate(script)
    assert tts.texts == ["霧裡傳來九條尾巴掃過蘆葦的聲音。T S M C"]  # fish_audio: shared entry only
    assert artifact.segments[0].tts_text.endswith("T S M C")
    record = load_checks(tmp_path / "audio")["scene_001.mp3"]
    assert record["status"] == "ok" and record["attempts"] == 1 and record["tts_text"].endswith("T S M C")
    assert tts.worker.closed is False  # the provider owns its worker; the checker does not close it


def test_no_check_file_means_no_finding(tmp_path: Path) -> None:
    assert speech_check_findings(tmp_path) == []
    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "speech_check.json").write_text(json.dumps({}), encoding="utf-8")
    assert speech_check_findings(tmp_path) == []
