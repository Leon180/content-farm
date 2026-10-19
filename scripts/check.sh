#!/usr/bin/env bash
# Rule check before every commit (Leon 2026-10-18: rules live in code + config + tests).
#   scripts/check.sh          config validation + the rule tests (review panels, gates, queue, paid guard, schedule)
#   scripts/check.sh --full   config validation + the whole unit suite
# Hooked by .pre-commit-config.yaml; also fine to run by hand. Exits non-zero on any failure.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${CF_PYTHON:-}"
if [[ -z "$PY" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then PY="$ROOT/.venv/bin/python"
  elif [[ -x "$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)/../.venv/bin/python" ]]; then
    PY="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)/../.venv/bin/python"
  else PY="python3"; fi
fi
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

echo "· review_panels.yaml + channels/*.yaml"
"$PY" -c "
from content_farm.review.config import load_review
from content_farm.production.channels import load_all
from content_farm.production.publish_slot import load_plan
channels = load_all()
for c in channels:
    load_review(c.code)
    load_plan(c.code)
print(f'  ok: review config valid for {len(channels)} channels')
"

if [[ "${1:-}" == "--full" ]]; then
  "$PY" -m pytest -q -p no:cacheprovider "$ROOT/tests/unit" \
    --deselect "tests/unit/test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results[asyncio]"
else
  "$PY" -m pytest -q -p no:cacheprovider \
    "$ROOT/tests/unit/test_review_config.py" "$ROOT/tests/unit/test_review_verdicts.py" \
    "$ROOT/tests/unit/test_review_gate.py" "$ROOT/tests/unit/test_review_runner.py" \
    "$ROOT/tests/unit/test_lanes_queue.py" "$ROOT/tests/unit/test_lanes_resources.py" \
    "$ROOT/tests/unit/test_lanes_heavy_rules.py" "$ROOT/tests/unit/test_llm_paid.py" \
    "$ROOT/tests/unit/test_publish_slot.py" "$ROOT/tests/unit/test_production_runner.py" \
    "$ROOT/tests/unit/test_production_channels.py" "$ROOT/tests/unit/test_shared_path_guard.py" \
    "$ROOT/tests/unit/test_review_usage.py"
fi
