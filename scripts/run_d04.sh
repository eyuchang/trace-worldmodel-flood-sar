#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

GEOGRAPHY_DIR="${1:-data/geography/antioch_delta_real_v1}"

if [[ ! -f "$GEOGRAPHY_DIR/scenario.json" ]]; then
  echo "Real geography has not been built."
  echo
  echo "Run:"
  echo "  ./scripts/build_d04_geography.sh"
  exit 1
fi

exec trace-jepa-d04 \
  --host 127.0.0.1 \
  --port 8020 \
  --geography "$GEOGRAPHY_DIR"
