"""Tests for the pipeline checkpoint/state system."""

from __future__ import annotations

import json

import pytest

from content_farm.pipeline.state import (
    PipelineStateDB,
    RunStatus,
    STAGE_ORDER,
)


@pytest.fixture
def db(tmp_path) -> PipelineStateDB:
    return PipelineStateDB(tmp_path / "test_state.db")


class TestRunManagement:
    def test_create_run(self, db: PipelineStateDB) -> None:
        run_id = db.create_run("test topic", "/tmp/output")
        assert len(run_id) == 12

        run = db.get_run(run_id)
        assert run is not None
        assert run.topic == "test topic"
        assert run.status == "in_progress"
        assert run.output_dir == "/tmp/output"
        assert run.completed_stages == ()

    def test_set_run_status(self, db: PipelineStateDB) -> None:
        run_id = db.create_run("topic", "/tmp")
        db.set_run_status(run_id, RunStatus.COMPLETED)

        run = db.get_run(run_id)
        assert run is not None
        assert run.status == "completed"

    def test_get_nonexistent_run(self, db: PipelineStateDB) -> None:
        assert db.get_run("nonexistent") is None

    def test_save_and_get_script(self, db: PipelineStateDB) -> None:
        run_id = db.create_run("topic", "/tmp")
        script_json = json.dumps({"video_title": "test"})
        db.save_script(run_id, script_json)

        result = db.get_script_json(run_id)
        assert result == script_json

    def test_list_runs(self, db: PipelineStateDB) -> None:
        db.create_run("topic 1", "/tmp/1")
        db.create_run("topic 2", "/tmp/2")
        db.create_run("topic 3", "/tmp/3")

        runs = db.list_runs(limit=2)
        assert len(runs) == 2
        # Most recent first
        assert runs[0].topic == "topic 3"
        assert runs[1].topic == "topic 2"


class TestCheckpoints:
    def test_save_and_get_checkpoint(self, db: PipelineStateDB) -> None:
        run_id = db.create_run("topic", "/tmp")
        artifact = {"segments": [{"scene": 1}]}

        db.save_checkpoint(run_id, "voice", json.dumps(artifact))

        result = db.get_checkpoint(run_id, "voice")
        assert result == artifact

    def test_checkpoint_updates_completed_stages(self, db: PipelineStateDB) -> None:
        run_id = db.create_run("topic", "/tmp")
        db.save_checkpoint(run_id, "script")
        db.save_checkpoint(run_id, "voice")

        run = db.get_run(run_id)
        assert run is not None
        assert run.completed_stages == ("script", "voice")

    def test_checkpoint_idempotent(self, db: PipelineStateDB) -> None:
        run_id = db.create_run("topic", "/tmp")
        db.save_checkpoint(run_id, "voice", '{"v":1}')
        db.save_checkpoint(run_id, "voice", '{"v":2}')

        result = db.get_checkpoint(run_id, "voice")
        assert result == {"v": 2}

        run = db.get_run(run_id)
        assert run is not None
        assert run.completed_stages == ("voice",)

    def test_get_nonexistent_checkpoint(self, db: PipelineStateDB) -> None:
        run_id = db.create_run("topic", "/tmp")
        assert db.get_checkpoint(run_id, "voice") is None


class TestResumeLogic:
    def test_next_stage_empty_run(self, db: PipelineStateDB) -> None:
        run_id = db.create_run("topic", "/tmp")
        assert db.get_next_stage(run_id) == "script"

    def test_next_stage_after_script(self, db: PipelineStateDB) -> None:
        run_id = db.create_run("topic", "/tmp")
        db.save_checkpoint(run_id, "script")
        assert db.get_next_stage(run_id) == "voice"

    def test_next_stage_after_voice_visual(self, db: PipelineStateDB) -> None:
        run_id = db.create_run("topic", "/tmp")
        db.save_checkpoint(run_id, "script")
        db.save_checkpoint(run_id, "voice")
        db.save_checkpoint(run_id, "visual")
        assert db.get_next_stage(run_id) == "subtitle"

    def test_next_stage_all_complete(self, db: PipelineStateDB) -> None:
        run_id = db.create_run("topic", "/tmp")
        for stage in STAGE_ORDER:
            db.save_checkpoint(run_id, stage)
        assert db.get_next_stage(run_id) is None

    def test_next_stage_nonexistent_run(self, db: PipelineStateDB) -> None:
        assert db.get_next_stage("nonexistent") is None
