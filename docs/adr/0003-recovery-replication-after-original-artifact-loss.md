# ADR 0003: Recovery replication after original artifact loss

- Status: Accepted; implementation awaiting branch and tag authorization
- Date: 2026-08-08
- Scope: confirmatory-v8 evidence recovery

## Context

The first authorization attempt, GitHub Actions run `31285710374`, failed in
tag-verification preflight before a registered seed was accessed. The corrected
authorization tag then produced run `31286349320`. That run passed every
authorization and environment check and completed all 100 development and 100
confirmatory-v8 seed evaluations. It wrote the registered report and generated
the book walkthrough in ephemeral runner storage.

The subsequent exact-replay command omitted the explicit validation-report
input bound by the reference manifest. Replay therefore failed with
`ArtifactMismatchError`. Because upload followed the failing shell step without
an `always()` condition, the registered report and book bundle were not
retained. The workflow log retains the exact run identity, study-completion
marker, book summary, failure traceback, commit, tag, and environment. The
original execution occurred and cannot truthfully be rerun or replaced.

## Decision

Preserve run `31286349320` as immutable adverse original-execution evidence.
Authorize at most one separately tagged `recovery-replication` to recover the
deterministic registered results. It is not a second original, not an untouched
holdout execution, and not a basis for claiming that the retained report came
from the original run.

The recovery:

1. uses the exact confirmatory-v8 seed list, generator, coefficients,
   reconciliation algorithm, resources, gates, policy, and environment;
2. changes only replay plumbing, evidence retention, execution-role labeling,
   and complete scientific-input hashes;
3. verifies run `31286349320` through GitHub's API, including failed conclusion,
   source commit, tag, run attempt, study-step failure, and skipped upload;
4. is authorized only by the annotated tag
   `wf-dfld-01-small-confirmatory-v8-recovery-replication-v1`;
5. refuses any second recovery run for the same tag and commit;
6. passes the registered validation report explicitly to exact replay;
7. uploads whatever evidence exists even if a later step fails; and
8. embeds the failed-original run ID in the typed recovery report.

The recovery report is registered as **registered evidence**, not as an
original report. Later replications must match its committed path, SHA-256, and
typed identity byte-for-byte.

Branch push, recovery-tag push, and result-commit push remain separate external
actions requiring explicit approval. A successful recovery does not erase the
original failure record.

## Consequences

- The retained numerical report has weaker evidentiary status than a retained
  report from the original execution because the holdout outcomes were exposed
  in the failed-run log before recovery.
- Determinism and unchanged scientific inputs make the recovery useful for
  reconstructing results, artifacts, and audit chains, but they do not restore
  untouched-holdout status.
- Any gate failure or adverse comparison in the recovery must be reported
  without retuning, seed replacement, threshold changes, or another primary
  recovery.
- Paper and book text must distinguish the immutable original failure from the
  retained recovery-replication evidence.
