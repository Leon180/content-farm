"""Pipeline stage protocol and orchestrator."""

from __future__ import annotations

import logging
from typing import Protocol, TypeVar, runtime_checkable

from content_farm.types import PipelineArtifact

Input = TypeVar("Input")
Output = TypeVar("Output", bound=PipelineArtifact)

logger = logging.getLogger(__name__)


@runtime_checkable
class PipelineStage(Protocol[Input, Output]):
    """Any pipeline stage must implement this protocol."""

    @property
    def name(self) -> str: ...

    async def execute(self, input_data: Input) -> Output: ...

    async def validate_input(self, input_data: Input) -> None: ...


class Pipeline:
    """Chains stages together. Each stage's output feeds the next."""

    def __init__(self, stages: list[PipelineStage]) -> None:  # type: ignore[type-arg]
        self._stages = tuple(stages)

    async def run(self, initial_input: object) -> PipelineArtifact:
        """Run all stages sequentially."""
        current = initial_input
        for stage in self._stages:
            logger.info("Running pipeline stage: %s", stage.name)
            await stage.validate_input(current)
            current = await stage.execute(current)
            logger.info("Completed stage: %s", stage.name)
        if not isinstance(current, PipelineArtifact):
            raise TypeError(f"Final stage output is not a PipelineArtifact: {type(current)}")
        return current
