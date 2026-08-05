# Observation and capacity protocol

## Latent truth and lossy evidence

Latent incidents are sampled from physical hazard, exposure, and vulnerability.
They are not sampled from the desired call schedule. The observation channel is
applied afterward and supports non-reporting, first reports, duplicates,
multi-channel reports, revisions, callback failures, dropped calls, third-party
welfare checks, false benign levee reports, and location noise.

At `iota=0.9`, expected reports are calibrated analytically to hourly arrivals
`[3, 5, 7, 12, 8, 5]`. The calculation subtracts uniform expected false reports,
conditions on the physical-hazard-derived latent rate, solves reporting and
extra-report probabilities, and accounts for expected delay spill into the next
hour. A unit test reconstructs the six expectations to numerical tolerance.

Artifacts are separated into:

- controller-visible raw calls;
- controller-derived belief relationships/revisions;
- hidden truth lineage used only after runtime for scoring.

The runtime has no lineage argument. Deleting lineage yields byte-identical
public decisions, evidence, TRACE records, commitments, and outcomes.

## Offline evaluation metrics

The registered report provides means or Wilson 95% intervals for total/hourly
calls, non-reporting, relationship fractions, callback failure, dropped calls,
location error, reconciliation accuracy, false-report outcomes, and operation
counts. These intervals describe synthetic seed variation, not population or
field uncertainty.

For `confirmatory-v4-primary`:

- duplicate fraction: 0.0748 (95% CI 0.0671–0.0833);
- multi-channel fraction: 0.0421 (0.0363–0.0487);
- revision fraction: 0.1416 (0.1312–0.1527);
- false-report fraction: 0.1278 (0.1178–0.1384);
- callback-failure fraction: 0.1092 (0.0999–0.1192);
- non-reporting fraction: 0.0469 (0.0394–0.0557);
- mean location error: 179.35 m;
- scored reconciliation accuracy: 0.8553 (0.8339–0.8744).

## Incident requirements and resource capabilities

The versioned tables live in the hashed population/resource parameter artifact.
Each incident declares one required capability, initial-response duration, and
service units. Each resource declares capabilities, base, route, activation,
staging, travel, availability, service duration, and service units.

The default inventory is one 25-foot rescue boat and one Type I engine. The boat
supports water rescue and missing-person search. The engine supports medical,
road rescue, welfare checks, and levee inspection. The engine is ineligible for
water rescue.

## Demand/capacity definition

At each 15-minute grid time:

1. select ground-truth incidents whose declared service interval is active and
   which have not completed an authorized allocation;
2. group required service units by capability and required crossing route;
3. exclude unavailable, not-yet-mobilized, committed, or unreachable resources;
4. assign each resource to at most one compatible capability/route bucket;
5. maximize actually coverable service units without exceeding bucket demand;
6. divide total uncovered demand by that maximum.

Empty demand has ratio zero. Positive demand with zero compatible capacity is
explicitly unserviceable and has no fabricated finite denominator.

## Registered gate result

The pre-audit 1.5 ratio resulted from a denominator that could count surplus or
partially incompatible capacity. The corrected `confirmatory-v4-primary` median
is 3.0 (bootstrap 95% CI 3.0–3.0), so the registered `[1.4, 1.6]` target is
rejected. This adverse finding is a required deliverable, not a simulator error
to hide through post-hoc retuning.
