"""The resource gate ignores shells that only mention the busy pattern (2026-10-17 deadlock)."""

from __future__ import annotations

import subprocess

from content_farm.voice import local_worker


def test_busy_pids_skips_shell_wait_loops(monkeypatch) -> None:
    listing = ("16642 /bin/zsh -c for i in $(seq 1 30); do pgrep -f \"mlx_video|ffmpeg\"; done\n"
               "200 ffmpeg -i in.mp4 out.mp4\n"
               "300 /usr/bin/python3 /x/bin/mflux-generate --prompt cat\n"
               "400 pgrep -f mlx_video|ffmpeg\n")

    def fake_run(cmd, **kwargs):
        assert cmd[:2] == ["pgrep", "-fl"]
        return subprocess.CompletedProcess(cmd, 0, stdout=listing, stderr="")

    monkeypatch.setattr(local_worker.subprocess, "run", fake_run)
    assert local_worker.busy_pids("mlx_video|mflux|ffmpeg") == [200, 300]
