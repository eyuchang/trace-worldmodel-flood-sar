# WF-DFLD-01-SMALL v9 pre-push remediation protocol

Status: scientific mechanics frozen; original execution completed but its
ephemeral report was lost after a replay-plumbing failure. One recovery
replication is preregistered and not yet authorized by tag.

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
scientific-input closure were frozen, exactly 100 confirmatory-v8 seeds were
derived from
`SHA-256("WF-DFLD-01-SMALL|confirmatory-v8|index")` with the established
unsigned-31-bit reduction. They were evaluated once by original GitHub Actions
run `31286349320` and MUST NOT be evaluated locally.

The original execution was authorized by the annotated tag
`wf-dfld-01-small-confirmatory-v8-original-r2`. Run `31286349320` checked out
the registered commit, verified the tag and pinned environment, and completed
all 100 development and 100 confirmatory seed evaluations. It then failed in
exact replay because replay did not receive the validation-report input bound by
the just-generated reference. Artifact upload was skipped, so the ephemeral
report was not retained. This execution is preserved as adverse original
evidence and is not rerun or replaced.

The earlier tag without the `-r2` suffix triggered run `31285710374`, which
failed during authorization preflight because the checkout action replaced the
local annotated-tag ref with its peeled commit. The study, book, replay, and
upload steps were skipped; no confirmatory seed was accessed. That tag and run
remain immutable. The recovery workflow verifies the remote annotated tag
object through GitHub's Git data API and otherwise preserves the scientific
protocol unchanged.

A single recovery replication may be authorized separately by the tag
`wf-dfld-01-small-confirmatory-v8-recovery-replication-v1`. It binds the failed
original through GitHub's API, uses unchanged seeds and scientific mechanics,
passes the registered report explicitly to replay, and uploads partial evidence
after any later failure. It is not a second original and cannot restore
untouched-holdout status. Later replications remain disabled until the retained
recovery report is committed in a byte-bound registered-evidence registry. See
ADR 0003.

Post-execution addendum: recovery run `31289293944` completed the registered
study, book run, byte-identical replay, and publication generation. Its upload
then failed because a protected container-root-owned file was unreadable to the
host uploader; GitHub retained zero artifacts. The recovery is not rerun.
Protocol v10 and ADR 0004 govern any separately authorized deterministic
artifact reconstruction.

## Claims and exclusions

Supported claims concern deterministic generation, causal axis isolation,
truth/observation separation, TRACE accountability, predictor provenance,
reconciliation evaluation, and reproducibility of a synthetic teaching model.
No operational-readiness, field-generalization, historical hydrodynamic,
demographic-representativeness, or learned-predictor-effectiveness claim is
authorized. Task 3 remains excluded.
