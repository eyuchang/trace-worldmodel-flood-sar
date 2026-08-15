# Reference validation-v2 recovery amendment v2

Status: local draft awaiting separate branch-push and annotated-tag authorization.

## Recorded predecessor

Recovery-v1 run `31856190911` was triggered by the annotated tag
`wf-dfld-01-reference-validation-v2-recovery-v1` at commit
`42ac2e1d46185618573fc1b26c84449f15f5bd07`. The remote tag object is
`e89658fb128bd790ad38ef461d449aebd3b60694`, and it peels to that commit.

The checkout action first fetched the annotated tag, then replaced the local ref
of the same name with the peeled commit. The workflow's local `cat-file` guard
therefore rejected the ref as lightweight. This was a valid fail-closed result
for the implemented guard, but the guard tested checkout-local state rather
than the immutable remote tag identity.

Run `31856190911` stopped in `Verify recovery tag and run identity`. The failed
original lifecycle check, image build, seed derivation, shards, and aggregate
were never entered. The run produced zero artifacts, executed zero missions,
and observed no scientific outcome. The protected validation-v2 namespace and
list digest remain unchanged; no seed value is recorded in this amendment or
its machine-readable failure record.

## Corrective authorization

The only eligible next attempt uses the distinct annotated tag
`wf-dfld-01-reference-validation-v2-recovery-v2` and run attempt 1. It is not a
rerun of recovery-v1, and neither earlier tag may be moved or reused.

Before any protected derivation, the authorize job must:

1. verify the v2 remote ref through GitHub's Git-data API;
2. require the remote ref object type to be `tag`;
3. resolve the tag object and require its target type to be `commit` and its
   target SHA to equal `GITHUB_SHA`;
4. verify original run `31833291955` as the recorded pre-evaluation artifact
   permission failure;
5. verify recovery-v1 run `31856190911` as the recorded pre-derivation tag-ref
   normalization failure, including zero artifacts and skipped shards;
6. reject every prior recovery workflow run other than exactly
   `31856190911` and the current v2 run; and
7. verify the unchanged base freeze and current recovery-governance manifest in
   the pinned, offline execution environment.

The checkout-local tag ref is not evidence of whether the pushed tag is
annotated. It may still be used to check the detached `HEAD`, but tag type and
target are verified against the remote immutable Git objects.

## Scientific invariants

This amendment changes authorization evidence only. It does not change the
Reference generator, truth, observations, resources, policy, reconciliation,
fault schedule, acceptance gates, environment, mission count, seed namespace,
seed-list digest, or statistical methods. LEAP remains absent. Recovery-v2 is
eligible to be called the first mission-executing validation only if its guards
pass and at least one mission actually begins.

If recovery-v2 fails before missions, preserve it and require another explicit
versioned authorization. If it fails after any shard finishes, disclose only
seed-concealing receipts and continue later with missing shard indices; never
rerun completed missions or replace the protected namespace.
