# WF-DFLD-01-SMALL recovery execution failure

- Authorization tag: `wf-dfld-01-small-confirmatory-v8-recovery-replication-v1`
- Tagged commit: `6f83ea5b6fc54a0b28b65174e02ed40bec38b339`
- GitHub Actions run: `31289293944`
- Job: `93183637958`
- Run attempt: `1`
- Outcome: `failed-after-successful-recovery-computation`

The tag, commit, first-attempt, failed-original, environment, and prior-recovery
checks all passed. In the pinned Python 3.11.14 container, the registered
recovery completed exactly 100 development and 100 confirmatory-v8 seed runs,
generated the validation report and book bundle, completed byte-identical
replay, and generated the publication bundle. The book walkthrough recorded
8 allocations, 12 refusals, 8 visible-evidence repairs, a finite strict load of
1.333, a finite historical normalized index of 1.333, and a finite residual
strict-pressure peak of 1.500.

Artifact transfer then failed outside the scientific container. The atomic
writer had correctly created hidden-lineage files with owner-only permissions
under the container's root user. GitHub's host-side upload process ran as a
different user and could not open `call_lineage.json` while constructing the
archive. It had discovered 66 files, but the upload failed before an artifact
was created; GitHub's artifact API reports a retained artifact count of zero.

This is an evidence-retention defect, not a simulator, validation, replay, or
publication-computation failure. Nevertheless, no report or bundle survived,
so the numerical ensemble results cannot be recovered from this run. The run
must not be retried, deleted, or relabeled as successful. Its successful
computation step and failed upload remain immutable adverse execution evidence.

Any later generation of the lost deterministic files is a separately
authorized **artifact-reconstruction replication**. It cannot be described as
the original execution, the recovery execution, or untouched confirmatory
evidence. The only permitted correction is a workflow-local ownership transfer
of the exact generated output paths before host-side upload; scientific file
permission defaults remain unchanged.
