#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[1/4] Python syntax"
python -m py_compile \
  src/trace_jepa/workbench/d05_server.py

echo
echo "[2/4] D0.5 focused tests"
python -m pytest -o addopts= -ra \
  tests/test_d05_concurrent_scheduling.py

echo
echo "[3/4] Full Python suite"
python -m pytest -o addopts= -ra

echo
echo "[4/4] Browser JavaScript syntax"

NODE_BIN="${CONDA_PREFIX:-}/bin/node"

if [[ ! -x "$NODE_BIN" ]]; then
  NODE_BIN="$(command -v node)"
fi

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/trace_d05_js.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT
TMP_JS="$TMP_DIR/check.js"

python - "$TMP_JS" <<'PY'
from pathlib import Path
import re
import sys

html = Path(
    "src/trace_jepa/workbench/d05_static/index.html"
).read_text(encoding="utf-8")

scripts = [
    body.strip()
    for body in re.findall(
        r"<script(?:\s[^>]*)?>(.*?)</script>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if body.strip()
]

Path(sys.argv[1]).write_text(
    "\n\n".join(scripts) + "\n",
    encoding="utf-8",
)
PY

"$NODE_BIN" --check "$TMP_JS"

echo
echo "D0.5 verification passed."
