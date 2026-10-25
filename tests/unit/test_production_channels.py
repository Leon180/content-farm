"""channels/*.yaml: the four real configs load, and bad configs fail loudly."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from content_farm.explainer.brands import brand_codes
from content_farm.production.channels import CHANNELS_DIR, Gate, Pipeline, load_all, load_channel
from content_farm.production.steps import step_names


def _raw(code: str = "chipcat") -> dict:
    return yaml.safe_load((CHANNELS_DIR / f"{code}.yaml").read_text(encoding="utf-8"))


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / f"{data['code']}.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_four_channels_each_with_own_brand() -> None:
    channels = {c.code: c for c in load_all(include_disabled=True)}
    assert set(channels) == {"chipcat", "yokai", "offwork", "cel", "technews", "ent", "deepsea", "fable"}
    assert {c.brand for c in channels.values()} == set(brand_codes())
    assert all(c.brand == c.code for c in channels.values())
    assert channels["chipcat"].name == "晶片貓"
    assert channels["yokai"].name == "怪談開談"
    assert channels["offwork"].name == "晶片貓下班了"
    assert channels["cel"].name == "賽璐璐研究室"


def test_channel_differences_are_expressed() -> None:
    channels = {c.code: c for c in load_all(include_disabled=True)}
    offwork, yokai, cel = channels["offwork"], channels["yokai"], channels["cel"]
    assert offwork.pipeline is Pipeline.SHORTS_SKIT and Gate.ARTICLE not in offwork.gates
    assert "article" not in step_names(offwork)
    assert yokai.media.artwork and yokai.media.artwork_license_required
    assert not any(c.media.source_footage for c in channels.values())
    # Leon 2026-10-17: yokai / cel / offwork use AI-generated PNGtuber packs; 晶片貓 keeps the vector rig
    # Leon 2026-10-23: yokai drops the frog (rig_ready false); its pack and frog motion profile stay on disk
    for code in ("yokai", "cel", "offwork"):
        assert channels[code].mascot.host == "pngtuber" and channels[code].mascot.ref.startswith("pngtuber/")
        assert channels[code].mascot.rig_ready == (code != "yokai")
    assert "mascot" not in step_names(yokai)
    assert "mascot" in step_names(cel) and "mascot" in step_names(channels["chipcat"])
    assert channels["chipcat"].mascot.host == "rig"


def test_mascot_step_passes_the_pngtuber_pack() -> None:
    from content_farm.production.steps import _host_args

    class Ctx:
        def __init__(self, channel):
            self.channel = channel

    channels = {c.code: c for c in load_all(include_disabled=True)}
    assert _host_args(Ctx(channels["cel"])) == ("--pngtuber", "pngtuber/paint-bottle-3d")
    assert _host_args(Ctx(channels["chipcat"])) == ()


def test_youtube_section_holds_env_names_only() -> None:
    for channel in load_all():
        for value in (channel.youtube.client_id_env, channel.youtube.client_secret_env,
                      channel.youtube.refresh_token_env, channel.youtube.channel_id_env,
                      channel.voice.voice_id_env):
            if value is None:  # local cloning voices: the reference clip is the voice, no id
                assert channel.voice.reference is not None
                continue
            assert value.isupper() and value.startswith("CF_")


def test_secret_value_instead_of_env_name_is_rejected(tmp_path: Path) -> None:
    data = _raw()
    data["youtube"]["refresh_token_env"] = "1//0gAbCdEf-secret-token"
    with pytest.raises(ValidationError, match="env var name"):
        load_channel(_write(tmp_path, data))


def test_unknown_brand_rejected(tmp_path: Path) -> None:
    data = _raw()
    data["brand"] = "neon"
    with pytest.raises(ValidationError, match="unknown brand"):
        load_channel(_write(tmp_path, data))


def test_final_gate_cannot_be_removed(tmp_path: Path) -> None:
    data = _raw()
    data["gates"] = ["article", "deck"]
    with pytest.raises(ValidationError, match="cannot be removed"):
        load_channel(_write(tmp_path, data))


def test_gate_must_exist_in_pipeline(tmp_path: Path) -> None:
    data = _raw("offwork")
    data["gates"] = ["article", "final"]
    with pytest.raises(ValidationError, match="do not exist"):
        load_channel(_write(tmp_path, data))


def test_source_footage_forbidden(tmp_path: Path) -> None:
    data = _raw("cel")
    data["media"]["source_footage"] = True
    with pytest.raises(ValidationError, match="原片"):
        load_channel(_write(tmp_path, data))


def test_file_name_must_match_code(tmp_path: Path) -> None:
    data = _raw()
    path = tmp_path / "other.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="must match code"):
        load_channel(path)


def test_unknown_field_rejected(tmp_path: Path) -> None:
    data = _raw()
    data["api_key"] = "x"
    with pytest.raises(ValidationError):
        load_channel(_write(tmp_path, data))


def test_offwork_is_disabled_and_technews_replaces_it() -> None:
    """Leon 2026-10-23: the goldfish channel is retired (kept on disk); 科技新知 takes its place, no mascot."""
    active = {c.code for c in load_all()}
    assert "offwork" not in active and {"chipcat", "yokai", "cel", "technews"} <= active
    assert load_channel("offwork").enabled is False          # still loadable: old run-dirs can be opened
    technews = load_channel("technews")
    assert technews.mascot.rig_ready is False and "mascot" not in step_names(technews)
    assert technews.voice.provider == "voxcpm2" and technews.voice.reference is not None
    assert technews.series["news"]["sources"] == ["hn", "lobsters", "arxiv", "github"]


def test_ent_is_disabled_but_loadable() -> None:
    """Leon 2026-10-24: the entertainment-news channel is retired (config, code and material kept)."""
    assert "ent" not in {c.code for c in load_all()}
    assert load_channel("ent").enabled is False
