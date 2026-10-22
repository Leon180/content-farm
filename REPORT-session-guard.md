# Session size guard (cf-cost-fix item 6)

Token audit 10-17..19: 73% of the nominal spend was cache re-reads of long conversations (worker prefixes 440–570k
tokens, orchestrator 500k). Each tool call re-reads the whole prefix, so past ~300k tokens a fresh session that reads a
written handoff is cheaper per call. `scripts/session_guard.py` measures the size instead of guessing: the last main-thread
assistant message of the transcript carries the API's own usage (`input + cache_creation + cache_read` = the prefix that
call read). Measured on this worker's own transcript: 370,709 tokens at the time the guard was written (exit 3).

```
python3 scripts/session_guard.py                        # newest transcript of the cwd; exit 0 ok / 1 ≥80% / 3 ≥ limit / 2 unknown
python3 scripts/session_guard.py --transcript X.jsonl   # any session, e.g. the orchestrator's own
python3 scripts/session_guard.py --hook                 # PostToolUse hook (stdin payload → additionalContext nudge)
```

Limit: `--limit N`, `CF_SESSION_TOKEN_LIMIT`, default 300,000.

## Worker side — what to add (not applied: it lives outside this repo)

1. **Worker brief** (dispatch's contract appendix, next to "抗中斷"): *"Every ~10 tool calls run
   `python3 <repo>/scripts/session_guard.py`; on exit 3 finish the current segment, write the handoff into the REPORT's
   progress log (done / next / exact commands / open decisions), commit, report 'suggest a new session' to main, stop."*
2. **Hook** (enforcement, `~/.claude/settings.json` or the worker settings template) — nudges after every tool call once
   over the limit; silent otherwise:

   ```json
   {"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [
     {"type": "command", "command": "python3 /Users/lileon/project/content-farm/scripts/session_guard.py --hook"}]}]}}
   ```

   The hook never blocks; it only adds the handoff instruction to the context. `python3` is on the allow list; the script
   reads one file tail (≤ 4 MB) per call.

## Orchestrator side

Same script against its own transcript, e.g. from the dispatch loop's tick:
`python3 scripts/session_guard.py --transcript ~/.claude/projects/<its project>/<session>.jsonl --json`.
At exit 3 the orchestrator writes its board state (in-flight jobs, pending decisions, mail ids) into a handoff file and
the user starts a fresh orchestrator session from it. The hook above works for it unchanged.

## What this does not do

It cannot end a session by itself (a hook can only add context or block a call). The enforcement is the nudge plus the
rule; an orchestrator can additionally refuse to count a worker as healthy while its guard exit is 3.
