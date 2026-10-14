"""slides → visual/ timeline namer."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from content_farm.assembly.timeline_assembly import scan_timeline_clips
from content_farm.explainer.timeline import (
    TimelineError,
    durations_from_audio,
    durations_from_voice_artifact,
    format_timestamp,
    place_slides,
    plan_slide_timeline,
)
from content_farm.voice.schemas import AudioSegment, VoiceArtifact

ROOT = Path(__file__).resolve().parents[2]


class TestFormat:
    @pytest.mark.parametrize(
        ("ms", "text"),
        [(0, "00:00.000"), (12_345, "00:12.345"), (61_005, "01:01.005"), (5_999_999, "99:59.999")],
    )
    def test_format(self, ms: int, text: str) -> None:
        assert format_timestamp(ms) == text

    @pytest.mark.parametrize("ms", [-1, 6_000_000])
    def test_out_of_range(self, ms: int) -> None:
        with pytest.raises(TimelineError):
            format_timestamp(ms)


class TestPlan:
    def test_contiguous_boundaries(self) -> None:
        clips = plan_slide_timeline([12.3, 18.75, 7.0])
        assert [c.filename for c in clips] == [
            "00:00.000~00:12.300.png",
            "00:12.300~00:31.050.png",
            "00:31.050~00:38.050.png",
        ]

    def test_no_accumulated_rounding_drift(self) -> None:
        # 30 slides of 1/3-ms-ish fractions: per-slide rounding would drift by
        # ~10 ms; cumulative rounding stays within 0.5 ms of the true total.
        durations = [10.0004] * 30
        clips = plan_slide_timeline(durations)
        assert all(a.end_ms == b.start_ms for a, b in zip(clips, clips[1:]))
        assert abs(clips[-1].end_ms - sum(durations) * 1000) <= 0.5
        naive_end = sum(round(d * 1000) for d in durations)
        assert naive_end != clips[-1].end_ms  # proves the naive way would have drifted

    @pytest.mark.parametrize("durations", [[], [1.0, 0.0], [float("nan")], [-2.0]])
    def test_rejects_bad_durations(self, durations: list[float]) -> None:
        with pytest.raises(TimelineError):
            plan_slide_timeline(durations)

    def test_rejects_videos_over_99_minutes(self) -> None:
        with pytest.raises(TimelineError):
            plan_slide_timeline([3000.0, 3000.0])


def _make_slides(slides_dir: Path, n: int) -> None:
    slides_dir.mkdir(parents=True)
    for i in range(1, n + 1):
        (slides_dir / f"slide_{i:03d}.png").write_bytes(f"png{i}".encode())


class TestPlace:
    def test_assembly_reads_back_the_same_timeline(self, tmp_path: Path) -> None:
        _make_slides(tmp_path / "slides", 3)
        clips = plan_slide_timeline([12.3456, 18.7, 7.25])
        place_slides(clips, tmp_path / "slides", tmp_path / "visual")

        parsed = scan_timeline_clips(tmp_path / "visual")
        assert [(c.start_seconds, c.end_seconds) for c in parsed] == [
            (c.start_ms / 1000, c.end_ms / 1000) for c in clips
        ]
        assert all(a.end_seconds == b.start_seconds for a, b in zip(parsed, parsed[1:]))
        assert [c.path.read_bytes() for c in parsed] == [b"png1", b"png2", b"png3"]

    def test_missing_slide(self, tmp_path: Path) -> None:
        _make_slides(tmp_path / "slides", 2)
        with pytest.raises(TimelineError, match="slide_003.png"):
            place_slides(plan_slide_timeline([1, 1, 1]), tmp_path / "slides", tmp_path / "visual")

    def test_refuses_to_mix_with_existing_timeline(self, tmp_path: Path) -> None:
        _make_slides(tmp_path / "slides", 2)
        visual = tmp_path / "visual"
        visual.mkdir()
        (visual / "00:00~00:05.mp4").write_bytes(b"old")
        (visual / "notes.txt").write_text("keep me")
        clips = plan_slide_timeline([1.5, 2.5])
        with pytest.raises(TimelineError, match="--replace"):
            place_slides(clips, tmp_path / "slides", visual)

        place_slides(clips, tmp_path / "slides", visual, replace=True)
        assert not (visual / "00:00~00:05.mp4").exists()
        assert (visual / "notes.txt").read_text() == "keep me"
        assert len(scan_timeline_clips(visual)) == 2


class TestDurationSources:
    def test_audio_uses_probe_per_scene(self, tmp_path: Path) -> None:
        for i in (1, 2):
            (tmp_path / f"scene_{i:03d}.mp3").write_bytes(b"x")
        probed = durations_from_audio(tmp_path, 2, probe=lambda p: float(p.stem[-1]) + 0.123456)
        assert probed == [1.123456, 2.123456]

    def test_audio_missing_scene(self, tmp_path: Path) -> None:
        (tmp_path / "scene_001.mp3").write_bytes(b"x")
        with pytest.raises(TimelineError, match="scene_002.mp3"):
            durations_from_audio(tmp_path, 2, probe=lambda p: 1.0)

    def test_voice_artifact(self, tmp_path: Path) -> None:
        segs = tuple(
            AudioSegment(scene_number=i, file_path=f"s{i}", duration_seconds=i * 1.5,
                         character_count=1)
            for i in (2, 1)
        )
        path = tmp_path / "voice_artifact.json"
        path.write_text(VoiceArtifact(segments=segs).model_dump_json(), encoding="utf-8")
        assert durations_from_voice_artifact(path, 2) == [1.5, 3.0]
        with pytest.raises(TimelineError):
            durations_from_voice_artifact(path, 3)


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "slides_to_visual", ROOT / "scripts/slides_to_visual.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCli:
    def _run_dir(self, tmp_path: Path) -> Path:
        from content_farm.explainer.deck import Deck
        from content_farm.explainer.to_script import deck_to_script
        from tests.unit.explainer_helpers import deck_dict

        script = deck_to_script(Deck.model_validate(deck_dict()))
        (tmp_path / "script.json").write_text(
            json.dumps(script.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8",
        )
        _make_slides(tmp_path / "slides", len(script.scenes))
        return tmp_path

    def test_auto_without_voice_refuses(self, tmp_path: Path) -> None:
        assert _load_cli().main(["--run-dir", str(self._run_dir(tmp_path))]) == 1

    def test_script_preview(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        run_dir = self._run_dir(tmp_path)
        assert _load_cli().main(["--run-dir", str(run_dir), "--source", "script"]) == 0
        assert len(scan_timeline_clips(run_dir / "visual")) == 4
        assert "estimated durations" in capsys.readouterr().err
