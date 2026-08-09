# ADR 0002: Tag-authorized, once-only original confirmation

- Status: Accepted; recovery authorization not yet granted
- Date: 2026-08-08
- Scope: confirmatory-v8 original execution

## Context

GitHub does not expose a feature-branch workflow to manual dispatch until that
workflow exists on the default branch. A generic `workflow_dispatch` input also
allows commit substitution, repeat execution, and accidental use of the holdout.
Artifact retention is unsuitable as the once-only guard because artifacts expire.

The original confirmatory execution must be bound to the preregistered source,
environment, seed list, and scientific inputs, while leaving later replications
possible only after the original report is committed and registered.

## Decision

The original workflow is triggered only by the exact annotated recovery tag
`wf-dfld-01-small-confirmatory-v8-original-r2`.

The first authorization tag, `wf-dfld-01-small-confirmatory-v8-original`,
triggered GitHub Actions run `31285710374`. The checkout action peeled the
annotated tag and rewrote its local tag ref to the commit, causing the local
tag-object assertion to fail. The registered study, book, replay, and upload
steps were all skipped, so no confirmatory seed was accessed. The failed run
and tag remain immutable. The recovery changes only authorization verification:
it verifies the annotated tag object through GitHub's Git data API and requires
that object to target `github.sha`; it does not alter seeds, coefficients,
algorithms, gates, or simulator mechanics.

The workflow:

1. checks out `github.sha` and verifies through the remote Git data API that the
   annotated authorization tag resolves to it;
2. refuses any run attempt other than attempt one;
3. queries workflow-run history for a prior successful run with the same tag and
   source commit, independent of artifact retention;
4. uses concurrency with cancellation disabled;
5. verifies the complete scientific-input manifest and digest-pinned Python
   3.11.14 environment;
6. runs the registered development and confirmatory-v8 studies exactly once;
7. emits source-bound report, book, replay, publication, and execution evidence.

The branch, annotated authorization tag, and result commits are three separate
external actions, each requiring explicit user approval. After a successful
original, the trigger is removed or permanently disabled. Replication stays
disabled until a committed registry binds the canonical original report by path,
SHA-256, and typed identity.

## Consequences

- The holdout cannot be selected by a user-supplied commit input.
- Expiring artifacts do not weaken once-only detection.
- A failure after registered study execution begins remains original evidence
  and must be published without retuning. A preflight failure before any seed
  access may be superseded only by an explicit, documented recovery tag that
  preserves the scientific inputs and holdout.
- Deleting and recreating the authorization tag is insufficient to authorize a
  second original because workflow history is checked.
- GitHub administrators could still rewrite repository history or workflow-run
  records; the report therefore embeds the source commit, tag, run identity,
  protocol, manifest, environment, lock, and seeds for external audit.
