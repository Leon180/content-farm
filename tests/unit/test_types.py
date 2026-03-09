"""Tests for shared domain types."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_farm.types import (
    PipelineArtifact,
    Tone,
    TopicBrief,
    VideoLength,
)


def test_tone_enum_values() -> None:
    assert Tone.EDUCATIONAL == "educational"
    assert Tone.DRAMATIC == "dramatic"


def test_video_length_enum_values() -> None:
    assert VideoLength.SHORT == "short"
    assert VideoLength.MEDIUM == "medium"
    assert VideoLength.LONG == "long"


def test_topic_brief_creation() -> None:
    brief = TopicBrief(
        topic="How Bitcoin Works",
        keywords=["bitcoin", "crypto"],
        video_length=VideoLength.MEDIUM,
        tone=Tone.EDUCATIONAL,
    )
    assert brief.topic == "How Bitcoin Works"
    assert len(brief.keywords) == 2


def test_topic_brief_defaults() -> None:
    brief = TopicBrief(topic="Test")
    assert brief.video_length == VideoLength.MEDIUM
    assert brief.tone == Tone.EDUCATIONAL
    assert brief.keywords == ()


def test_topic_brief_is_frozen() -> None:
    brief = TopicBrief(topic="Test")
    with pytest.raises(ValidationError):
        brief.topic = "Changed"  # type: ignore[misc]


def test_pipeline_artifact_has_id_and_timestamp() -> None:
    artifact = PipelineArtifact(stage="test")
    assert artifact.artifact_id is not None
    assert artifact.created_at is not None
    assert artifact.stage == "test"


def test_pipeline_artifact_is_frozen() -> None:
    artifact = PipelineArtifact(stage="test")
    with pytest.raises(ValidationError):
        artifact.stage = "changed"  # type: ignore[misc]
