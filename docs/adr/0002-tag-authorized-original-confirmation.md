# ADR 0002: Tag-authorized, once-only original confirmation

- Status: Accepted, not yet authorized
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

The original workflow is triggered only by the exact annotated tag
`wf-dfld-01-small-confirmatory-v8-original`.

The workflow:

1. checks out `github.sha` and verifies that the annotated tag resolves to it;
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
- A failed original remains the original and must be published without retuning.
- Deleting and recreating the authorization tag is insufficient to authorize a
  second original because workflow history is checked.
- GitHub administrators could still rewrite repository history or workflow-run
  records; the report therefore embeds the source commit, tag, run identity,
  protocol, manifest, environment, lock, and seeds for external audit.
