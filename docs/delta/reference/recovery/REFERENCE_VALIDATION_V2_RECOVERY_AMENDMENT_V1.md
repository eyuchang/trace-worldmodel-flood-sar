# Reference validation-v2 recovery amendment v1

Status: locally frozen; separate recovery-tag authorization required  
Recorded: 2026-08-14  
Scientific scenario: `WF-DFLD-01-REFERENCE`

## Trigger

The tag-authorized original workflow run `31833291955` passed its identity,
prior-run, environment, image, and protected-list derivation steps. Its next
step could not read the protected plan from the runner temporary directory.
The root-running container had atomically created a root-owned mode-`0600`
file, while the artifact action ran as the unprivileged runner user. GitHub
reported `EACCES`, retained no artifact, skipped all validation shards, and
skipped aggregation.

This is an authorization-stage infrastructure failure. No Reference mission
ran, no outcome was calculated, and no validation result was observed. The
original run, tag object, source commit, and failure remain immutable evidence.

## Scientific continuity

The recovery changes execution governance only:

- The exact 240-member base scientific manifest, base freeze, simulator,
  coefficients, registered gates, estimands, environment, validation-v2
  namespace, and derivation algorithm remain unchanged.
- The recovery must derive the same protected list whose digest was logged by
  the failed original authorization. A different namespace, seed list, fitted
  value, numerical gate, or scenario mechanic is prohibited.
- The failed original run is not relabeled as a scientific evaluation. The
  first recovery run that actually executes missions is reported as
  `original-base-reference-validation-recovery` and links the failed run.
- No local command, branch CI command, or preflight test may derive, display,
  or materialize the protected validation-v2 seeds.

## Recovery authorization

Recovery requires a distinct annotated tag and workflow. The workflow accepts
only run attempt one, the exact tag target, the immutable failed-run identity,
zero original artifacts, the successful original derivation step, skipped
original mission and aggregate jobs, and no prior recovery attempt. Branch
push, recovery-tag creation, and result publication remain separate approval
actions.

Each remote shard privately derives the unchanged list inside its offline
container after all guards pass. There is no pre-mission raw-plan artifact.
The shard emits five seed-concealing mission receipts. The aggregate job
privately rederives the same list, verifies all shard bindings, and writes the
recovery-labeled report. The exact plan may be disclosed only in the same
successful final artifact as the completed immutable report.

All output-producing containers run as the GitHub runner user with `umask 077`.
Before upload, every expected artifact must be a readable, non-symlinked,
runner-owned regular file within its declared root and below its registered
size ceiling.

## Interruption rule

If recovery infrastructure fails after one or more shard receipts exist, those
receipts become immutable observed evidence. The interrupted workflow must
publish a seed-free continuation plan identifying completed and missing shard
indices. A later continuation requires a new, versioned authorization bound to
that plan and may execute only the missing mission indices. Completed missions
may never be rerun, and the protected namespace may never be replaced. A
complete recovery report is produced only after exactly one verified receipt
exists for every mission index.

## Claims

Recovery results retain the frozen base protocol's scope: non-LEAP Reference
integration validation with descriptive mission-seed intervals. Recovery does
not create evidence of policy superiority, field validity, or learned-predictor
effectiveness.
