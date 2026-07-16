#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="${PYTHONPATH:-src}"
pytest tests/test_navigation_and_reasoning.py -q
pytest -q
