"""Walk a channel's steps for one run-dir, stopping at gates, missing agent
work, paid steps without consent, and failures. Re-running resumes: finished
steps whose inputs did not change are skipped."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from content_farm.explainer.deck import load_deck
from content_farm.production import publish, qc
from content_farm.production.channels import Channel, Gate
from content_farm.production.review import write_review
from content_farm.production.state import (
    Decision, RunState, StepRecord, fingerprint, load_state, now_iso, save_state,
)
from content_farm.production.steps import REPO_ROOT, Command, Context, Step, steps_for

LOCK_PATH = Path.home() / ".cache" / "content-farm" / "render.lock"
SCHEDULE_FILE = "production.schedule.json"
LOAD_POLL_SECONDS = 30


class Outcome(str, Enum):
    COMPLETE = "complete"
    GATE = "waiting_gate"
    AGENT = "waiting_agent"
    PAID = "needs_paid_consent"
    FAILED = "failed"


@dataclass(frozen=True)
class RunResult:
    outcome: Outcome
    step: str = ""
    message: str = ""
    review_page: Path | None = None

    @property
    def exit_code(self) -> int:
        return {Outcome.COMPLETE: 0, Outcome.FAILED: 1}.get(self.outcome, 3)


Executor = Callable[[Command, Path], int]


def subprocess_executor(command: Command, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n$ {' '.join(command.argv)}\n")
        log.flush()
        proc = subprocess.run(command.argv, env=command.full_env(), cwd=REPO_ROOT,
                              stdout=log, stderr=subprocess.STDOUT, check=False)
    return proc.returncode


@contextmanager
def render_lock(max_load: float | None, log: Callable[[str], None]) -> Iterator[None]:
    """One heavy render (Chromium capture, ffmpeg encode, mascot) on the machine at a time,
    and wait while the 1-minute load average is above ``max_load``."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("render lock held by another run; waiting")
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            while max_load is not None and os.getloadavg()[0] > max_load:
                log(f"load {os.getloadavg()[0]:.1f} > {max_load}; waiting {LOAD_POLL_SECONDS}s")
                time.sleep(LOAD_POLL_SECONDS)
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _event(run_dir: Path, **fields: object) -> None:
    with (run_dir / "production.log.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"at": now_iso(), **fields}, ensure_ascii=False) + "\n")


def _outputs_present(run_dir: Path, step: Step) -> bool:
    return all(any(path.is_file() for path in run_dir.glob(pattern)) for pattern in step.outputs)


def gate_fingerprint(run_dir: Path, step: Step) -> str:
    return fingerprint(run_dir, step.artifacts)


def scheduled_publish_at(run_dir: Path) -> datetime | None:
    path = run_dir / SCHEDULE_FILE
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8")).get("publish_at")
    return datetime.fromisoformat(value) if value else None


def _internal(ctx: Context, step: Step) -> tuple[bool, str]:
    run_dir, channel = ctx.run_dir, ctx.channel
    if step.name == "policy":
        findings = qc.deck_findings(channel, load_deck(run_dir / "deck.json"))
        bad = [f.message for f in findings if f.level == "error"]
        return (not bad, "; ".join(bad) or findings[0].message)
    if step.name == "qc":
        deck_path = run_dir / "deck.json"
        report = qc.run_qc(run_dir, channel, load_deck(deck_path) if deck_path.is_file() else None)
        # QC never blocks here: errors surface on the final review page and block approval.
        return True, f"{report['errors']} error(s), {report['warnings']} warning(s)"
    if step.name == "package":
        meta = publish.build_meta(channel, run_dir, publish_at=scheduled_publish_at(run_dir))
        path = publish.write_meta(run_dir, meta)
        return True, f"{path.relative_to(run_dir)} (publish_at={meta['publish_at']})"
    raise ValueError(f"no internal implementation for step {step.name!r}")


@dataclass
class Runner:
    ctx: Context
    executor: Executor = subprocess_executor
    max_load: float | None = None
    log: Callable[[str], None] = print

    @property
    def run_dir(self) -> Path:
        return self.ctx.run_dir

    def run(self, *, until: str | None = None, force: frozenset[str] = frozenset()) -> RunResult:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        state = load_state(self.run_dir, self.ctx.channel.code)
        save_state(self.run_dir, state)
        for step in steps_for(self.ctx.channel, self.run_dir):
            state, result = self._step(state, step, step.name in force)
            save_state(self.run_dir, state)
            if result is not None:
                _event(self.run_dir, step=step.name, outcome=result.outcome.value, message=result.message)
                return result
            if step.name == until:
                return RunResult(Outcome.COMPLETE, step.name, f"stopped after {until}")
        return RunResult(Outcome.COMPLETE, "", "all steps done")

    def _step(self, state: RunState, step: Step, forced: bool) -> tuple[RunState, RunResult | None]:
        handler = {"agent": self._agent, "gate": self._gate, "cmd": self._cmd, "internal": self._internal}
        return handler[step.kind](state, step, forced)

    def _fresh(self, state: RunState, step: Step, inputs: str, forced: bool) -> bool:
        record = state.steps.get(step.name)
        return (not forced and record is not None and record.status == "done"
                and record.inputs == inputs and _outputs_present(self.run_dir, step))

    def _agent(self, state: RunState, step: Step, forced: bool) -> tuple[RunState, RunResult | None]:
        if not _outputs_present(self.run_dir, step):
            message = f"{step.title}：缺 {', '.join(step.outputs)}。{step.hint}"
            return state, RunResult(Outcome.AGENT, step.name, message)
        inputs = fingerprint(self.run_dir, step.outputs)
        if self._fresh(state, step, inputs, forced):
            return state, None
        if step.verify is None:
            return state.with_step(step.name, StepRecord("done", now_iso(), inputs=inputs)), None
        return self._execute(state, step, step.verify(self.ctx), lambda: fingerprint(self.run_dir, step.outputs))

    def _gate(self, state: RunState, step: Step, forced: bool) -> tuple[RunState, RunResult | None]:
        assert step.gate is not None
        current = gate_fingerprint(self.run_dir, step)
        if state.approved(step.gate.value, current):
            decision = state.decisions[step.gate.value]
            record = StepRecord("approved", decision.at, inputs=current, note=f"by {decision.by}")
            return state.with_step(step.name, record), None
        decision = state.decisions.get(step.gate.value)
        unchanged_rejection = (decision is not None and decision.verdict == "rejected"
                               and decision.fingerprint == current)
        page = write_review(self.run_dir, self.ctx.channel, step.gate, step.title, current,
                            status="rejected" if unchanged_rejection else "pending")
        if unchanged_rejection:
            assert decision is not None
            message = f"{step.title} 被退回：{decision.note}（修改後重跑）"
        elif decision is not None and decision.verdict == "rejected":
            message = f"{step.title}：退回後已修改，請重新審核"
        elif decision is not None:
            message = f"{step.title}：核可後檔案已變更，需要重新審核"
        else:
            message = f"{step.title}：等待審核"
        record = StepRecord("waiting", now_iso(), inputs=current, note=message)
        return state.with_step(step.name, record), RunResult(Outcome.GATE, step.name, message, page)

    def _cmd_inputs(self, step: Step) -> str:
        files = fingerprint(self.run_dir, step.inputs)
        if step.identity is None:
            return files
        identity = hashlib.sha256(step.identity(self.ctx).encode("utf-8")).hexdigest()[:16]
        return f"{files}+{identity}"

    def _cmd(self, state: RunState, step: Step, forced: bool) -> tuple[RunState, RunResult | None]:
        assert step.command is not None
        if self._fresh(state, step, self._cmd_inputs(step), forced):
            return state, None
        if step.paid(self.ctx) and not self.ctx.options.allow_paid:
            message = f"{step.title} 會呼叫付費 API；加 --allow-paid 或 --mock-voice"
            return state, RunResult(Outcome.PAID, step.name, message)
        if step.identity is not None:
            identity = step.identity(self.ctx)
            self.log(f"{step.name}: {identity}")
            _event(self.run_dir, step=step.name, identity=identity)
        command = step.command(self.ctx)
        if not step.heavy:
            return self._execute(state, step, command, lambda: self._cmd_inputs(step))
        with render_lock(self.max_load, self.log):
            return self._execute(state, step, command, lambda: self._cmd_inputs(step))

    def _execute(
        self, state: RunState, step: Step, command: Command, inputs_after: Callable[[], str],
    ) -> tuple[RunState, RunResult | None]:
        self.log(f"▶ {step.name}: {step.title}")
        started = time.monotonic()
        code = self.executor(command, self.run_dir / "logs" / f"{step.name}.log")
        seconds = round(time.monotonic() - started, 1)
        _event(self.run_dir, step=step.name, exit_code=code, seconds=seconds)
        if code != 0:
            message = f"{step.title} 失敗（exit {code}），看 logs/{step.name}.log"
            record = StepRecord("failed", now_iso(), seconds, code, note=message)
            return state.with_step(step.name, record), RunResult(Outcome.FAILED, step.name, message)
        self.log(f"✓ {step.name} {seconds}s")
        return state.with_step(step.name, StepRecord("done", now_iso(), seconds, 0, inputs_after())), None

    def _internal(self, state: RunState, step: Step, forced: bool) -> tuple[RunState, RunResult | None]:
        inputs = fingerprint(self.run_dir, step.inputs)
        if step.outputs and self._fresh(state, step, inputs, forced):
            return state, None
        started = time.monotonic()
        try:
            ok, note = _internal(self.ctx, step)
        except (OSError, ValueError) as exc:
            ok, note = False, f"{type(exc).__name__}: {exc}"
        seconds = round(time.monotonic() - started, 1)
        self.log(f"{'✓' if ok else '✗'} {step.name}: {note}")
        record = StepRecord("done" if ok else "failed", now_iso(), seconds, None,
                            fingerprint(self.run_dir, step.inputs), note)
        state = state.with_step(step.name, record)
        return state, None if ok else RunResult(Outcome.FAILED, step.name, note)


def decide(
    run_dir: Path, channel: Channel, gate: Gate, verdict: str, *, note: str = "", override: str = "",
    by: str = "leon",
) -> Decision:
    """Record approve/reject for a gate against the artifacts as they are now."""
    step = next((s for s in steps_for(channel, run_dir) if s.gate is gate), None)
    if step is None:
        raise ValueError(f"channel {channel.code} has no gate {gate.value!r}")
    if verdict == "approved" and gate is Gate.FINAL:
        report = json.loads((run_dir / qc.QC_REPORT).read_text(encoding="utf-8")) \
            if (run_dir / qc.QC_REPORT).is_file() else None
        if report is None:
            raise ValueError("no qc/qc_report.json yet; run the pipeline to the final gate first")
        if report["errors"] and not override:
            raise ValueError(f"QC has {report['errors']} error(s); fix them or pass --override \"reason\"")
        if report["errors"]:
            note = f"OVERRIDE QC ({report['errors']} errors): {override}. {note}".strip()
    decision = Decision(gate.value, verdict, gate_fingerprint(run_dir, step), now_iso(), by=by, note=note)
    state = load_state(run_dir, channel.code).with_decision(decision)
    save_state(run_dir, state)
    _event(run_dir, gate=gate.value, verdict=verdict, note=note)
    item = run_dir / "review" / f"{gate.value}.decision.json"
    if item.is_file():
        data = json.loads(item.read_text(encoding="utf-8"))
        data.update(status=verdict, decided_at=decision.at, note=note, decided_fingerprint=decision.fingerprint)
        item.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return decision
