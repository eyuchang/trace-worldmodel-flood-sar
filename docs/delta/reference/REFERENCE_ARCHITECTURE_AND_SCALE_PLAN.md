# WF-DFLD-01-REFERENCE architecture and scale plan

Status: development design; no validation or confirmatory evidence  
Base: delivered Small commit `3f912bdf3fbacb679063da9ed2ce15a2330b91ab`  
Protocol: `WF_DFLD_01_REFERENCE_PROTOCOL_DRAFT.md`

## Purpose

Reference is the eight-island Flood-SAR integration scenario. It is not the
separate public demonstration domain and it is not an enlargement of the Small
runner. Reference needs a new event-sourced execution surface because its
required restarts, reordered evidence, late provider outcomes, crew cycles, and
compensation cannot be represented faithfully by Small's one-pass call loop.

This plan governs reversible Phase 0 architecture work. It does not freeze
scientific coefficients, validation seeds, operational authority, or paper
claims.

## Package boundaries

The implementation begins in the top-level companion package `trace_reference`
and will expose a separate orchestrator. Keeping it outside `trace_jepa` prevents
new Task 3 sources from invalidating the complete scientific-input inventory for
the already frozen Tasks 1 and 2 evidence. Stable public support may be imported
from `trace_jepa` only when a byte-preservation test proves that Small outputs
remain unchanged. A future freeze will define a complete Reference inventory.

| Component | Responsibility | Forbidden dependency |
|---|---|---|
| `domain` | frozen event, state, resource, crew, route, action, receipt, and recovery contracts | generators and runtime services |
| `geography` | offline source registry, clipping, topology, coordinate transforms, provenance | controller or hidden truth |
| `generation` | physical state, breach, exposure, incidents, observations, resources, telemetry | policy outcomes |
| `runtime` | event queue, controller-visible state, TRACE assessment, commitments, outcomes, recovery | hidden lineage or offline scoring |
| `routing` | time-dependent multimodal graph and deterministic path tie-breaking | Small's two-crossing shortcut |
| `capacity` | polynomial compatibility matching and post-run scoring | exponential incident bitmasks |
| `evaluation` | joins public/runtime artifacts to hidden truth after execution | online controller path |
| `provenance` | canonical artifacts, manifests, replay, execution receipts | ambient files or network state |

## Deterministic event machine

The runtime will process a totally ordered queue. An event key is
`(simulation_time, event_priority, stable_entity_id, event_digest)`. Priorities
are versioned and cover physical samples, observation creation, coordination
delivery, telemetry, decision deadlines, provider receipts, crew transitions,
restart, recovery, and censoring.

The persisted state boundary includes the queue cursor, public evidence ledger,
TRACE records, commitments, resource and crew beliefs, provider receipt inbox,
and idempotency keys. Restart reconstructs these bytes and must produce the same
continuation as uninterrupted execution. Hidden truth and future scripted events
are not part of controller recovery state.

## Route and access model

Reference uses an explicit directed multimodal graph, not an island-to-one-
crossing lookup. Edges identify mode, endpoints, distance, crossing/ferry
dependency, operability truth, controller belief, evidence time, travel model,
and boundary-connector status. Routing consumes only controller-visible beliefs;
offline evaluation may compare the chosen route with route truth later.

Path selection uses a documented lexicographic tie break after total generalized
travel cost. Re-routing occurs only at registered checkpoints. Ferry and air
assets remain distinct from road and boat capabilities.

## Resource, crew, and action contracts

Physical assets and crews are separate entities. Availability requires a
compatible asset, qualified rested crew, authority-visible activation, route,
fuel or consumables where modeled, and non-conflicting commitment. Telemetry is
a lossy observation of physical resource state.

Every action class declares reversibility, physical effect, dependency type,
provider interface, outcome evidence, and available compensation. Compensation
repairs a commitment chain; it never claims to reverse an irreversible physical
effect.

## Matching and complexity

Small's exact incident-bitmask matcher is unsuitable at Reference scale.
Reference will use deterministic polynomial maximum-weight bipartite or flow
matching with integer weights and canonical tie-breaking. Fixture tests must
show equivalence to exhaustive matching on Small-sized cases. Cardinality and
runtime profiling will determine whether reconciliation also needs a stable
temporal/spatial index.

Person trajectories remain change-point sequences rather than materialized
five-minute samples. Large line-oriented artifacts are streamed through
canonical writers. One-seed profiling precedes any performance freeze; current
15-minute and 2-GiB limits are provisional engineering targets only.

## Scientific separation

- The scripted `T+52 h` breach tests anticipation, authorization, response, and
  recovery. It cannot show that a policy caused or prevented the breach.
- Burn-in state and cost carry into `T0`, but future breach truth is never
  controller-visible.
- `phi` changes evidence delivery or approval behavior, not raw observations.
- `kappa` changes inventory, `mu` mobilization, `delta` physical degradation,
  and `iota` observation/telemetry quality.
- Authentication establishes source and envelope integrity, not truthfulness.
- Nominal and faulted runs share byte-identical exogenous artifacts.
- LEAP, if studied later, operates only after TRACE admissibility and uses a
  separate protocol and seed namespace.

## Gates before implementation advances

Phase 0 requires Small hash verification, Reference-only schemas, no
confirmatory seed surface, a complete import/dependency map, and scale
benchmarks. Phase 1 requires verified source identity, redistribution review,
offline source snapshots or locator-only records, topology QA, and explicit
labels for every approximate or non-operative field.

The project must not freeze physical calibration, legal/authority semantics,
the 2,900-report denominator, the 95/hour interpretation, a 4:1 load gate,
policy endpoints, or validation seeds until the protocol ambiguity ledger is
resolved.
