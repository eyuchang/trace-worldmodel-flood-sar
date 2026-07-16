#!/usr/bin/env bash
# Stage 2: render the operational cast and the two knowledge views.

set -euo pipefail

trace-jepa-visualize \
  --scenario configs/scenarios/riverside_flood_v1.yaml \
  --output artifacts/runs/scenario_brief

# macOS helpers:
open artifacts/runs/scenario_brief/operational_cast.svg
open artifacts/runs/scenario_brief/mission_controller_knowledge.svg
open artifacts/runs/scenario_brief/simulation_ground_truth.svg
