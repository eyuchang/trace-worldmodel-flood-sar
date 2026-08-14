# WF-DFLD-01-REFERENCE base validation preregistration draft

## Status

| Field | Value |
|---|---|
| Draft ID | `reference-base-validation-preregistration-draft-v1` |
| Scientific role | Base non-LEAP integration validation |
| Current authority | Design only; no untouched-seed access |
| Policy-effectiveness claim | None |
| LEAP behavior | None |
| Validation execution | Disabled pending approval |
| Confirmatory execution | Not defined |

The typed machine-readable draft is
`data/scenario/delta/reference_protocol/reference_base_validation_preregistration_draft_v1.json`.
It binds the current development scientific-input aggregate and execution
evidence, declares the approved exact integration gates, and contains no
selection, validation, holdout, or confirmatory seed values.

## Intended study

The first Reference validation follows approved Decision D7. It asks whether
the full non-LEAP simulator and TRACE recovery path satisfy their declared
contracts, not whether a policy is superior.

For each proposed validation mission, the canonical `kappa=1.0` world supplies
paired nominal and registered-fault execution. Nominal and faulted profiles
share byte-identical exogenous inputs and are reported separately. The required
`kappa=0.5` scarcity sensitivity changes only the deterministic resource
inventory and reports strict load, unserviceable windows, uncapped service-unit
load, and the historical normalized sensitivity. It has no numerical load gate.

The approved exact gates cover:

- causal-axis isolation under keyed common random numbers;
- exact replay and deterministic publication;
- restart, retry, and recovery equivalence;
- event, evidence, TRACE, authorization, commitment, outcome, revision, and
  compensation-chain integrity;
- hidden-truth exclusion;
- resource, crew, action, commitment, outcome, and capacity conservation;
- complete registered-fault reachability;
- source, license, safe-path, offline, and Small-preservation checks; and
- resource ceilings in the exact registered environment.

Coverage, allocation/refusal/HOLD, evidence cost, consistency, recovery,
reconciliation, route failure, utilization, censoring, and load are descriptive
mission-level estimands with seed-cluster intervals. They are not efficacy
gates. No call, incident, commitment, or repair is treated as an independent
sample.

## Namespace audit and required supersession

The existing `selection-v1` and `validation-v1` namespaces cannot be described
as untouched. A development unit test in
`tests/delta/reference/test_reference_protocol.py` calls
`derive_seed_prefix("selection", 100)` and
`derive_seed_prefix("validation", 100)`. No scenario was run with either
prefix and their values were not committed as evidence, but their derivation
spent the concealment boundary. The scientifically conservative remedy is to:

1. retain both v1 namespaces as `superseded-before-scientific-use`;
2. prohibit their use by any registered study;
3. introduce `selection-v2` and `validation-v2` only after a protocol amendment;
4. keep v2 values unmaterialized in local tests, code, documentation, and logs;
   and
5. derive the approved validation list only inside the authorized remote
   original workflow.

The base integration study does not select a policy or operating point, so
`selection-v2` remains reserved and unused. A future policy-effectiveness or
LEAP study needs a separate selection and powered evaluation protocol.

## Proposed validation count

The proposed base validation uses 100 independent mission seeds. This is a
precision and defect-detection choice, not a powered policy comparison.

The 100 spent development missions give:

| Quantity | Development estimate | Projected 95% half-width at 100 validation missions |
|---|---:|---:|
| Evaluation public-report total, seed-level SD | 123.156 reports | 24.139 reports |
| Per-seed breach-phase hourly mean, seed-level SD | 6.510 reports/hour | 1.276 reports/hour |

The projections use `1.96 × s / sqrt(100)` and are planning approximations; the
registered report uses a deterministic 10,000-resample mission-cluster
bootstrap. If an exact gate has zero failures in 100 missions, the exact
one-sided 95% binomial upper bound on a mission failure probability is about
2.95%. This does not establish field or operational reliability.

A policy-effectiveness confirmatory count cannot be determined from this
calculation. It requires a minimum practically relevant paired effect, endpoint
hierarchy, margins, type-I error allocation, target power, and variance estimate
approved in a separate protocol.

## Proposed remote original boundary

The original base validation should be a remote once-only workflow that:

1. runs only from an immutable annotated authorization tag;
2. verifies that the checked-out SHA is the preregistration commit;
3. requires workflow run attempt one and no prior successful run for the same
   workflow, tag, and source commit;
4. uses no cancel-in-progress behavior;
5. verifies the exact OCI index/platform manifest, Python environment contract,
   dependency lock, protocol, scientific-input aggregate, and seed-list digest;
6. derives the validation-v2 list only after those checks, without printing the
   list to ordinary logs;
7. runs scientific generation, runtime, replay, validation, and publication
   with networking disabled;
8. emits source commit, tag, workflow/run identity, environment, protocol,
   manifest, and seed-list digests in every report; and
9. publishes failures and adverse results without tuning, seed replacement, or
   relabeling.

Replication remains disabled until the original report and its exact file
digest are committed to an original-report registry. A later run must verify
that report byte-for-byte and identify itself as a replication.

## Canonical-receipt correction required before freeze

The exact Python 3.11.14 Linux/amd64 Phase 6 execution passed the registered
wall-time, memory, output, replay, and publication requirements. The frozen
runner nevertheless hard-codes every direct resource receipt as
`local-preflight` with canonical status pending. A separate execution receipt
truthfully verifies the actual environment, but the validation workflow should
not depend on that workaround.

Before this draft becomes a frozen protocol, the runner should accept a typed
verified-environment identity, mark a receipt canonical only after exact
contract/lock/platform matching, and fail closed otherwise. This source change
must enter the scientific-input manifest, and canonical Phase 6 must be rerun.
No simulator coefficient, seed, load target, or resource ceiling changes.

## Approval gate

The next action requires Jay's approval of one versioned amendment covering all
four items below:

1. permanently supersede the development-exposed selection-v1 and validation-v1
   namespaces and create protected v2 namespaces;
2. implement exact canonical environment-role derivation and rerun canonical
   Phase 6 after the manifest changes;
3. freeze a 100-mission, remote original base validation whose gates are
   deterministic integration requirements and whose operational results are
   descriptive; and
4. freeze the immutable-tag, run-attempt-one, prior-success-registry,
   no-cancellation remote workflow design.

Approval authorizes implementation and freeze preparation. It does not by
itself authorize materializing validation-v2 seeds or launching the remote
original. That execution remains a separate explicit gate. Dr. Chang's review
is required before a later manuscript-level policy-effectiveness or LEAP
protocol freezes endpoint hierarchy, superiority/noninferiority margins,
multiplicity, and power.
