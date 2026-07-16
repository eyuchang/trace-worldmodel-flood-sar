# Stepwise Migration from D0.1

The recommended process is one verified increment at a time.

## Step 1, this release

- route-constrained navigation;
- edge interruption;
- visible reasoning cycles for S1-S5 changes;
- decluttered decision UI.

Guide: `docs/STEP_01_ROUTE_SAFE_NAVIGATION.md`.

## Step 2, this release

- complete boat rescue lifecycle: pickup, evacuation, safe handoff, standby;
- separate TRACE record for the return-to-safety action;
- explicit current-count versus additional-people alert semantics;
- one incident marker per active same-location request;
- recognizable animated SVG boat and drone assets.

Guide: `docs/STEP_02_RESCUE_LIFECYCLE_AND_ANIMATION.md`.

## Step 3, next

- `TraceOperationalBinding`;
- dependency index from observations and forecasts to records and commitments;
- material-change detector;
- proactive re-audit and commitment revocation.

## Step 4

- continuous drone coverage;
- alert priority queue;
- interrupt/resume token;
- observation footprints and continuously updated reconnaissance state.

## Step 5

- weather and hydrology forecast ensembles;
- predicted edge closure time;
- clearance validity horizon;
- safe-node hold and reroute.

## Step 6

- four UI modes: Operations, Reasoning, Experiment, Replay;
- S1-S5 impact preview before applying a change;
- experiment protocol and deterministic attribution.

## Step 7

- V-JEPA encoder service;
- flood-domain action-conditioned predictor;
- calibrated semantic probes, support, OOD, and uncertainty.
