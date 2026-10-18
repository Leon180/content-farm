"""Client for ``scripts/local_tts_worker.py`` — one local model process per voice run.

The worker runs in the TTS venv (``CF_LOCAL_TTS_PYTHON``), so heavy packages
(mlx, mlx_audio) never enter the repo's .venv. Before it starts, a resource
gate waits until no video/image model or render is running and enough memory
is free (VoxCPM2 peaks around 21.7 GB system-wide, Qwen3-TTS around 24.5 GB on
a 32 GB machine), and a machine-wide lock keeps a second local model from
loading at the same time. The model stays loaded for the whole video and is
released by ``close()``.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKER_SCRIPT = REPO_ROOT / "scripts" / "local_tts_worker.py"
POLL_SECONDS = 60
_FREE_PCT = re.compile(r"free percentage:\s*(\d+)%")


class LocalWorkerError(RuntimeError):
    """The local TTS/ASR worker could not start or a request failed."""


def snapshot_dir(hub_dir: str, repo_id: str) -> Path:
    """The local snapshot of a Hugging Face repo inside a hub cache; never downloads."""
    hub = Path(hub_dir).expanduser()
    snapshots = hub / f"models--{repo_id.replace('/', '--')}" / "snapshots"
    found = sorted(snapshots.glob("*/config.json"), key=lambda p: p.stat().st_mtime) if snapshots.is_dir() else []
    if not found:
        raise LocalWorkerError(f"model {repo_id!r} not found under {hub} (expected {snapshots}/<rev>/config.json)")
    return found[-1].parent


@dataclass(frozen=True)
class GateConfig:
    busy_pattern: str = "mlx_video|mflux|ffmpeg"
    min_free_pct: int = 25
    max_wait_s: int = 1800
    lock_path: str = "~/.cache/content-farm/local_tts.lock"


_SHELLS = ("sh", "bash", "zsh", "pgrep", "grep", "timeout")


def busy_pids(pattern: str) -> list[int]:
    """PIDs whose command line matches ``pattern`` (pgrep -fl), excluding this process and shells /
    pgrep wrappers that merely mention the pattern (2026-10-17: another job's `for … pgrep -f
    "mlx_video|…"` wait loop matched, and the two gates waited on each other)."""
    proc = subprocess.run(["pgrep", "-fl", pattern], capture_output=True, text=True, check=False)
    pids = []
    for line in proc.stdout.splitlines():
        pid, _, command = line.strip().partition(" ")
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        if Path(command.split(" ", 1)[0]).name in _SHELLS:
            continue
        pids.append(int(pid))
    return pids


def free_memory_pct() -> int | None:
    """System-wide free memory percentage from ``memory_pressure -Q`` (None if unreadable)."""
    try:
        proc = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True, check=False)
    except OSError:
        return None
    match = _FREE_PCT.search(proc.stdout)
    return int(match.group(1)) if match else None


async def wait_for_resources(
    config: GateConfig,
    *,
    probe_busy: Callable[[str], list[int]] = busy_pids,
    probe_free: Callable[[], int | None] = free_memory_pct,
    sleep: Callable[[float], object] = asyncio.sleep,
    busy_only: bool = False,
) -> int:
    """Wait until nothing heavy runs and free memory >= the floor. Returns seconds waited.
    ``busy_only``: between scenes, with our own model already loaded, free memory is ours to
    use — only wait for other heavy processes."""
    waited = 0
    while True:
        busy, free = probe_busy(config.busy_pattern), None if busy_only else probe_free()
        if not busy and (free is None or free >= config.min_free_pct):
            if waited:
                logger.info("Resource gate open after %ds (free=%s%%)", waited, free)
            return waited
        if waited >= config.max_wait_s:
            raise LocalWorkerError(
                f"resource gate: still busy after {waited}s (pids matching {config.busy_pattern!r}: "
                f"{busy[:5]}, free memory {free}% < {config.min_free_pct}%)")
        logger.info("Resource gate waiting: busy=%s free=%s%% (t=%ds)", busy[:5], free, waited)
        await sleep(POLL_SECONDS)
        waited += POLL_SECONDS


class LocalWorker:
    """Async JSON-lines client for one worker process; requests are serialized."""

    def __init__(self, python: str, gate: GateConfig, *, script: Path = WORKER_SCRIPT) -> None:
        self._python = str(Path(python).expanduser())
        self._gate = gate
        self._script = script
        self._proc: asyncio.subprocess.Process | None = None
        self._lock_handle: IO[str] | None = None
        self._slot = None                      # lanes.queue heavy slot when this worker queued itself
        self._io_lock = asyncio.Lock()
        self._load_lock = asyncio.Lock()
        self._loaded: set[str] = set()

    async def _start(self) -> None:
        if not Path(self._python).is_file():
            raise LocalWorkerError(f"local TTS python not found: {self._python} (CF_LOCAL_TTS_PYTHON)")
        await self._acquire_model_lock()
        await wait_for_resources(self._gate)
        env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"}
        env.pop("PYTHONPATH", None)
        self._proc = await asyncio.create_subprocess_exec(
            self._python, "-I", str(self._script),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=None, env=env,
            limit=1 << 20)
        logger.info("Local TTS worker started (pid %d)", self._proc.pid)

    async def _acquire_model_lock(self) -> None:
        """The machine-wide heavy queue (lanes.queue). Under ``produce.py run`` the runner already
        holds the slot (CF_HEAVY_SLOT); run on its own, this worker queues like any other job."""
        from content_farm.lanes.queue import SLOT_ENV, Ticket, heavy_slot

        if os.environ.get(SLOT_ENV):
            return
        slot = heavy_slot(Ticket(job=f"local-tts:pid{os.getpid()}", kind="other"), logger.info)
        await asyncio.to_thread(slot.__enter__)
        self._slot = slot

    async def _acquire_legacy_lock(self) -> None:
        path = Path(self._gate.lock_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("w")
        waited = 0
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if waited >= self._gate.max_wait_s:
                    handle.close()
                    raise LocalWorkerError(f"another local model holds {path} after {waited}s") from None
                logger.info("Local model lock %s held by another run; waiting", path)
                await asyncio.sleep(POLL_SECONDS)
                waited += POLL_SECONDS
        self._lock_handle = handle

    async def request(self, payload: dict) -> dict:
        async with self._io_lock:
            if self._proc is None:
                await self._start()
            elif payload.get("op") == "synth":
                # Another session may have started a video/image model or a render after we
                # loaded: pause (model stays loaded) rather than share the GPU with it.
                await wait_for_resources(self._gate, busy_only=True)
            assert self._proc is not None and self._proc.stdin is not None and self._proc.stdout is not None
            self._proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            await self._proc.stdin.drain()
            line = await self._proc.stdout.readline()
        if not line:
            raise LocalWorkerError(f"local TTS worker exited (code {self._proc.returncode}) during {payload['op']}")
        reply = json.loads(line)
        if not reply.get("ok"):
            raise LocalWorkerError(f"local worker {payload['op']} failed: {reply.get('error')}")
        return reply

    async def ensure_loaded(self, op: str, **fields: str) -> None:
        key = f"{op}:{fields.get('model_dir')}"
        async with self._load_lock:  # concurrent scenes must not each send a load
            if key in self._loaded:
                return
            reply = await self.request({"op": op, **fields})
            logger.info("Local worker %s %s loaded in %ss", op,
                        Path(fields.get("model_dir", "")).parent.parent.name, reply.get("load_s"))
            self._loaded.add(key)

    async def close(self) -> None:
        """Quit the worker (frees the model's memory) and release the machine-wide lock."""
        proc, self._proc = self._proc, None
        try:
            if proc is not None and proc.returncode is None:
                try:
                    assert proc.stdin is not None
                    proc.stdin.write(b'{"op": "quit"}\n')
                    await proc.stdin.drain()
                    proc.stdin.close()
                    await asyncio.wait_for(proc.wait(), timeout=60)
                except (asyncio.TimeoutError, BrokenPipeError, ConnectionResetError):
                    logger.warning("Local TTS worker did not quit cleanly; killing pid %d", proc.pid)
                    proc.kill()
                    await proc.wait()
                logger.info("Local TTS worker stopped (model unloaded)")
        finally:
            self._loaded.clear()
            slot, self._slot = self._slot, None
            if slot is not None:
                slot.__exit__(None, None, None)
            if self._lock_handle is not None:
                fcntl.flock(self._lock_handle, fcntl.LOCK_UN)
                self._lock_handle.close()
                self._lock_handle = None
