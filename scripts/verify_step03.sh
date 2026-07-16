#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

printf '\n[1/3] GeoJSON overlay contract tests\n'
python -m pytest -ra tests/test_maplibre_geojson_overlay.py

printf '\n[2/3] Full Python suite\n'
python -m pytest -ra

printf '\n[3/3] JavaScript syntax checks\n'
NODE_BIN=""
if [[ -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/node" ]]; then
  NODE_BIN="${CONDA_PREFIX}/bin/node"
elif command -v node >/dev/null 2>&1; then
  NODE_BIN="$(command -v node)"
else
  echo "Node is not installed; JavaScript syntax check cannot run." >&2
  exit 1
fi
printf 'Using Node: %s\n' "$NODE_BIN"
"$NODE_BIN" --check src/trace_jepa/workbench/static/maplibre_overlays.js
"$NODE_BIN" --check src/trace_jepa/workbench/static/app.js

printf '\nD0.2 Step 3 verification passed.\n'
