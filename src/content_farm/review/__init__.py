"""Agent review panels wired into the production pipeline (Leon 2026-10-17, e0ac3ac36faf).

Every stage: producer agent → review panel (``claude -p`` subprocesses the pipeline launches
itself) → threshold → pass, or send a fix list back to the step that caused it.
The rules that must not be bypassed live in code (``config.RULES``), not in prompts.
"""
