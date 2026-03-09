"""Tests for visual domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_farm.visual.schemas import VideoResult, VisualArtifact, VisualAsset


class TestVideoResult:
    def test_create_minimal(self) -> None:
        vr = VideoResult(
            provider_id="pexels:123",
            url="https://example.com/video.mp4",
            duration_seconds=10,
            width=1920,
            height=1080,
        )
        assert vr.provider_id == "pexels:123"
        assert vr.thumbnail_url == ""

    def test_frozen(self) -> None:
        vr = VideoResult(
            provider_id="pexels:1",
            url="https://example.com/v.mp4",
            duration_seconds=5,
            width=1280,
            height=720,
        )
        with pytest.raises(ValidationError):
            vr.url = "https://other.com/v.mp4"  # type: ignore[misc]


class TestVisualAsset:
    def test_create(self) -> None:
        asset = VisualAsset(
            scene_number=1,
            file_path="/tmp/scene_001.mp4",
            source="pexels",
            duration_seconds=12.5,
            query_used="ocean waves",
        )
        assert asset.format == "mp4"
        assert asset.scene_number == 1

    def test_frozen(self) -> None:
        asset = VisualAsset(
            scene_number=1,
            file_path="/tmp/scene_001.mp4",
            source="pexels",
            duration_seconds=12.5,
            query_used="ocean waves",
        )
        with pytest.raises(ValidationError):
            asset.source = "kling"  # type: ignore[misc]


class TestVisualArtifact:
    def test_defaults(self) -> None:
        artifact = VisualArtifact()
        assert artifact.stage == "visual_generation"
        assert artifact.assets == ()
        assert artifact.total_duration_seconds == 0.0
        assert artifact.output_dir == ""

    def test_with_assets(self) -> None:
        asset = VisualAsset(
            scene_number=1,
            file_path="/tmp/scene_001.mp4",
            source="pexels",
            duration_seconds=10.0,
            query_used="sunset",
        )
        artifact = VisualArtifact(
            assets=(asset,),
            total_duration_seconds=10.0,
            output_dir="/tmp/visual",
        )
        assert len(artifact.assets) == 1
        assert artifact.total_duration_seconds == 10.0
