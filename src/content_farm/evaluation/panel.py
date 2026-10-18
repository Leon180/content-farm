"""Review panel config (``channels/shared/review_panels.yaml``) and who sits on a given round.

Anti-overfitting (Leon 2026-10-17): every round re-words each persona (another framing, traits
shuffled with a round-specific seed) and shuffles the reviewer order; the holdout viewer joins
only the last round and never feeds the fixes of earlier rounds.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

PANELS_FILE = Path(__file__).resolve().parents[3] / "channels" / "shared" / "review_panels.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Persona(_Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    who: str
    traits: tuple[str, ...]
    holdout: bool = False


class Pro(_Strict):
    title: str
    brief: str
    rubric: tuple[str, ...]


class Stage(_Strict):
    viewers: int = Field(ge=0, le=12)
    holdout: bool = False
    pros: dict[str, int] = {}
    homepage: bool = False


class Thresholds(_Strict):
    leave_median_pct: float = 0.5
    click_mean: float = 7.0
    objective_all_green: bool = True
    homepage_noticed_median: float = 3
    homepage_pick_factor: float = 2.0
    max_rounds: int = Field(default=3, ge=1, le=10)


class Panels(_Strict):
    version: int = 1
    framings: tuple[str, ...]
    personas: dict[str, tuple[Persona, ...]]
    pros: dict[str, Pro]
    stages: dict[str, Stage]
    thresholds: Thresholds = Thresholds()
    sentence_id_field: str = "sid"   # deck sentence id (feat/incremental-render); see review/config.py
    review: dict = {}                # the pipeline review panels; validated by review/config.py


@dataclass(frozen=True)
class Reviewer:
    rid: str            # file-safe id, e.g. viewer-engineer, pro-editor-1
    kind: str           # viewer | pro
    role: str           # persona id or pro key
    holdout: bool
    description: str    # the re-worded persona text, or the pro brief


def load_panels(path: Path = PANELS_FILE) -> Panels:
    return Panels.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def persona_set(panels: Panels, channel_code: str) -> tuple[Persona, ...]:
    if channel_code in panels.personas:
        return panels.personas[channel_code]
    if "chipcat" in panels.personas:   # channel without its own audience: the default set
        return panels.personas["chipcat"]
    raise ValueError(f"no personas for channel {channel_code!r}")


def word_persona(panels: Panels, persona: Persona, round_no: int) -> str:
    rng = random.Random(f"{persona.id}:{round_no}")
    traits = list(persona.traits)
    rng.shuffle(traits)
    framing = panels.framings[(round_no - 1 + len(persona.id)) % len(panels.framings)]
    return framing.format(who=persona.who, traits="；".join(t.rstrip("。") for t in traits)).replace("。。", "。")


def roster(panels: Panels, stage_name: str, channel_code: str, round_no: int, *, final_round: bool,
           holdout_only: bool = False) -> list[Reviewer]:
    """``holdout_only``: the holdout viewer alone (a round that passed before the last allowed one)."""
    stage = panels.stages[stage_name]
    people = persona_set(panels, channel_code)
    if holdout_only:
        return [Reviewer(f"viewer-{p.id}", "viewer", p.id, True, word_persona(panels, p, round_no))
                for p in people if p.holdout]
    regular = [p for p in people if not p.holdout][: stage.viewers]
    chosen = [*regular, *([p for p in people if p.holdout] if (stage.holdout or final_round) else [])]
    reviewers = [Reviewer(f"viewer-{p.id}", "viewer", p.id, p.holdout, word_persona(panels, p, round_no))
                 for p in chosen]
    for key, count in stage.pros.items():
        pro = panels.pros[key]
        reviewers += [Reviewer(f"pro-{key}-{n}", "pro", key, False, pro.brief) for n in range(1, count + 1)]
    random.Random(f"order:{round_no}").shuffle(reviewers)
    return reviewers
