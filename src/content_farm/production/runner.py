"""Walk a channel's steps for one run-dir, stopping at gates, missing agent
work, paid steps without consent, and failures. Re-running resumes: finished
steps whose inputs did not change are skipped."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from content_farm.explainer.deck import load_deck
from content_farm.lanes.queue import Ticket, heavy_slot
from content_farm.lanes.resources import Need, load_config, need_for
from content_farm.production import panel_flow, publish, qc
from content_farm.production.channels import Channel, Gate
from content_farm.production.review import write_review
from content_farm.production.state import (
    Decision, RunState, StepRecord, fingerprint, load_state, now_iso, save_state,
)
from content_farm.production.steps import REPO_ROOT, Command, Context, Step, steps_for
from content_farm.review.freeze import FROZEN_FILE, frozen_steps

LOCK_PATH = Path.home() / ".cache" / "content-farm" / "render.lock"   # legacy; heavy work goes through lanes.queue
SCHEDULE_FILE = "production.schedule.json"
APPROVED_DECK = "review/deck.approved.json"   # snapshot at deck approval (fix scope baseline)
LOAD_POLL_SECONDS = 30


class Outcome(str, Enum):
    COMPLETE = "complete"
    GATE = "waiting_gate"
    AGENT = "waiting_agent"
    PAID = "needs_paid_consent"
    REWORK = "rework"            # a review panel sent work back to an earlier step
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
def render_lock(max_load: float | None, log: Callable[[str], None], ticket: Ticket | None = None,
                need: Need | None = None) -> Iterator[None]:
    """Admission through the machine-wide queue (``lanes.queue``, shared by every channel, worker
    and ``scripts/heavy``): waits until the step's need fits (memory, swap, load, GPU, locks), then
    while the 1-minute load average is above ``max_load``. ``need`` defaults to exclusive local work."""
    with heavy_slot(ticket or Ticket(job=f"pid{os.getpid()}", kind="other"), log, need=need):
        while max_load is not None and os.getloadavg()[0] > max_load:
            log(f"load {os.getloadavg()[0]:.1f} > {max_load}; waiting {LOAD_POLL_SECONDS}s")
            time.sleep(LOAD_POLL_SECONDS)
        yield


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
    if step.name == "short_script":
        from content_farm.production.shorts_cut import write_scripted_script

        path = write_scripted_script(run_dir)
        return True, f"{path.relative_to(run_dir)} from short_source.json beats"
    if step.name == "qc":
        deck_path = run_dir / "deck.json"
        report = qc.run_qc(run_dir, channel, load_deck(deck_path) if deck_path.is_file() else None)
        # QC never blocks here: errors surface on the final review page and block approval.
        return True, f"{report['errors']} error(s), {report['warnings']} warning(s)"
    if step.name == "package":
        publish_at = scheduled_publish_at(run_dir)
        if publish_at is None:   # suggested slot from channels/<code>.yaml publish: (kept if someone set one)
            from content_farm.production.publish_slot import ensure_schedule

            kind = "short" if panel_flow._short(ctx) else "long"  # noqa: SLF001
            publish_at = ensure_schedule(run_dir, channel.code, kind, now=datetime.now().astimezone())
        meta = publish.build_meta(channel, run_dir, publish_at=publish_at)
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
        record = state.steps.get(step.name)
        pending_rework = (record is not None and record.status == "rework"
                          and record.inputs == fingerprint(self.run_dir, step.outputs))
        if pending_rework and step.name in frozen_steps(self.run_dir) and _outputs_present(self.run_dir, step):
            # frozen for this run (production.frozen.json): its issues are re-planned onto a later step
            self.log(f"❄ {step.name}: 凍結（{FROZEN_FILE}），不重做")
            _event(self.run_dir, step=step.name, frozen=True, skipped_rework=record.note if record else "")
            inputs = fingerprint(self.run_dir, step.outputs)
            state = state.with_step(step.name, StepRecord("done", now_iso(), inputs=inputs, note="frozen"))
            pending_rework = False
        if not _outputs_present(self.run_dir, step) or pending_rework:
            if self.ctx.options.auto_agents and step.name in panel_flow.PRODUCER_STEPS:
                before = fingerprint(self.run_dir, step.outputs)
                with self._admit(state, step):
                    failure = panel_flow.run_producer(self.ctx, step.name, self.log)
                if failure is None and not _outputs_present(self.run_dir, step):
                    failure = f"{step.title}：產出 agent 結束但缺 {', '.join(step.outputs)}"
                if failure is None and pending_rework and fingerprint(self.run_dir, step.outputs) == before:
                    failure = f"{step.title}：退回重做後檔案沒有改變"
                if failure is not None:
                    return state, RunResult(Outcome.FAILED, step.name, failure)
                return self._agent(state.with_step(step.name, StepRecord("produced", now_iso())), step, forced)
            what = f"退回重做：見 {record.note}" if pending_rework and record is not None else \
                f"缺 {', '.join(step.outputs)}"
            message = f"{step.title}：{what}。{step.hint}"
            return state, RunResult(Outcome.AGENT, step.name, message)
        inputs = fingerprint(self.run_dir, step.outputs)
        if self._fresh(state, step, inputs, forced):
            return state, None
        if step.verify is None:
            return state.with_step(step.name, StepRecord("done", now_iso(), inputs=inputs)), None
        with self._admit(state, step):
            return self._execute(state, step, step.verify(self.ctx), lambda: fingerprint(self.run_dir, step.outputs))

    def _gate(self, state: RunState, step: Step, forced: bool) -> tuple[RunState, RunResult | None]:
        assert step.gate is not None
        current = gate_fingerprint(self.run_dir, step)
        if state.approved(step.gate.value, current):
            decision = state.decisions[step.gate.value]
            record = StepRecord("approved", decision.at, inputs=current, note=f"by {decision.by}")
            return state.with_step(step.name, record), None
        stage = panel_flow.stage_of(self.ctx, step.gate)
        if stage is not None:
            with self._admit(state, step):
                return panel_flow.panel_step(self.ctx, state, step, stage, current, self.log)
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

    def _need(self, step: Step) -> Need:
        """The step's declared need (heavy_work.json steps); a local TTS voice is exclusive GPU work,
        a mock voice is light; an undeclared heavy step is treated as exclusive local work."""
        config = load_config()
        if step.name == "voice" and not step.heavy_if(self.ctx):
            return Need(mem_gb=1.0, cpu_cores=1)
        default = need_for("heavy_default", config) if step.heavy else Need()
        return need_for(step.name, config, default=default)

    def _admit(self, state: RunState, step: Step):
        """Entry check before a step does work (cloud lane too): queue until its need fits."""
        return render_lock(self.max_load if step.heavy else None, self.log, self._ticket(state, step), self._need(step))

    def _ticket(self, state: RunState, step: Step) -> Ticket:
        """Queue ticket: Shorts first, then the long video closest to done."""
        names = [s.name for s in steps_for(self.ctx.channel, self.run_dir)]
        done = sum(1 for n in names if (r := state.steps.get(n)) is not None and r.status in ("done", "approved"))
        kind = "short" if panel_flow._short(self.ctx) else "long"  # noqa: SLF001
        return Ticket(job=f"{self.ctx.channel.code}/{self.run_dir.name}:{step.name}", kind=kind,
                      progress=round(done / max(len(names), 1), 3))

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
        with self._admit(state, step):
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
            with self._admit(state, step):
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
    """Record approve/reject for a gate against the artifacts as they are now.

    Gates are opened by review panels; a manual approval is the back door and needs
    ``override`` (a reason), which is written to production.log.jsonl."""
    step = next((s for s in steps_for(channel, run_dir) if s.gate is gate), None)
    if step is None:
        raise ValueError(f"channel {channel.code} has no gate {gate.value!r}")
    if verdict == "approved" and not override.strip():
        raise ValueError(f"gate {gate.value} is approved by its review panel; a manual approve needs "
                         f'--override "reason"')
    if verdict == "approved":
        note = f"MANUAL OVERRIDE of the review panel: {override}. {note}".strip()
    if verdict == "approved" and gate is Gate.FINAL:
        report = json.loads((run_dir / qc.QC_REPORT).read_text(encoding="utf-8")) \
            if (run_dir / qc.QC_REPORT).is_file() else None
        if report is None:
            raise ValueError("no qc/qc_report.json yet; run the pipeline to the final gate first")
        if report["errors"]:
            note = f"OVERRIDE QC ({report['errors']} errors): {note}".strip()
    decision = Decision(gate.value, verdict, gate_fingerprint(run_dir, step), now_iso(), by=by, note=note)
    state = load_state(run_dir, channel.code).with_decision(decision)
    save_state(run_dir, state)
    _event(run_dir, gate=gate.value, verdict=verdict, note=note, by=by, override=override or None)
    if verdict == "approved" and gate is Gate.DECK and (run_dir / "deck.json").is_file():
        # what the next edit is compared against (scripts/fix_scope.py); panel approvals: panel_flow
        (run_dir / "review").mkdir(parents=True, exist_ok=True)
        shutil.copy2(run_dir / "deck.json", run_dir / APPROVED_DECK)
    item = run_dir / "review" / f"{gate.value}.decision.json"
    if item.is_file():
        data = json.loads(item.read_text(encoding="utf-8"))
        data.update(status=verdict, decided_at=decision.at, note=note, decided_fingerprint=decision.fingerprint)
        item.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return decision
