# From Flood Mission to TRACE Record

This walkthrough connects the visible rescue scenario to the durable TRACE artifacts. The numerical predictions are deterministic teaching fixtures, not empirical findings.

## 1. What exists before any reasoning

### Flood Environment hidden state

```text
north_channel = blocked
south_detour = open
```

### Mission Controller knowledge

```text
north_channel = unknown
south_detour = reported open
```

The hidden blockage is not passed to the Planner, World Model, or TRACE Gate.

## 2. Grounded candidate action

The Planner proposes a concrete command rather than an opaque label:

```yaml
action_type: dispatch_rescue_boat
actor_id: rescue_boat_1
origin: rescue_base
destination: riverside_apartments
route_id: north_channel
parameters:
  people_count: 4
  deadline_s: 1200
```

The Planner has only proposed the action. Nothing has been authorized.

## 3. Model-conditional prediction

The toy World Model emits:

```text
predicted plan success probability: 0.92
claim confidence:                    0.92
model support:                       0.28
out-of-distribution score:           0.82
uncertainty:                         0.08
```

The claim confidence is a teaching proxy copied from plan success. A later learned system must calibrate predicate-specific claim probabilities separately.

## 4. First TRACE record

The TRACE Gate evaluates the evidence under `trace-flood-v1`:

```yaml
claim_type: predictive
claim: north_channel is traversable and rescue_boat_1 can arrive before the deadline
final_status: defer
failed_gates:
  - model_support
  - out_of_distribution
missing_items:
  - evidence inside the declared model support
  - current observation or verification for the out-of-support region
repair: send survey_drone_1 to verify north_channel before dispatching rescue_boat_1
consumer_decision: hold
```

The important output is not only `hold`. The record explains why, names missing evidence, and names a bounded repair.

## 5. Information-gathering action

The Planner separately proposes:

```yaml
action_type: verify_route
actor_id: survey_drone_1
route_id: north_channel
parameters:
  purpose: resolve_route_access
```

This reversible action passes its own TRACE checks. The Mission Controller dispatches the drone.

## 6. Realized observation

The Flood Environment returns what the drone observes:

```yaml
route_id: north_channel
route_status: blocked
source: survey_drone_1
```

Only now does the Mission Controller change its route knowledge from `unknown` to `blocked`.

## 7. Revision rather than overwrite

A new record version:

- cites the original record;
- attaches the realized observation;
- changes the north-route claim to `reject`;
- records `realized_contradiction`;
- preserves the earlier prediction and its evidence.

The system does not edit history to pretend the predictor was always correct.

## 8. Local plan repair

Only the branch that depended on `north_channel is traversable` is removed. The survey observation remains valid, and the supported `south-detour` branch remains available.

A new record can then clear:

```yaml
action_type: dispatch_rescue_boat
actor_id: rescue_boat_1
origin: rescue_base
destination: riverside_apartments
route_id: south_detour
parameters:
  people_count: 4
  deadline_s: 1200
```

The final `Commitment` cites the exact TRACE record version that authorized this action.

## What the example demonstrates

| Property | Evidence in the episode |
|---|---|
| Faithful | The hold can be reconstructed from support, OOD, policy, and failed gates |
| Actionable | The defer names a route-verification action |
| Revisable | The drone report creates a linked record version rather than an overwrite |
| Local | Only the north-dependent plan branch is repaired |
| Consequential | No durable dispatch is written without an authorizing TRACE record |

This is the bridge between the Chapter 8 specification and the Chapter 9 implementation: Chapter 8 defines the record contract; the implementation shows how a Mission Controller consumes it.
