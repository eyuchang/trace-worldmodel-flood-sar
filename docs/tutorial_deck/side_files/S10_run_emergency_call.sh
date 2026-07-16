#!/usr/bin/env bash
set -euo pipefail

trace-jepa-call \
  --call-file examples/calls/riverside_call.txt \
  --output artifacts/runs/call_001

cat artifacts/runs/call_001/timeline.txt
open artifacts/runs/call_001/figures/mission_controller_knowledge.svg
open artifacts/runs/call_001/figures/action_timeline.svg
