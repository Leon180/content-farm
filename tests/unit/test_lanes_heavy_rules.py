"""Hook classifier cases (REPORT-review-panels.md lists the same table for the PreToolUse hook)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from content_farm.lanes.heavy_rules import classify

REPO = Path(__file__).resolve().parents[2]

BLOCK = [
    "ffmpeg -i in.mov -c:v libx264 out.mp4",
    "/opt/homebrew/bin/ffmpeg -y -i a.mp4 b.mp4",
    "cd output && ffmpeg -i a.wav a.mp3",
    "PYTHONPATH=src .venv/bin/python scripts/media_to_visual.py --run-dir output/x",
    "python scripts/mascot_overlay.py --run-dir output/x",
    "python scripts/run_stage.py --stage voice --run-dir output/x",
    "python -m mlx_video.generate --prompt cat",
    "mflux-generate --model schnell --prompt cat",
    "~/.local/share/qwen3-tts/.venv/bin/python scripts/local_tts_worker.py",
    "python ~/.local/share/content-farm-music/ACE-Step/infer.py",
    "mlx_whisper audio.mp3",
    "echo start; nohup python scripts/illustrate.py --run-dir x &",
]
ALLOW = [
    "scripts/heavy --label transcode -- ffmpeg -i in.mov out.mp4",
    "/Users/me/content-farm/scripts/heavy -- python scripts/media_to_visual.py --run-dir x",
    "PYTHONPATH=src .venv/bin/python scripts/produce.py run --run-dir output/x",
    "python scripts/produce.py queue",
    "ffprobe -v error -show_format a.mp4",
    "ffmpeg -version",
    "pgrep -fl ffmpeg",
    "git log --oneline",
    "python -m pytest tests/unit",
    "grep -rn ffmpeg_path src/",
]


@pytest.mark.parametrize("command", BLOCK)
def test_heavy_commands_outside_the_queue_are_blocked(command):
    verdict = classify(command)
    assert verdict.block, command
    assert "scripts/heavy" in verdict.why


@pytest.mark.parametrize("command", ALLOW)
def test_wrapped_read_only_and_ordinary_commands_pass(command):
    assert not classify(command).block, command


def test_cli_check_exit_codes():
    script = REPO / "scripts" / "heavy"
    blocked = subprocess.run([sys.executable, str(script), "--check", "ffmpeg -i a b"], capture_output=True, text=True)
    allowed = subprocess.run([sys.executable, str(script), "--check", "scripts/heavy -- ffmpeg -i a b"],
                             capture_output=True, text=True)
    assert blocked.returncode == 2 and '"block": true' in blocked.stdout
    assert allowed.returncode == 0
