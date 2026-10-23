"""review_panels.yaml validation: hard rules live in code and reject a loosened yaml."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from content_farm.review.config import PANELS_FILE, ReviewConfig, Tier, load_review, sentence_id_field

RAW = yaml.safe_load(PANELS_FILE.read_text(encoding="utf-8"))["review"]


def _with(mutate) -> dict:
    raw = copy.deepcopy(RAW)
    mutate(raw)
    return raw


def _seat(raw: dict, stage: str, role: str) -> dict:
    return next(s for s in raw["stages"][stage]["seats"] if s["role"] == role)


def test_shipped_config_is_valid():
    config = ReviewConfig.model_validate(RAW)
    assert set(config.stages) >= {"topic", "article", "script_structure", "script_facts", "title_thumb", "media", "final"}


@pytest.mark.parametrize("stage", ["article", "script_structure", "script_facts"])
def test_fact_checker_effort_floor_is_medium(stage):
    raw = _with(lambda r: _seat(r, stage, "fact_checker").update(effort="low"))
    with pytest.raises(ValidationError, match="fact_checker is sonnet · low, below sonnet · medium"):
        ReviewConfig.model_validate(raw)
    raw = _with(lambda r: _seat(r, stage, "fact_checker").update(effort="high"))
    ReviewConfig.model_validate(raw)    # a floor, not a cap


def test_fact_checker_floor_applies_in_late_stages_too():
    def add(r):
        r["stages"]["final"]["seats"].append({"role": "fact_checker", "count": 1, "model": "sonnet", "effort": "low"})
    with pytest.raises(ValidationError, match="final: fact_checker"):
        ReviewConfig.model_validate(_with(add))


def test_shipped_defaults_are_sonnet_low_except_facts_and_the_plan_producer():
    config = ReviewConfig.model_validate(RAW)
    for name, stage in config.stages.items():
        for seat in stage.seats:
            fact = config.roles[seat.role].kind == "fact"
            assert (seat.model, seat.effort) == ("sonnet", "medium" if fact else "low"), (name, seat.role)
        if stage.arbiter is not None:
            assert (stage.arbiter.model, stage.arbiter.effort) == ("sonnet", "medium"), name
        if stage.producer is not None and name != "topic":
            assert (stage.producer.model, stage.producer.effort) == ("sonnet", "low"), name
    assert config.stages["topic"].producer.model == "opus"


@pytest.mark.parametrize("stage", ["article", "script_structure", "script_facts", "title_thumb", "media", "final"])
def test_opus_is_refused_everywhere_but_the_plan_producer(stage):
    def mutate(r):
        r["stages"][stage]["seats"][0].update(model="opus")
    with pytest.raises(ValidationError, match="opus is only allowed for the plan stage"):
        ReviewConfig.model_validate(_with(mutate))


def test_opus_arbiter_and_non_plan_producer_are_refused():
    raw = _with(lambda r: r["stages"]["article"].update(arbiter={"model": "opus", "effort": "medium"}))
    with pytest.raises(ValidationError, match="article: fact arbiter is opus"):
        ReviewConfig.model_validate(raw)
    raw = _with(lambda r: r["stages"]["script_structure"].update(producer={"model": "opus", "effort": "low"}))
    with pytest.raises(ValidationError, match="script_structure: producer agent is opus"):
        ReviewConfig.model_validate(raw)


def test_the_plan_producer_may_use_opus_but_not_haiku():
    raw = _with(lambda r: r["stages"]["topic"].update(producer={"model": "opus", "effort": "high"}))
    assert ReviewConfig.model_validate(raw).stages["topic"].producer.model == "opus"
    raw = _with(lambda r: r["stages"]["topic"].update(producer={"model": "haiku", "effort": "low"}))
    with pytest.raises(ValidationError, match="topic: producer agent is haiku"):
        ReviewConfig.model_validate(raw)


def test_required_roles_cannot_be_removed():
    raw = _with(lambda r: r["stages"]["script_structure"].update(
        seats=[s for s in r["stages"]["script_structure"]["seats"] if s["role"] != "director"]))
    with pytest.raises(ValidationError, match="script_structure: needs director ×1"):
        ReviewConfig.model_validate(raw)


def test_viewer_count_cannot_shrink():
    raw = _with(lambda r: _seat(r, "title_thumb", "viewer").update(count=3))
    with pytest.raises(ValidationError, match="title_thumb: needs viewer ×5"):
        ReviewConfig.model_validate(raw)


def test_script_needs_a_holdout_viewer():
    raw = _with(lambda r: _seat(r, "script_structure", "viewer").update(holdout=0))
    with pytest.raises(ValidationError, match="script_structure: needs 1 holdout"):
        ReviewConfig.model_validate(raw)


@pytest.mark.parametrize(("stage", "field", "value"), [
    ("script_structure", "leave_median_pct", 0.3), ("script_structure", "writer_min", 5.5),
    ("script_facts", "fact_errors_max", 1),
    ("article", "fact_errors_max", 2), ("title_thumb", "noticed_median_max", 5), ("media", "compliance_issues_max", 1),
])
def test_thresholds_cannot_loosen(stage, field, value):
    raw = _with(lambda r: r["stages"][stage]["threshold"].update({field: value}))
    with pytest.raises(ValidationError, match=rf"{field}={value}(\.0)? is looser"):
        ReviewConfig.model_validate(raw)


def test_threshold_cannot_be_dropped():
    raw = _with(lambda r: r["stages"]["script_structure"]["threshold"].pop("writer_min"))
    with pytest.raises(ValidationError, match="writer_min is required"):
        ReviewConfig.model_validate(raw)


def test_tighter_threshold_is_fine():
    raw = _with(lambda r: r["stages"]["script_structure"]["threshold"].update(writer_min=8))
    assert ReviewConfig.model_validate(raw).stages["script_structure"].threshold.writer_min == 8


def test_rounds_capped():
    """Article: 3 rounds since Leon 59fdefb32bd7 = D (was 2); a 4th is still refused."""
    assert ReviewConfig.model_validate(RAW).stages["article"].max_rounds == 3
    raw = _with(lambda r: r["stages"]["article"].update(max_rounds=4))
    with pytest.raises(ValidationError, match="article: max_rounds 4 > 3"):
        ReviewConfig.model_validate(raw)
    raw = _with(lambda r: r["stages"]["topic"].update(max_rounds=3))
    with pytest.raises(ValidationError, match="topic: max_rounds 3 > 2"):
        ReviewConfig.model_validate(raw)


def test_article_needs_an_arbiter_and_two_checkers():
    raw = _with(lambda r: r["stages"]["article"].pop("arbiter"))
    with pytest.raises(ValidationError, match="article: needs a fact arbiter"):
        ReviewConfig.model_validate(raw)
    raw = _with(lambda r: r["stages"]["article"].update(arbiter={"model": "sonnet", "effort": "low"}))
    with pytest.raises(ValidationError, match="fact arbiter is sonnet · low, below sonnet · medium"):
        ReviewConfig.model_validate(raw)
    raw = _with(lambda r: _seat(r, "article", "fact_checker").update(count=3))
    with pytest.raises(ValidationError, match="exactly 2 fact-checkers, has 3"):
        ReviewConfig.model_validate(raw)


def test_leave_median_threshold_is_the_sonnet_scale_040():
    config = ReviewConfig.model_validate(RAW)
    for name in ("script_structure", "final", "shorts_script", "shorts_final"):
        assert config.stages[name].threshold.leave_median_pct == 0.35, name


def test_missing_stage_and_unknown_role():
    raw = _with(lambda r: r["stages"].pop("media"))
    with pytest.raises(ValidationError, match="stage 'media' missing"):
        ReviewConfig.model_validate(raw)
    raw = _with(lambda r: r["stages"]["media"]["seats"].append(
        {"role": "astrologer", "count": 1, "model": "opus", "effort": "high"}))
    with pytest.raises(ValidationError, match="unknown role 'astrologer'"):
        ReviewConfig.model_validate(raw)


def test_fact_checker_must_fetch_sources():
    raw = _with(lambda r: r["roles"]["fact_checker"].update(tools=["Read"]))
    with pytest.raises(ValidationError, match="must be able to WebFetch"):
        ReviewConfig.model_validate(raw)


def _write(tmp_path: Path, review: dict) -> Path:
    path = tmp_path / "panels.yaml"
    path.write_text(yaml.safe_dump({"sentence_id_field": "sent_id", "review": review}, allow_unicode=True),
                    encoding="utf-8")
    return path


def test_channel_override_can_tighten_but_not_loosen(tmp_path):
    tighter = _with(lambda r: r.update(channels={"yokai": {"stages": {"script_structure": {"threshold": {"writer_min": 8}}}}}))
    config = load_review("yokai", path=_write(tmp_path, tighter))
    assert config.stages["script_structure"].threshold.writer_min == 8
    assert load_review("chipcat", path=_write(tmp_path, tighter)).stages["script_structure"].threshold.writer_min == 6.0
    looser = _with(lambda r: r.update(channels={"yokai": {"stages": {"script_structure": {"threshold": {"writer_min": 5}}}}}))
    with pytest.raises(ValidationError, match="writer_min=5"):
        load_review("yokai", path=_write(tmp_path, looser))


def test_raise_tier_lifts_every_seat_and_never_lowers():
    config = load_review(raise_tier=Tier(model="opus", effort="high"))
    assert config.tier_mode == "lifted"
    assert all(seat.model == "opus" and seat.effort in ("high", "xhigh", "max")
               for stage in config.stages.values() for seat in stage.seats)
    low = load_review(raise_tier=Tier(model="haiku", effort="low"))
    assert low.stages["script_structure"].seats == load_review().stages["script_structure"].seats


def test_sentence_id_field(tmp_path):
    assert sentence_id_field(_write(tmp_path, RAW)) == "sent_id"
