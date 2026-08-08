# WF-DFLD-01-SMALL v9 pre-push remediation protocol

Status: implementation protocol frozen before any confirmatory-v8 seed is
derived or evaluated.

## Protocol history

The v5 and v6 evidence, the unexecuted v7 registration, and the unexecuted v8
acceptance/confirmatory-v7 seed list remain immutable. Confirmatory-v7 is
**superseded-before-execution** and MUST never be run. This remediation does not
alter the v8 truth, observation, resource, or reconciliation coefficients and
does not tune the book seed.

## Purpose

The remediation corrects four pre-push governance defects:

1. the feature-branch manual workflow could not launch as documented;
2. the scientific-input manifest did not bind the complete executable surface;
3. finite-only peak metrics were not labeled as finite;
4. replication accepted an incompletely verified original report.

It also restructures the Task 1/2 implementation into cohesive typed packages.
The structural refactor is required to preserve the current scientific outputs
byte-for-byte. Only version identifiers, corrected metric names, manifests,
summaries, reports, and figures may change after the metric amendment.

## Frozen scientific decisions

- Generator, truth, observation, resource, and reconciliation mechanics remain
  `delta-small-generator-v8`, `delta-ground-truth-v5`,
  `delta-observations-v5`, `delta-resources-v3`, and
  `delta-reconciliation-v3`.
- The active scenario becomes `trace-delta-scenario-v5`; the demand/capacity
  contract becomes `delta-demand-capacity-v5` and contains no strict-load target.
- Strict one-resource/one-incident concurrency remains primary. Finite strict,
  uncapped, historical normalized, and residual peaks are reported alongside
  their unserviceable-window counts. No strict numerical gate is introduced.
- The Toy predictor remains canonical. MLP and V-JEPA remain unqualified without
  an exact qualification artifact. No learned model is trained or retuned.
- The geography, automatic-aid schedule, hydrology, cohort, six-hour window,
  book seed, coefficients, q075 reconciliation algorithm, and Task 3 exclusions
  remain unchanged.

## Confirmation discipline

After development-only equivalence, tests, documentation, environment, and
scientific-input closure are frozen, exactly 100 confirmatory-v8 seeds are
derived from
`SHA-256("WF-DFLD-01-SMALL|confirmatory-v8|index")` with the established
unsigned-31-bit reduction. They MUST NOT be evaluated locally.

The original execution is authorized only by pushing the exact annotated tag
`wf-dfld-01-small-confirmatory-v8-original` after separate user approval. The
workflow checks out the tag commit, requires run attempt one, rejects a prior
successful original run independently of artifact retention, and records its
complete execution identity. Later runs require a committed original-report
registry and are labeled replications.

## Claims and exclusions

Supported claims concern deterministic generation, causal axis isolation,
truth/observation separation, TRACE accountability, predictor provenance,
reconciliation evaluation, and reproducibility of a synthetic teaching model.
No operational-readiness, field-generalization, historical hydrodynamic,
demographic-representativeness, or learned-predictor-effectiveness claim is
authorized. Task 3 remains excluded.
