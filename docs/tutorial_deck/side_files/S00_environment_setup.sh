#!/usr/bin/env bash
# Stage 0: native Python environment for TRACE-JEPA flood SAR.
# On Apple Silicon, use native osx-arm64 Conda/Miniforge.

set -euo pipefail

git --version
uname -m
conda info | grep platform

conda create -n trace-jepa python=3.12 pip -y
conda activate trace-jepa
python --version
which python
