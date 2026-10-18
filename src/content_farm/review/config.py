"""The ``review:`` section of ``channels/shared/review_panels.yaml``, validated against rules
that live here in code so that no prompt, memory or edited yaml can loosen them (Leon 2026-10-18):

- every stage keeps at least its required reviewers (``REQUIRED_ROLES``);
- fact-checkers are opus · high in every stage; every role meets its tier floor (``TIER_FLOOR``);
- thresholds cannot be looser than ``THRESHOLD_FLOOR``, rounds not more than ``MAX_ROUNDS``.

Channels may override a stage (``review.channels.<code>.stages.<stage>``); the merged result is
validated again, so an override can raise a tier or tighten a threshold but never lower one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

PANELS_FILE = Path(__file__).resolve().parents[3] / "channels" / "shared" / "review_panels.yaml"

Model = Literal["haiku", "sonnet", "opus"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]
MODEL_RANK = {"haiku": 0, "sonnet": 1, "opus": 2}
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}

LONG_STAGES = ("topic", "article", "script", "title_thumb", "media", "final")
SHORT_STAGES = ("shorts_topic", "shorts_script", "shorts_title", "shorts_final")
STAGES = LONG_STAGES + SHORT_STAGES

# Minimum reviewers per stage (design page Q6ug8VB3rWc6fBLtorKi6r). viewer counts include the holdout.
REQUIRED_ROLES: dict[str, dict[str, int]] = {
    "topic": {"viewer": 3, "writer_story": 1, "producer": 1},
    "article": {"fact_checker": 2, "writer_story": 1},
    "script": {"viewer": 5, "writer_story": 1, "writer_density": 1, "director": 1, "fact_checker": 1},
    "title_thumb": {"viewer": 5, "designer": 1, "producer": 1},
    "media": {"compliance": 1},
    "final": {"viewer": 5, "editor_visual": 1, "editor_audio": 1, "director": 1},
    "shorts_topic": {"viewer": 3},
    "shorts_script": {"viewer": 3, "writer_story": 1},
    "shorts_title": {"viewer": 3},
    "shorts_final": {"viewer": 3, "editor_visual": 1},
}
REQUIRED_HOLDOUT = {"script": 1, "final": 1}

# (model, effort) floors per stage × role (Leon 2026-10-18 table). "*" = any role in that stage.
TIER_FLOOR: dict[str, dict[str, tuple[Model, Effort]]] = {
    "topic": {"producer_agent": ("opus", "high"), "viewer": ("sonnet", "medium"), "*": ("opus", "high")},
    "article": {"producer_agent": ("opus", "high"), "writer_story": ("opus", "medium"), "*": ("opus", "high")},
    "script": {"producer_agent": ("opus", "high"), "viewer": ("sonnet", "medium"), "*": ("opus", "high")},
    "title_thumb": {"*": ("sonnet", "medium")},
    "media": {"*": ("sonnet", "medium")},
    "final": {"*": ("sonnet", "medium")},
    "shorts_topic": {"*": ("sonnet", "medium")},
    "shorts_script": {"*": ("sonnet", "medium")},
    "shorts_title": {"*": ("sonnet", "medium")},
    "shorts_final": {"*": ("sonnet", "medium")},
}
FACT_CHECKER_TIER: tuple[Model, Effort] = ("opus", "high")   # every stage: errors are dearest downstream
# article 2 → 3: Leon 2026-10-18 decision 59fdefb32bd7 = D (with delete-or-edit-only rewrites and arbitration)
MAX_ROUNDS = {"topic": 2, "article": 3, "script": 3, "title_thumb": 3, "media": 3, "final": 3,
              "shorts_topic": 2, "shorts_script": 3, "shorts_title": 3, "shorts_final": 3}
# Stages whose two fact-checkers' disagreements go to a third (``Stage.arbiter``, ≥ FACT_CHECKER_TIER).
ARBITRATED_STAGES = ("article",)
# step → first round whose material must be a delete-or-edit-only rewrite (``review.article_diff``).
DELETE_ONLY_FROM_ROUND = {"article": 2}

# Threshold fields: (direction, floor). "min" = value must be ≥ floor; "max" = value must be ≤ floor.
THRESHOLD_FLOOR: dict[str, dict[str, tuple[str, float]]] = {
    "article": {"fact_errors_max": ("max", 0)},
    "script": {"leave_median_pct": ("min", 0.5), "writer_min": ("min", 7), "fact_errors_max": ("max", 0)},
    "title_thumb": {"noticed_median_max": ("max", 3), "pick_factor": ("min", 2.0)},
    "media": {"compliance_issues_max": ("max", 0)},
    "final": {"leave_median_pct": ("min", 0.5)},
    "shorts_script": {"leave_median_pct": ("min", 0.5)},
    "shorts_final": {"leave_median_pct": ("min", 0.5)},
}

# Steps a fix may be routed back to (``caused_by`` in reviewer output).
REWORK_STEPS = ("topic", "article", "deck", "thumbnail_spec", "voice", "illustrate", "media",
                "assembly", "mascot", "mix")


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Tier(_Strict):
    model: Model
    effort: Effort

    def at_least(self, floor: tuple[str, str]) -> bool:
        return MODEL_RANK[self.model] >= MODEL_RANK[floor[0]] and EFFORT_RANK[self.effort] >= EFFORT_RANK[floor[1]]

    def label(self) -> str:
        return f"{self.model} · {self.effort}"


class Role(_Strict):
    title: str
    kind: Literal["viewer", "pro", "fact", "producer", "designer", "compliance"]
    brief: str = ""
    rubric: tuple[str, ...] = ()
    tools: tuple[str, ...] = ("Read",)        # tools the reviewer subprocess may use


class Seat(_Strict):
    role: str
    count: int = Field(ge=1, le=8)
    model: Model
    effort: Effort
    holdout: int = Field(default=0, ge=0, le=2)   # of ``count``, held out until the last round

    @property
    def tier(self) -> Tier:
        return Tier(model=self.model, effort=self.effort)


class Threshold(_Strict):
    leave_median_pct: float | None = None       # viewers' leave point median ≥ this share of length
    writer_min: float | None = None             # every writer_* ≥ this /10
    fact_errors_max: int | None = None          # each fact-checker finds ≤ this many errors
    noticed_median_max: float | None = None     # homepage: noticed rank median ≤ this
    pick_factor: float | None = None            # homepage: pick rate ≥ factor × chance
    auto_checks: bool = False                   # thumbnail auto checks must all pass
    producer_honest: bool = False               # producer finds no exaggeration
    compliance_issues_max: int | None = None
    licenses_confirmed: bool = False            # credits.json pending empty
    objective_all_green: bool = False           # retention report: no red column
    thumbnail_consistent: bool = False          # final: viewers say thumbnail matches the video
    pro_min: float | None = None                # every pro reviewer ≥ this /10
    top_n_long: int = 1                         # topic: how many go to production
    top_n_short: int = 3
    topic_min_score: float | None = None


class Stage(_Strict):
    gate: str                                    # review/<gate>.decision.json
    reviews: tuple[str, ...]                     # run-dir files the panel reads (fingerprint)
    producer: Tier | None = None                 # the agent that makes the stage's output
    arbiter: Tier | None = None                  # third fact-checker for disagreements (ARBITRATED_STAGES)
    rework: str                                 # step a failed round goes back to by default
    max_rounds: int = Field(ge=1, le=5)
    seats: tuple[Seat, ...]
    threshold: Threshold = Threshold()


class Aggregator(_Strict):
    model: Model = "haiku"
    effort: Effort = "low"


class Defaults(_Strict):
    max_parallel: int = Field(default=4, ge=1, le=8)
    timeout_s: int = Field(default=1200, ge=60, le=7200)
    schema_retries: int = Field(default=1, ge=0, le=3)


class ReviewConfig(_Strict):
    defaults: Defaults = Defaults()
    aggregator: Aggregator = Aggregator()
    roles: dict[str, Role]
    stages: dict[str, Stage]
    channels: dict[str, dict] = {}

    @model_validator(mode="after")
    def _rules(self) -> ReviewConfig:
        errors = rule_violations(self)
        if errors:
            raise ValueError("review_panels.yaml breaks hard rules:\n  - " + "\n  - ".join(errors))
        return self


def _seat_errors(name: str, stage: Stage, roles: dict[str, Role]) -> list[str]:
    errors = []
    counts: dict[str, int] = {}
    holdouts = 0
    for seat in stage.seats:
        if seat.role not in roles:
            errors.append(f"{name}: unknown role {seat.role!r}")
            continue
        counts[seat.role] = counts.get(seat.role, 0) + seat.count
        holdouts += seat.holdout
        if seat.holdout and roles[seat.role].kind != "viewer":
            errors.append(f"{name}: only viewers can be held out ({seat.role})")
        if seat.holdout >= seat.count:
            errors.append(f"{name}: {seat.role} holdout {seat.holdout} must leave regular viewers")
        floors = TIER_FLOOR[name]
        floor = FACT_CHECKER_TIER if roles[seat.role].kind == "fact" else floors.get(seat.role, floors["*"])
        if not seat.tier.at_least(floor):
            errors.append(f"{name}: {seat.role} is {seat.tier.label()}, below {floor[0]} · {floor[1]}")
    for role, need in REQUIRED_ROLES[name].items():
        if counts.get(role, 0) < need:
            errors.append(f"{name}: needs {role} ×{need}, has ×{counts.get(role, 0)}")
    if holdouts < REQUIRED_HOLDOUT.get(name, 0):
        errors.append(f"{name}: needs {REQUIRED_HOLDOUT[name]} holdout viewer(s)")
    return errors


def _threshold_errors(name: str, threshold: Threshold) -> list[str]:
    errors = []
    for field, (direction, floor) in THRESHOLD_FLOOR.get(name, {}).items():
        value = getattr(threshold, field)
        if value is None:
            errors.append(f"{name}: threshold {field} is required (floor {floor})")
        elif (direction == "min" and value < floor) or (direction == "max" and value > floor):
            errors.append(f"{name}: threshold {field}={value} is looser than {floor}")
    return errors


def rule_violations(config: ReviewConfig) -> list[str]:
    errors = []
    for name in STAGES:
        if name not in config.stages:
            errors.append(f"stage {name!r} missing")
    for name, stage in config.stages.items():
        if name not in STAGES:
            errors.append(f"unknown stage {name!r}")
            continue
        errors += _seat_errors(name, stage, config.roles)
        errors += _threshold_errors(name, stage.threshold)
        if stage.max_rounds > MAX_ROUNDS[name]:
            errors.append(f"{name}: max_rounds {stage.max_rounds} > {MAX_ROUNDS[name]}")
        if stage.rework not in REWORK_STEPS:
            errors.append(f"{name}: rework target {stage.rework!r} not in {REWORK_STEPS}")
        floor = TIER_FLOOR[name].get("producer_agent")
        if floor and (stage.producer is None or not stage.producer.at_least(floor)):
            errors.append(f"{name}: producer agent must be ≥ {floor[0]} · {floor[1]}")
        if name in ARBITRATED_STAGES and (stage.arbiter is None or not stage.arbiter.at_least(FACT_CHECKER_TIER)):
            errors.append(f"{name}: fact arbiter must be ≥ {FACT_CHECKER_TIER[0]} · {FACT_CHECKER_TIER[1]}")
        if name in ARBITRATED_STAGES:
            checkers = sum(s.count for s in stage.seats if config.roles.get(s.role, None) is not None
                           and config.roles[s.role].kind == "fact")
            if checkers != 2:
                errors.append(f"{name}: arbitration needs exactly 2 fact-checkers, has {checkers}")
    for role in config.roles.values():
        if role.kind == "fact" and "WebFetch" not in role.tools:
            errors.append(f"fact-checker role {role.title!r} must be able to WebFetch its sources")
    return errors


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        out[key] = _merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def load_review(channel: str | None = None, *, path: Path = PANELS_FILE,
                raise_tier: Tier | None = None) -> ReviewConfig:
    """The validated review config, with ``channel``'s overrides merged in. ``raise_tier`` lifts
    every seat to at least that tier (the all-opus comparison run); it can never lower one."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))["review"]
    config = ReviewConfig.model_validate(raw)
    if channel and channel in config.channels:
        raw = {**raw, "stages": _merge(raw["stages"], config.channels[channel].get("stages", {}))}
        config = ReviewConfig.model_validate(raw)
    if raise_tier is not None:
        config = _lift(raw, config, raise_tier)
    return config


def _lift(raw: dict, config: ReviewConfig, tier: Tier) -> ReviewConfig:
    stages = {}
    for name, stage in raw["stages"].items():
        seats = []
        for seat in stage["seats"]:
            current = Tier(model=seat["model"], effort=seat["effort"])
            model = max(current.model, tier.model, key=MODEL_RANK.get)
            effort = max(current.effort, tier.effort, key=EFFORT_RANK.get)
            seats.append({**seat, "model": model, "effort": effort})
        stages[name] = {**stage, "seats": seats}
    return ReviewConfig.model_validate({**raw, "stages": stages})


def sentence_id_field(path: Path = PANELS_FILE) -> str:
    """deck.json sentence id field; owned by feat/incremental-render, configurable until it lands."""
    return str(yaml.safe_load(path.read_text(encoding="utf-8")).get("sentence_id_field", "sentence_ids"))
