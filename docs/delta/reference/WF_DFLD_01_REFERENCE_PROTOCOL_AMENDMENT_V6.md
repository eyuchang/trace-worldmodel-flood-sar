# WF-DFLD-01-REFERENCE protocol amendment v6

## Document control

| Field | Value |
|---|---|
| Amendment ID | `reference-protocol-amendment-v6` |
| Status | Approved validation-boundary implementation basis |
| Approval date | 2026-08-13 |
| Approved by | Jay Roy, project owner |
| Supplements | Amendments v1 through v5 |
| Approval-ready draft SHA-256 | `fc80c92d95347affcecc6460c3001828641d190fa2b4adcc3373a856c585b6e6` |
| Approval-ready draft commit | `599f653b1eb4ba170a87394bd812ed16b2251eea` |
| Validation-seed materialization authority | None |
| Validation-execution authority | None |
| Confirmatory authority | None |
| LEAP authority | None |

Jay approved the four validation-boundary recommendations recorded in
`REFERENCE_BASE_VALIDATION_PREREGISTRATION_DRAFT_V1.md`. This amendment
authorizes their implementation and freeze preparation. It does not authorize
deriving, materializing, logging, or executing any protected v2 seed.

## D9 — Supersede exposed v1 evaluation namespaces

Development tests previously called `derive_seed_prefix("selection", 100)` and
`derive_seed_prefix("validation", 100)`. No scenario was executed with those
values and no result used them, but derivation spent their concealment boundary.

The following lifecycle is binding:

- `selection-v1` and `validation-v1` are
  `superseded-before-scientific-use` and shall never be used by a registered
  study;
- `selection-v2` and `validation-v2` replace them;
- protected v2 derivation is unavailable to ordinary imports, unit tests,
  development CLIs, documentation examples, and local workflows;
- base Reference selects no policy or operating point, so `selection-v2`
  remains reserved and unused; and
- the validation-v2 list may be derived exactly once only inside a separately
  authorized remote original workflow after the frozen commit, tag,
  environment, scientific manifest, protocol, and execution role verify.

The development-v1 namespace and its 100 spent missions remain unchanged.

## D10 — Exact canonical resource-receipt identity

A resource receipt may use `measurement_role=canonical` only when an in-process
verification matches every field required by the registered environment
contract:

- environment-contract SHA-256;
- dependency-lock name and SHA-256;
- exact Python version;
- platform system and machine;
- every locked distribution version; and
- all required imports.

The verifier returns a typed immutable identity to the Phase 6 runner. The
runner derives the role from that identity and shall not accept a caller-supplied
`canonical` string or boolean. Any missing or mismatched identity produces
`local-preflight` and `pending-canonical-environment`; a forged or substituted
identity fails closed under model validation. The receipt records the contract
and lock hashes used for classification.

This corrects execution provenance only. It does not change scenario mechanics,
coefficients, seed, faults, resource ceilings, load definitions, or policy.
Because the verifier and receipt schema are scientific inputs, the complete
scientific manifest, G3 handoff, and Phase 6 evidence must be regenerated, and
canonical Phase 6 must pass again in the pinned environment.

## D11 — Base validation scope and sample size

The original base-Reference validation uses 100 independent validation-v2
mission seeds. The scientific role is non-LEAP integration validation, not
policy-effectiveness testing.

The approved exact gates are:

- all eight causal-axis invariants;
- chain, authorization, correction, commitment, outcome, recovery, and
  compensation integrity;
- exact generation, restart continuation, replay, and publication;
- hidden-truth exclusion;
- resource, crew, action, commitment, outcome, and capacity conservation;
- registered fault-family reachability;
- source, license, safe-path, offline, and Small-preservation checks; and
- canonical runtime, memory, and transient-output ceilings.

Canonical `kappa=1.0` nominal and faulted profiles share byte-identical
exogenous worlds and are reported separately. The registered paired
`reference-kappa-0p5-scarcity-v1` sensitivity changes inventory only and has no
numerical load gate.

Operational metrics are descriptive mission-seed estimands with deterministic
mission-cluster intervals. No policy-superiority, field-reliability,
hydrodynamic-validity, or operational-readiness claim is authorized. The
100-mission count is justified by precision and integration-defect detection
using only spent development summaries; it is not a powered efficacy design.

## D12 — Once-only remote original workflow

The remote original workflow shall:

1. trigger only from one exact annotated authorization tag on the frozen
   preregistration commit;
2. verify the checked-out SHA and never accept a user-supplied source commit;
3. require workflow run attempt one;
4. reject any prior successful run for the same workflow, tag, and source
   commit using workflow-run history rather than artifact retention;
5. use concurrency protection with cancellation disabled;
6. verify the complete scientific-input manifest, protocol, environment
   contract, lock, OCI index and platform manifest before seed derivation;
7. derive the validation-v2 list without printing seed values to ordinary logs;
8. run exactly 100 missions with scientific runtime, replay, validation, and
   publication offline;
9. bind source commit, tag, workflow/run identity, protocol, manifest,
   environment, lock, and seed-list digest in every report; and
10. publish every gate, failure, and adverse result without retuning or seed
    replacement.

The original result cannot be overwritten. Replication is disabled until the
original report and a byte-exact digest registry are committed. Every later run
must verify the registered original and label itself `replication`.

## Separate execution gate

This amendment authorizes code, tests, workflow preparation, scientific-input
binding, and canonical development reruns. After that freeze package is locally
complete, Jay must separately authorize the external branch push and later the
authorization tag that opens validation-v2. No local command may derive or
inspect protected v2 seed values.

A later policy-effectiveness or LEAP study remains separate and requires
approved endpoints, margins, multiplicity, power, namespaces, and workflows.
