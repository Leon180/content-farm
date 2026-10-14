"""Per-slide ``media`` hint — what the visual track shows for this slide.

Schema only: nothing here renders. The v2 visual worker owns rendering (and,
on integration, this model); it is defined here so a deck that already
carries ``media`` validates under ``extra="forbid"``. Absent ``media`` means
``kind="slide"`` (the rendered slide PNG), exactly as before.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

MediaKind = Literal["slide", "animated", "stock", "ai_image", "title_card"]

# kind -> the field that kind cannot do without
_REQUIRED: dict[str, tuple[str, ...]] = {
    "slide": (),
    "animated": ("animation",),
    "stock": ("query",),
    "ai_image": ("prompt",),
    "title_card": ("headline", "source_id"),
}


class Media(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}

    kind: MediaKind = "slide"
    query: str = Field(default="", max_length=120)  # stock footage search terms
    prompt: str = Field(default="", max_length=600)  # ai_image prompt
    # e.g. count_up | grow_bars | reveal_list | draw_line
    animation: str = Field(default="", pattern=r"^([a-z][a-z0-9_]{0,31})?$")
    headline: str = Field(default="", max_length=60)  # title_card news headline
    source_id: str = Field(default="", max_length=32)  # title_card: must exist in deck sources

    @model_validator(mode="after")
    def _required_for_kind(self) -> Media:
        missing = [name for name in _REQUIRED[self.kind] if not getattr(self, name).strip()]
        if missing:
            raise ValueError(f"media kind {self.kind!r} requires {missing}")
        return self
