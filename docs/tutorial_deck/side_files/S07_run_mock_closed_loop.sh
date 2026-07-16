#!/usr/bin/env bash
# Stage 7: run the complete deterministic closed-loop demo.

set -euo pipefail

trace-jepa-demo --output artifacts/runs/deck_walkthrough
cat artifacts/runs/deck_walkthrough/summary.json

# Check the saved records and commitments.
find artifacts/runs/deck_walkthrough -maxdepth 3 -type f | sort
