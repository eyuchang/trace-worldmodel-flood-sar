#!/usr/bin/env bash
set -euo pipefail

mode="${1:-core}"

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
trace-jepa-verify
pytest

if [[ "$mode" == "jepa" ]]; then
  python -m pip install -e ".[jepa]"
  trace-jepa-download --model vjepa2_1_vit_base_384
elif [[ "$mode" != "core" ]]; then
  echo "usage: $0 [core|jepa]" >&2
  exit 2
fi

echo "TRACE-WorldModel $mode environment is ready."
