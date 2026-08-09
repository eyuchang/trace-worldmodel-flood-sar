# WF-DFLD-01-SMALL protocol v10: deterministic artifact reconstruction

## Status

Protocol v10 is preregistration for one artifact-reconstruction replication.
It does not create a new holdout and does not change generator-v8 scientific
mechanics. The confirmatory-v8 seeds were consumed by original run
`31286349320` and recomputed by recovery run `31289293944`; neither run retained
its generated report.

## Immutable history

- Run `31285710374` failed before seed access during tag preflight.
- Original run `31286349320` completed 100 development and 100 confirmatory
  evaluations, then failed replay and skipped upload.
- Recovery run `31289293944` completed all 200 evaluations, the book run,
  byte-identical replay, and publication generation. Upload found 66 files but
  failed on an owner-only container-root-owned hidden-lineage file. GitHub's
  artifact API reports zero retained artifacts.

The runs and their tags are never retried, deleted, or relabeled. Their
machine-readable failure records are frozen scientific inputs.

## Unchanged scientific inputs

The reconstruction preserves:

- the exact confirmatory-v8 seed list;
- generator-v8 truth and observation mechanisms;
- every fitted coefficient and selected `evidence-graph-q075` threshold;
- the resource roster and preauthorized-automatic-aid schedule;
- the TRACE policy, predictor qualification, gates, and statistical endpoints;
- the digest-pinned Python 3.11.14 environment and complete dependency lock; and
- the absence of a strict-load numerical target.

No simulator, predictor, evaluation, seed, or book parameter may be retuned.
The book seed remains descriptive.

## Authorization and execution

The sole authorization tag is
`wf-dfld-01-small-confirmatory-v8-artifact-reconstruction-replication-v1`.
The dedicated workflow:

1. verifies the remote annotated tag and exact source commit;
2. requires run attempt one and refuses any prior run for the same tag/commit;
3. verifies both immutable failed runs, including recovery-step success,
   upload-step failure, and zero retained artifacts;
4. verifies the complete scientific-input manifest and reference environment;
5. runs exactly 100 development and 100 already-consumed confirmatory-v8 seeds;
6. generates report v6, book v6, exact replay, and publication v6 in one
   container;
7. rejects symlinks in each exact output path, then transfers only those paths
   to the host runner user; and
8. uploads source-bound partial evidence only if the ownership/symlink check
   succeeds.

The atomic writer remains restrictive. Ownership changes only at the explicit
CI export boundary, so hidden truth is not made broadly readable on disk.

## Claims limit

Any retained results are deterministic artifact-reconstruction evidence. They
may support auditability, reproducibility, and transparent reporting of the
fixed experiment, but they are not an intact first confirmatory execution and
cannot be called untouched holdout evidence. All gates and adverse results are
published without tuning or replacement.

Branch push, authorization-tag push, and result-commit push are three separate
external actions requiring explicit approval. A failed reconstruction is final
under this protocol.
