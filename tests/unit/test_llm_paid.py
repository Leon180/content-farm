"""The metered Anthropic API needs explicit consent (CF_ALLOW_PAID=1 / --allow-paid)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from content_farm.llm import paid
from content_farm.llm.client import LLMClient

REPO = Path(__file__).resolve().parents[2]


def test_llmclient_refuses_without_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_ALLOW_PAID", raising=False)
    with patch("anthropic.AsyncAnthropic") as sdk, pytest.raises(paid.PaidAPIRefused, match="CF_ALLOW_PAID"):
        LLMClient(api_key="k")
    sdk.assert_not_called()


def test_llmclient_allowed_with_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ALLOW_PAID", "1")
    with patch("anthropic.AsyncAnthropic") as sdk:
        LLMClient(api_key="k")
    sdk.assert_called_once()


def test_only_exact_one_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ALLOW_PAID", "true")
    assert not paid.allowed()


def test_argv_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_ALLOW_PAID", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        paid.consent_from_argv(["x.py", "--topic", "t"], "x.py")
    assert exit_info.value.code == 2
    assert paid.consent_from_argv(["x.py", "--allow-paid", "--topic", "t"], "x.py") == ["x.py", "--topic", "t"]
    assert paid.allowed()


@pytest.mark.parametrize("script", ["generate_script.py", "run_bot.py", "run_pipeline.py"])
def test_scripts_exit_without_allow_paid(script: str) -> None:
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"), "HOME": str(Path.home())}
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / script), "--topic", "x"], capture_output=True,
                          text=True, env=env, timeout=120, check=False)
    assert proc.returncode == 2, proc.stderr[-400:]
    assert "--allow-paid" in proc.stderr
