"""Consent for the metered Anthropic API (Leon 2026-10-18).

The production line writes and reviews through Claude Code / ``claude -p`` on the subscription.
Anything that would call the pay-per-token API through ``LLMClient`` must be started with
``--allow-paid`` (scripts) or ``CF_ALLOW_PAID=1`` (env); ``LLMClient`` refuses to build otherwise,
so new code cannot bypass it.
"""

from __future__ import annotations

import os
import sys

ALLOW_ENV = "CF_ALLOW_PAID"
FLAG = "--allow-paid"


class PaidAPIRefused(RuntimeError):
    """The metered API was about to be used without explicit consent."""


def allowed() -> bool:
    return os.environ.get(ALLOW_ENV) == "1"


def check() -> None:
    if not allowed():
        raise PaidAPIRefused(f"LLMClient calls the metered Anthropic API; set {ALLOW_ENV}=1 or pass {FLAG} "
                             f"(the production line uses claude -p on the subscription instead)")


def consent_from_argv(argv: list[str], script: str) -> list[str]:
    """For script entry points: strip ``--allow-paid`` and set the env flag, or explain and exit 2."""
    if FLAG not in argv:
        print(f"{script} 會用 CF_ANTHROPIC_API_KEY 呼叫按量計費的 Anthropic API；確定要付費才加 {FLAG}。"
              f"（現行流程用 produce.py / claude -p 走訂閱）", file=sys.stderr)
        raise SystemExit(2)
    os.environ[ALLOW_ENV] = "1"
    return [arg for arg in argv if arg != FLAG]
