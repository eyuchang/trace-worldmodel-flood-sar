#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[1/4] Python syntax"
python -m py_compile \
  src/trace_jepa/workbench/geography_builder.py \
  src/trace_jepa/workbench/real_geography.py \
  src/trace_jepa/workbench/d04_server.py

echo
echo "[2/4] D0.4 focused tests"
python -m pytest -ra \
  tests/test_d04_real_geography.py

echo
echo "[3/4] Full Python suite"
python -m pytest -ra

echo
echo "[4/4] Browser JavaScript syntax"

NODE_BIN="${CONDA_PREFIX:-}/bin/node"

if [[ -x "$NODE_BIN" ]]; then
  NODE="$NODE_BIN"
elif command -v node >/dev/null 2>&1; then
  NODE="$(command -v node)"
else
  echo "Node is not available."
  exit 1
fi

TMP_JS="$(mktemp -t trace_d04_XXXXXX.js)"

python - "$TMP_JS" <<'PY'
from pathlib import Path
import sys

html = Path(
    "src/trace_jepa/workbench/d04_static/index.html"
).read_text(encoding="utf-8")

start = html.find("<script>\n")
end = html.rfind("</script>")

if start < 0 or end < 0 or end <= start:
    raise SystemExit("Could not locate the inline D0.4 script.")

Path(sys.argv[1]).write_text(
    html[start + len("<script>\n"):end],
    encoding="utf-8",
)
PY

"$NODE" --check "$TMP_JS"
rm -f "$TMP_JS"

echo
echo "D0.4 verification passed."
