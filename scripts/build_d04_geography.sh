#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python -m trace_jepa.workbench.geography_builder \
  --config configs/geography/antioch_delta_real_v1.yaml
