# ADR 0004: Artifact reconstruction after recovery upload failure

- Status: Accepted; implementation requires new branch and tag authorization
- Date: 2026-08-08
- Scope: confirmatory-v8 deterministic evidence reconstruction

## Context

The immutable original execution, run `31286349320`, completed the registered
study but lost its report after a replay-input plumbing defect. The separately
authorized recovery, run `31289293944`, corrected replay and successfully
completed the registered 200-seed computation, book run, exact replay, and
publication generation. Its final upload failed because container-root-owned
files with owner-only permissions were unreadable to GitHub's host runner.
GitHub retained no artifact.

The second failure exposed no ensemble values in the log, changed no scientific
mechanic, and created no retained report. It nonetheless consumed the sole
recovery authorization and must never be rerun.

## Decision

Permit at most one separately tagged `artifact-reconstruction-replication`.
It is a deterministic reconstruction of lost files, not a replacement original,
not a replacement recovery, and not untouched holdout evidence.

The reconstruction must:

1. bind both immutable failed runs, including exact commit, tag, attempt, step
   conclusions, and zero retained artifacts for the recovery;
2. use the unchanged confirmatory-v8 seeds, generator, coefficients,
   reconciliation algorithm, resource roster, policy, gates, and reference
   environment;
3. use a new versioned acceptance/manifest/report surface so no frozen protocol
   file is overwritten;
4. change only evidence-governance code, execution-role labeling, failure
   records, and host-side export plumbing;
5. refuse any prior run for the reconstruction tag and commit;
6. transfer ownership only for the four exact output paths after container
   execution, reject output symlinks, and leave scientific permission defaults
   unchanged;
7. upload partial evidence even if a later command fails; and
8. disclose the original and recovery failures in the retained report and in
   all paper/book provenance.

The branch push, reconstruction authorization-tag push, and result-commit push
remain three separately approved external actions.

## Consequences

- A retained reconstruction can support reproducibility, artifact inspection,
  and transparent reporting of the fixed study, but it cannot restore the
  evidentiary status of an intact first confirmatory execution.
- No result may be tuned, suppressed, or replaced. A failed reconstruction is
  published as another adverse result and no further registered reconstruction
  is authorized by this decision.
- Restrictive atomic-write permissions remain the correct default for hidden
  truth. The interoperability fix belongs only at the explicit CI export
  boundary.
