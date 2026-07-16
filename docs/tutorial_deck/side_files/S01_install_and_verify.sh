#!/usr/bin/env bash
# Stage 1: install the laptop-safe core project. No PyTorch or V-JEPA yet.

set -euo pipefail

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
trace-jepa-verify
pytest
