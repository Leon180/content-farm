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

from content_farm import paths
from content_farm.explainer.deck import load_deck
from content_farm.lanes.queue import Ticket, heavy_slot
from content_farm.lanes.resources import Need, load_config, need_for
from content_farm.production import auto_fix_fallback, panel_flow, publish, qc, timing
from content_farm.production.channels import Channel, Gate
from content_farm.production.review import write_review
from content_farm.production.state import (
    Decision, RunState, StepRecord, fingerprint, load_state, now_iso, save_state,
)
from content_farm.production.steps import (REPO_ROOT, VOICE_SPOKEN_FILE, Command, Context, Step, steps_for,
                                           voice_choice, voice_nothing_to_synthesize)
from content_farm.review.freeze import FROZEN_FILE, frozen_steps

LOCK_PATH = paths.render_lock_path()   # legacy, unused; heavy work goes through lanes.queue
SCHEDULE_FILE = "production.schedule.json"
APPROVED_DECK = "review/deck.approved.json"   # snapshot at deck approval (fix scope baseline)
LOAD_POLL_SECONDS = 30


class Outcome(str, Enum):
    COMPLETE = "complete"
    GATE = "waiting_gate"
    AGENT = "waiting_agent"
    PAID = "needs_paid_consent"
    PREREQ = "missing_prerequisite"   # an input only another step can make (the reference voice); no ticket queued
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


def _voice_ref_product(ctx: Context) -> str:
    """Queue product name of a channel's reference voice (what voice-design ``--provides``)."""
    return f"voice-ref:{ctx.channel.code}"


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
        """One pass over the steps. The timing ledger gets a start and an end event, and ``timing.json`` is
        refreshed when the pass ends (machine time vs. waiting for a person: ``production.timing``)."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        timing.record_event(self.run_dir, event="run_start", pid=os.getpid())
        result = RunResult(Outcome.FAILED, "", "run aborted by an exception")
        try:
            result = self._run(until=until, force=force)
            return result
        finally:
            timing.record_event(self.run_dir, event="run_end", outcome=result.outcome.value, step=result.step)
            self._write_timing()

    def _write_timing(self) -> None:
        try:
            timing.write(self.run_dir, channel=self.ctx.channel.code, queue_history=paths.heavy_queue_dir() / "history.jsonl")
        except (OSError, ValueError, KeyError) as exc:        # the ledger must never stop a production run
            self.log(f"timing.json not written: {type(exc).__name__}: {exc}")

    def _run(self, *, until: str | None, force: frozenset[str]) -> RunResult:
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
        if step.name in frozen_steps(self.run_dir) and _outputs_present(self.run_dir, step):
            return self._frozen_agent(state, step, record, pending_rework), None
        if not _outputs_present(self.run_dir, step) or pending_rework:
            if self.ctx.options.auto_agents and step.name in panel_flow.PRODUCER_STEPS:
                before = fingerprint(self.run_dir, step.outputs)
                gate = panel_flow.rework_gate(record.note) if pending_rework and record is not None else None
                with self._admit(state, step):
                    failure = panel_flow.run_producer(self.ctx, step.name, self.log, gate=gate)
                if failure is None and not _outputs_present(self.run_dir, step):
                    failure = f"{step.title}：產出 agent 結束但缺 {', '.join(step.outputs)}"
                if (failure is None and pending_rework and fingerprint(self.run_dir, step.outputs) == before
                        and not auto_fix_fallback.is_auto_fix(self.run_dir, gate or step.name)):   # the one auto fix may change nothing
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

    def _frozen_agent(self, state: RunState, step: Step, record: StepRecord | None, pending_rework: bool) -> RunState:
        """Frozen for this run (production.frozen.json): never redone or re-verified. Its outputs may
        still change through a later step (the script adding a source to sources.json); that is logged."""
        inputs = fingerprint(self.run_dir, step.outputs)
        if record is not None and record.status == "done" and record.inputs == inputs and not pending_rework:
            return state
        self.log(f"❄ {step.name}: 凍結（{FROZEN_FILE}），不重做、不重驗")
        _event(self.run_dir, step=step.name, frozen=True, skipped_rework=pending_rework,
               inputs_before=record.inputs if record else None, inputs_now=inputs)
        return state.with_step(step.name, StepRecord("done", now_iso(), inputs=inputs, note="frozen"))

    def _frozen_gate(self, state: RunState, step: Step, current: str) -> tuple[RunState, RunResult | None]:
        """A frozen gate keeps its earlier approval (the panel is not re-run); without one the run stops."""
        assert step.gate is not None
        decision = state.decisions.get(step.gate.value)
        if decision is None or decision.verdict != "approved":
            message = f"{step.title}：{FROZEN_FILE} 凍結了這個閘門，但它沒有先前的核可"
            return state, RunResult(Outcome.FAILED, step.name, message)
        if decision.fingerprint != current:
            self.log(f"❄ {step.name}: 凍結，沿用 {decision.at} 的核可（輸入已由後面步驟變更）")
            _event(self.run_dir, step=step.name, frozen=True, approved_fingerprint=decision.fingerprint,
                   inputs_now=current, by=decision.by)
        record = StepRecord("approved", decision.at, inputs=current, note=f"frozen; by {decision.by}")
        return state.with_step(step.name, record), None

    def _gate(self, state: RunState, step: Step, forced: bool) -> tuple[RunState, RunResult | None]:
        assert step.gate is not None
        current = gate_fingerprint(self.run_dir, step)
        if step.name in frozen_steps(self.run_dir):
            return self._frozen_gate(state, step, current)
        if state.approved(step.gate.value, current):
            decision = state.decisions[step.gate.value]
            record = StepRecord("approved", decision.at, inputs=current, note=f"by {decision.by}")
            return state.with_step(step.name, record), None
        stage = panel_flow.stage_of(self.ctx, step.gate)
        if stage == "script_structure":
            kept = panel_flow.structure_kept(self.ctx, state, current, self.log)
            if kept is not None:
                return kept, None
        if stage is not None:
            with self._admit(state, step):
                if stage == "script_facts":
                    delta = panel_flow.facts_delta(self.ctx, state, step, current, self.log)
                    if delta is not None:
                        return delta
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
        if step.name == "voice" and voice_nothing_to_synthesize(self.ctx):
            # 0 sentences to synthesize: re-time and re-align only, the TTS model never loads
            return need_for("voice_retime", config, default=Need(mem_gb=1.0, cpu_cores=1))
        default = need_for("heavy_default", config) if step.heavy else Need()
        return need_for(step.name, config, default=default)

    @contextmanager
    def _admit(self, state: RunState, step: Step) -> Iterator[None]:
        """Entry check before a step does work (cloud lane too): queue until its need fits. A wait of a second
        or more goes to the timing ledger with the step it held up."""
        began = time.monotonic()
        need = self._need(step)
        with render_lock(self.max_load if step.heavy else None, self.log, self._ticket(state, step), need):
            waited = time.monotonic() - began
            if waited >= 1.0:
                timing.record_event(self.run_dir, event="queue", step=step.name, waited_s=round(waited, 1),
                                    mem_gb=need.mem_gb, gpu=need.gpu)
            yield

    def _missing_voice_reference(self, step: Step) -> str:
        """A local clone voice without its reference clip must not queue: its ticket would age into an
        anti-starvation reservation and hold back the voice-design job that makes the clip."""
        if step.name != "voice" or self.ctx.options.mock_voice or not step.heavy_if(self.ctx):
            return ""
        reference = voice_choice(self.ctx).reference
        if reference is None or reference.audio_path().is_file():
            return ""
        return (f"參考聲不存在：{reference.audio_path()}。先排 voice-design（scripts/heavy --step voice_design "
                f"--provides {_voice_ref_product(self.ctx)} -- … scripts/design_voice.py …），再重跑；"
                f"這一步不登記佇列票，以免預約擋住 voice-design")

    def _ticket(self, state: RunState, step: Step) -> Ticket:
        """Queue ticket: Shorts first, then the long video closest to done."""
        names = [s.name for s in steps_for(self.ctx.channel, self.run_dir)]
        done = sum(1 for n in names if (r := state.steps.get(n)) is not None and r.status in ("done", "approved"))
        kind = "short" if panel_flow._short(self.ctx) else "long"  # noqa: SLF001
        needs = _voice_ref_product(self.ctx) if step.name == "voice" and step.heavy_if(self.ctx) else ""
        return Ticket(job=f"{self.ctx.channel.code}/{self.run_dir.name}:{step.name}", kind=kind,
                      progress=round(done / max(len(names), 1), 3), needs=needs)

    def _cmd_inputs(self, step: Step) -> str:
        files = fingerprint(self.run_dir, step.inputs)
        if step.identity is None:
            return files
        identity = hashlib.sha256(step.identity(self.ctx).encode("utf-8")).hexdigest()[:16]
        return f"{files}+{identity}"

    def _idle(self, step: Step) -> bool:
        """The step's own cheap check says every output is already there; any error means "has work"."""
        if step.has_work is None:
            return False
        try:
            return not step.has_work(self.ctx)
        except Exception as exc:  # noqa: BLE001 - a broken check must never skip work
            self.log(f"{step.name}: has_work check failed ({type(exc).__name__}: {exc}); running the step")
            return False

    def _cmd(self, state: RunState, step: Step, forced: bool) -> tuple[RunState, RunResult | None]:
        assert step.command is not None
        if self._fresh(state, step, self._cmd_inputs(step), forced):
            return state, None
        if not forced and self._idle(step):
            self.log(f"✓ {step.name}: nothing to do, no machine slot taken")
            _event(self.run_dir, step=step.name, exit_code=0, seconds=0.0, lane="local", skipped="no work")
            return state.with_step(step.name, StepRecord("done", now_iso(), 0.0, 0, self._cmd_inputs(step))), None
        if step.paid(self.ctx) and not self.ctx.options.allow_paid:
            message = f"{step.title} 會呼叫付費 API；加 --allow-paid 或 --mock-voice"
            return state, RunResult(Outcome.PAID, step.name, message)
        if step.identity is not None:
            identity = step.identity(self.ctx)
            self.log(f"{step.name}: {identity}")
            _event(self.run_dir, step=step.name, identity=identity)
        missing = self._missing_voice_reference(step)
        if missing:
            self.log(f"⏸ {step.name}: {missing}")
            return state, RunResult(Outcome.PREREQ, step.name, missing)
        command = step.command(self.ctx)
        with self._admit(state, step):
            state, result = self._execute(state, step, command, lambda: self._cmd_inputs(step))
        if step.name == "voice" and result is None and step.identity is not None:
            (self.run_dir / VOICE_SPOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
            (self.run_dir / VOICE_SPOKEN_FILE).write_text(json.dumps({"key": step.identity(self.ctx), "at": now_iso()},
                                                                     ensure_ascii=False), encoding="utf-8")
        return state, result

    def _execute(
        self, state: RunState, step: Step, command: Command, inputs_after: Callable[[], str],
    ) -> tuple[RunState, RunResult | None]:
        self.log(f"▶ {step.name}: {step.title}")
        started = time.monotonic()
        code = self.executor(command, self.run_dir / "logs" / f"{step.name}.log")
        seconds = round(time.monotonic() - started, 1)
        _event(self.run_dir, step=step.name, exit_code=code, seconds=seconds,
               lane="local" if step.kind == "cmd" else "cloud")
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
