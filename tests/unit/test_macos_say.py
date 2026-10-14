"""Tests for the macOS `say` TTS provider (free, development/testing only)."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from content_farm.config import Settings
from content_farm.voice import macos_say
from content_farm.voice.factory import create_tts_provider
from content_farm.voice.macos_say import (
    DEFAULT_VOICE,
    MacSayError,
    MacSayProvider,
    parse_voice_list,
)
from content_farm.voice.protocol import TTSProvider

VOICE_LISTING = (
    "Albert              en_US    # Hello! My name is Albert.\n"
    "Flo (Chinese (Taiwan)) zh_TW    # 你好，我叫Flo。\n"
    "Meijia              zh_TW    # 你好，我叫美佳。\n"
    "Majed               ar_001   # مرحبًا! اسمي ماجد.\n"
).encode()


def _process(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> MagicMock:
    process = MagicMock()
    process.returncode = returncode
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    return process


class FakeExec:
    """Stands in for asyncio.create_subprocess_exec and records every argv."""

    def __init__(self, *, say_rc: int = 0, ffmpeg_rc: int = 0, stderr: bytes = b"boom") -> None:
        self.calls: list[tuple[str, ...]] = []
        self._say_rc = say_rc
        self._ffmpeg_rc = ffmpeg_rc
        self._stderr = stderr

    async def __call__(self, *args: str, **kwargs: object) -> MagicMock:
        self.calls.append(args)
        if args[1:] == ("-v", "?"):
            return _process(stdout=VOICE_LISTING)
        if "ffmpeg" in Path(args[0]).name:
            if self._ffmpeg_rc == 0:
                Path(args[-1]).write_bytes(b"ID3fake-mp3")
            return _process(self._ffmpeg_rc, stderr=self._stderr)
        return _process(self._say_rc, stderr=self._stderr)


@pytest.fixture
def fake_exec(monkeypatch: pytest.MonkeyPatch) -> FakeExec:
    fake = FakeExec()
    monkeypatch.setattr(macos_say.asyncio, "create_subprocess_exec", fake)
    monkeypatch.setattr(macos_say.sys, "platform", "darwin")
    monkeypatch.setattr(macos_say.shutil, "which", lambda name: f"/usr/bin/{name}")
    return fake


class TestParseVoiceList:
    def test_names_with_spaces_and_parentheses(self) -> None:
        voices = parse_voice_list(VOICE_LISTING.decode())
        assert voices == {"Albert", "Flo (Chinese (Taiwan))", "Meijia", "Majed"}

    def test_ignores_garbage_lines(self) -> None:
        assert parse_voice_list("\nnot a voice line\n") == frozenset()


class TestGenerateSpeech:
    def test_conforms_to_protocol(self) -> None:
        assert isinstance(MacSayProvider(), TTSProvider)

    async def test_argv_and_output(self, fake_exec: FakeExec, tmp_path: Path) -> None:
        provider = MacSayProvider(ffmpeg_path="/opt/ffmpeg")
        out = tmp_path / "audio" / "scene_001.mp3"

        written = await provider.generate_speech("台積電 $(rm -rf ~); 賺什麼", output_path=out)

        assert written == out.stat().st_size == len(b"ID3fake-mp3")
        listing, say, ffmpeg = fake_exec.calls
        assert listing == ("say", "-v", "?")
        assert say[:3] == ("say", "-v", DEFAULT_VOICE)
        assert say[-2:] == ("--", "台積電 $(rm -rf ~); 賺什麼")  # one argv element, no shell
        assert "-r" not in say
        aiff = say[say.index("-o") + 1]
        assert aiff.endswith(".aiff")
        assert ffmpeg[0] == "/opt/ffmpeg"
        assert ffmpeg[ffmpeg.index("-i") + 1] == aiff
        assert ffmpeg[-1] == str(out)
        assert not Path(aiff).parent.exists()  # temp dir cleaned up

    async def test_rate_and_voice_override(self, fake_exec: FakeExec, tmp_path: Path) -> None:
        provider = MacSayProvider(voice="Meijia", rate=180)
        await provider.generate_speech("你好", output_path=tmp_path / "a.mp3")
        say = fake_exec.calls[1]
        assert say[1:5] == ("-v", "Meijia", "-r", "180")

        await provider.generate_speech("你好", output_path=tmp_path / "b.mp3", voice_id="Albert")
        assert fake_exec.calls[-2][2] == "Albert"

    async def test_voice_listing_is_cached(self, fake_exec: FakeExec, tmp_path: Path) -> None:
        provider = MacSayProvider()
        await provider.generate_speech("一", output_path=tmp_path / "1.mp3")
        await provider.generate_speech("二", output_path=tmp_path / "2.mp3")
        listings = [c for c in fake_exec.calls if c[1:] == ("-v", "?")]
        assert len(listings) == 1

    async def test_with_context_ignores_neighbours(
        self, fake_exec: FakeExec, tmp_path: Path
    ) -> None:
        provider = MacSayProvider()
        await provider.generate_speech_with_context(
            "中間", output_path=tmp_path / "m.mp3", previous_text="前", next_text="後"
        )
        assert fake_exec.calls[1][-1] == "中間"


class TestErrors:
    async def test_not_macos(self, fake_exec: FakeExec, monkeypatch: pytest.MonkeyPatch,
                             tmp_path: Path) -> None:
        monkeypatch.setattr(macos_say.sys, "platform", "linux")
        with pytest.raises(MacSayError, match="only works on macOS.*CF_TTS_PROVIDER"):
            await MacSayProvider().generate_speech("你好", output_path=tmp_path / "x.mp3")
        assert fake_exec.calls == []

    async def test_say_missing(self, fake_exec: FakeExec, monkeypatch: pytest.MonkeyPatch,
                               tmp_path: Path) -> None:
        monkeypatch.setattr(
            macos_say.shutil, "which", lambda name: None if name == "say" else "/x/" + name
        )
        with pytest.raises(MacSayError, match="`say` not found.*/usr/bin/say"):
            await MacSayProvider().generate_speech("你好", output_path=tmp_path / "x.mp3")

    async def test_ffmpeg_missing(self, fake_exec: FakeExec, monkeypatch: pytest.MonkeyPatch,
                                  tmp_path: Path) -> None:
        monkeypatch.setattr(
            macos_say.shutil, "which", lambda name: None if name == "ffmpeg" else "/x/" + name
        )
        with pytest.raises(MacSayError, match="ffmpeg not found.*brew install ffmpeg.*CF_FFMPEG_PATH"):
            await MacSayProvider().generate_speech("你好", output_path=tmp_path / "x.mp3")

    async def test_unknown_voice(self, fake_exec: FakeExec, tmp_path: Path) -> None:
        provider = MacSayProvider(voice="Nope")
        with pytest.raises(MacSayError, match="'Nope' is not installed.*CF_MACOS_SAY_VOICE"):
            await provider.generate_speech("你好", output_path=tmp_path / "x.mp3")
        assert all(c[1:] == ("-v", "?") for c in fake_exec.calls)  # never synthesized

    async def test_say_fails(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        fake = FakeExec(say_rc=1, stderr=b"Open speech channel failed")
        monkeypatch.setattr(macos_say.asyncio, "create_subprocess_exec", fake)
        monkeypatch.setattr(macos_say.sys, "platform", "darwin")
        monkeypatch.setattr(macos_say.shutil, "which", lambda name: name)
        with pytest.raises(MacSayError, match="say exited with code 1: Open speech channel failed"):
            await MacSayProvider().generate_speech("你好", output_path=tmp_path / "x.mp3")

    async def test_ffmpeg_fails(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        fake = FakeExec(ffmpeg_rc=1, stderr=b"Unknown encoder 'libmp3lame'")
        monkeypatch.setattr(macos_say.asyncio, "create_subprocess_exec", fake)
        monkeypatch.setattr(macos_say.sys, "platform", "darwin")
        monkeypatch.setattr(macos_say.shutil, "which", lambda name: name)
        with pytest.raises(MacSayError, match="ffmpeg exited with code 1: Unknown encoder"):
            await MacSayProvider().generate_speech("你好", output_path=tmp_path / "x.mp3")

    async def test_executable_cannot_start(self, monkeypatch: pytest.MonkeyPatch,
                                           tmp_path: Path) -> None:
        async def raise_oserror(*args: str, **kwargs: object) -> None:
            raise PermissionError("denied")

        monkeypatch.setattr(macos_say.asyncio, "create_subprocess_exec", raise_oserror)
        monkeypatch.setattr(macos_say.sys, "platform", "darwin")
        monkeypatch.setattr(macos_say.shutil, "which", lambda name: name)
        with pytest.raises(MacSayError, match="failed to start 'say'"):
            await MacSayProvider().generate_speech("你好", output_path=tmp_path / "x.mp3")

    async def test_empty_text(self, fake_exec: FakeExec, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="empty text"):
            await MacSayProvider().generate_speech("  ", output_path=tmp_path / "x.mp3")
        assert fake_exec.calls == []

    def test_non_positive_rate(self) -> None:
        with pytest.raises(ValueError, match="CF_MACOS_SAY_RATE"):
            MacSayProvider(rate=0)


class TestFactory:
    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("CF_TTS_PROVIDER", "macos_say")
        monkeypatch.delenv("CF_MACOS_SAY_VOICE", raising=False)
        monkeypatch.delenv("CF_MACOS_SAY_RATE", raising=False)

    def test_creates_with_defaults(self) -> None:
        provider = create_tts_provider(Settings(_env_file=None))  # type: ignore[call-arg]
        assert isinstance(provider, MacSayProvider)
        assert provider._voice == DEFAULT_VOICE
        assert provider._rate is None

    def test_reads_voice_rate_and_ffmpeg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_MACOS_SAY_VOICE", "Meijia")
        monkeypatch.setenv("CF_MACOS_SAY_RATE", "220")
        monkeypatch.setenv("CF_FFMPEG_PATH", "/opt/homebrew/bin/ffmpeg")
        provider = create_tts_provider(Settings(_env_file=None))  # type: ignore[call-arg]
        assert isinstance(provider, MacSayProvider)
        assert (provider._voice, provider._rate, provider._ffmpeg_path) == (
            "Meijia", 220, "/opt/homebrew/bin/ffmpeg"
        )

    def test_needs_no_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_FISH_AUDIO_API_KEY", "")
        monkeypatch.setenv("CF_ELEVENLABS_API_KEY", "")
        provider = create_tts_provider(Settings(_env_file=None))  # type: ignore[call-arg]
        assert isinstance(provider, MacSayProvider)

    def test_invalid_rate_rejected_by_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_MACOS_SAY_RATE", "0")
        with pytest.raises(ValueError, match="macos_say_rate"):
            Settings(_env_file=None)  # type: ignore[call-arg]


_HAS_SAY = sys.platform == "darwin" and shutil.which("say") is not None
_HAS_FFMPEG = shutil.which("ffmpeg") is not None
_HAS_VOICE = _HAS_SAY and DEFAULT_VOICE in parse_voice_list(
    subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=False).stdout
    if _HAS_SAY else ""
)


@pytest.mark.skipif(not (_HAS_SAY and _HAS_FFMPEG and _HAS_VOICE),
                    reason="needs macOS `say`, ffmpeg and the default zh-TW voice")
async def test_real_say_produces_mp3(tmp_path: Path) -> None:
    out = tmp_path / "hello.mp3"
    written = await MacSayProvider().generate_speech("你好，這是測試。", output_path=out)

    assert written == out.stat().st_size > 0
    probe = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "format=duration,format_name",
        "-of", "default=nw=1", str(out),
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await probe.communicate()
    info = dict(line.split("=", 1) for line in stdout.decode().split())
    assert info["format_name"] == "mp3"
    assert 0.3 < float(info["duration"]) < 10
