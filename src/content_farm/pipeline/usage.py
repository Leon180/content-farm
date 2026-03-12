"""Usage tracking for API calls across pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class UsageRecord:
    """Single API call record."""

    stage: str
    provider: str  # "anthropic", "elevenlabs", "pexels", "gemini", etc.
    metric: str  # "input_tokens", "output_tokens", "characters", "api_calls"
    value: int
    model: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat(),
    )


@dataclass
class UsageTracker:
    """Accumulates usage records across a pipeline run.

    Records are appended during pipeline execution and flushed
    to the state DB once the run completes (or at each checkpoint).
    """

    run_id: str
    records: list[UsageRecord] = field(default_factory=list)

    def record(
        self,
        stage: str,
        provider: str,
        metric: str,
        value: int,
        model: str = "",
    ) -> None:
        """Append a usage record."""
        self.records.append(UsageRecord(
            stage=stage,
            provider=provider,
            metric=metric,
            value=value,
            model=model,
        ))

    def total(self, metric: str) -> int:
        """Sum all records for a given metric."""
        return sum(r.value for r in self.records if r.metric == metric)

    def by_stage(self, stage: str) -> list[UsageRecord]:
        """Filter records by stage name."""
        return [r for r in self.records if r.stage == stage]

    def by_provider(self, provider: str) -> list[UsageRecord]:
        """Filter records by provider name."""
        return [r for r in self.records if r.provider == provider]

    def summary(self) -> dict[str, int]:
        """Return a metric → total mapping for all recorded metrics."""
        totals: dict[str, int] = {}
        for r in self.records:
            totals[r.metric] = totals.get(r.metric, 0) + r.value
        return totals