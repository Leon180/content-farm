"""Pipeline checkpoint/resume system using SQLite.

Tracks pipeline runs and their stage completions so that:
1. A failed run can be resumed from the last successful stage.
2. Expensive API artifacts are not regenerated unnecessarily.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

logger = logging.getLogger(__name__)

DB_FILENAME = "pipeline_state.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    topic         TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'in_progress',
    output_dir    TEXT NOT NULL,
    script_json   TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL REFERENCES runs(run_id),
    stage         TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'completed',
    artifact_json TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE(run_id, stage)
);

CREATE TABLE IF NOT EXISTS usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL REFERENCES runs(run_id),
    stage         TEXT NOT NULL,
    provider      TEXT NOT NULL,
    metric        TEXT NOT NULL,
    value         INTEGER NOT NULL,
    model         TEXT DEFAULT '',
    created_at    TEXT NOT NULL
);
"""


class RunStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


# Ordered pipeline stages — defines resume ordering.
STAGE_ORDER = (
    "script",
    "voice",
    "visual",
    "subtitle",
    "thumbnail",
    "assembly",
    "drive",
    "upload",
)


class RunInfo(BaseModel):
    """Summary of a pipeline run."""

    model_config = {"frozen": True}

    run_id: str
    topic: str
    status: str
    output_dir: str
    completed_stages: tuple[str, ...]
    created_at: str
    updated_at: str


class PipelineStateDB:
    """SQLite-backed pipeline state manager.

    Thread-safe for single-writer use (SQLite default).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or Path(DB_FILENAME)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Run management
    # ------------------------------------------------------------------

    def create_run(self, topic: str, output_dir: str) -> str:
        """Create a new pipeline run. Returns run_id."""
        run_id = uuid4().hex[:12]
        now = _now_iso()
        self._conn.execute(
            "INSERT INTO runs (run_id, topic, status, output_dir, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, topic, RunStatus.IN_PROGRESS, output_dir, now, now),
        )
        self._conn.commit()
        logger.info("Created run %s for topic '%s'", run_id, topic)
        return run_id

    def set_run_status(self, run_id: str, status: RunStatus) -> None:
        self._conn.execute(
            "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
            (status, _now_iso(), run_id),
        )
        self._conn.commit()

    def save_script(self, run_id: str, script_json: str) -> None:
        """Persist the script JSON for a run."""
        self._conn.execute(
            "UPDATE runs SET script_json = ?, updated_at = ? WHERE run_id = ?",
            (script_json, _now_iso(), run_id),
        )
        self._conn.commit()

    def get_run(self, run_id: str) -> RunInfo | None:
        """Retrieve run info including completed stages."""
        row = self._conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None

        stages = self._conn.execute(
            "SELECT stage FROM checkpoints WHERE run_id = ? AND status = ? ORDER BY id",
            (run_id, StageStatus.COMPLETED),
        ).fetchall()

        return RunInfo(
            run_id=row["run_id"],
            topic=row["topic"],
            status=row["status"],
            output_dir=row["output_dir"],
            completed_stages=tuple(s["stage"] for s in stages),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_script_json(self, run_id: str) -> str | None:
        """Retrieve the script JSON for a run."""
        row = self._conn.execute(
            "SELECT script_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return row["script_json"] if row else None

    def list_runs(self, limit: int = 20) -> list[RunInfo]:
        """List recent runs."""
        rows = self._conn.execute(
            "SELECT run_id FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self.get_run(r["run_id"]) for r in rows if self.get_run(r["run_id"])]

    # ------------------------------------------------------------------
    # Checkpoint management
    # ------------------------------------------------------------------

    def save_checkpoint(
        self,
        run_id: str,
        stage: str,
        artifact_json: str | None = None,
    ) -> None:
        """Record a completed stage checkpoint."""
        self._conn.execute(
            "INSERT OR REPLACE INTO checkpoints (run_id, stage, status, artifact_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, stage, StageStatus.COMPLETED, artifact_json, _now_iso()),
        )
        self._conn.execute(
            "UPDATE runs SET updated_at = ? WHERE run_id = ?",
            (_now_iso(), run_id),
        )
        self._conn.commit()
        logger.info("Checkpoint saved: run=%s stage=%s", run_id, stage)

    def get_checkpoint(self, run_id: str, stage: str) -> dict[str, Any] | None:
        """Retrieve a checkpoint's artifact JSON (parsed)."""
        row = self._conn.execute(
            "SELECT artifact_json FROM checkpoints WHERE run_id = ? AND stage = ? AND status = ?",
            (run_id, stage, StageStatus.COMPLETED),
        ).fetchone()
        if row is None or row["artifact_json"] is None:
            return None
        return json.loads(row["artifact_json"])

    def get_next_stage(self, run_id: str) -> str | None:
        """Determine which stage to resume from.

        Returns the first stage not yet completed, or None if all done.
        """
        run = self.get_run(run_id)
        if run is None:
            return None

        completed = set(run.completed_stages)
        for stage in STAGE_ORDER:
            if stage not in completed:
                return stage
        return None


    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------

    def save_usage(
        self,
        run_id: str,
        records: list[tuple[str, str, str, int, str]],
    ) -> None:
        """Persist usage records (stage, provider, metric, value, model)."""
        now = _now_iso()
        self._conn.executemany(
            "INSERT INTO usage (run_id, stage, provider, metric, value, model, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(run_id, stage, provider, metric, value, model, now)
             for stage, provider, metric, value, model in records],
        )
        self._conn.commit()

    def get_usage_summary(self, run_id: str) -> dict[str, int]:
        """Return {metric: total_value} for a run."""
        rows = self._conn.execute(
            "SELECT metric, SUM(value) AS total "
            "FROM usage WHERE run_id = ? GROUP BY metric",
            (run_id,),
        ).fetchall()
        return {r["metric"]: r["total"] for r in rows}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
