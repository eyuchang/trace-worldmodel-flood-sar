#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

export PYTHONPATH="${PYTHONPATH:-}:$repo_root/src"

python -m pytest tests/test_rescue_lifecycle_and_alert_merge.py -q
python -m pytest -q
node --check src/trace_jepa/workbench/static/app.js

echo "D0.2 Step 2 verification passed."
