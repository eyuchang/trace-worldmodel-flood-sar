# Lab 5 - From latent output to typed claims

## Goal

Prevent a vector or free-form narrative from becoming operational evidence without a declared semantic interface.

## Tasks

1. Define at least four grounded predicates with units and horizons.
2. Split data into training, calibration, and test scenarios.
3. Fit or implement probes for route access, deadline arrival, hazard, and resource margin.
4. Calibrate thresholds on the calibration split only.
5. Emit `WorldModelEvidence` objects carrying predictor, probe, support, uncertainty, horizon, and data versions.
6. Test the central case: high confidence plus low model support must yield `HOLD`.

## Suggested predicates

```text
route_open(route_id, horizon)
arrival_before(asset_id, deadline)
rescue_capacity_sufficient(asset_id, people_count)
resource_margin_positive(asset_id, horizon)
```

## Exit test

Every operational claim is grounded and versioned; no claim is created by merely asking an LLM to narrate an embedding.
