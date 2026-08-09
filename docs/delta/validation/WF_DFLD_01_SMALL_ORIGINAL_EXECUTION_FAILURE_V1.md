# WF-DFLD-01-SMALL original execution failure

- Authorization tag: `wf-dfld-01-small-confirmatory-v8-original-r2`
- Tagged commit: `991a628828c3fa1400372cb2a6e390cb76cbf47f`
- GitHub Actions run: `31286349320`
- Job: `93175800705`
- Run attempt: `1`
- Outcome: `failed-after-registered-study`

The authorization, immutable tag, first-attempt, and prior-success checks all
passed. The pinned Python 3.11.14 container then completed the 100 development
and 100 confirmatory-v8 seed runs and wrote the registered validation report.
It also generated the book walkthrough. Clean replay failed because the replay
command did not receive the explicit validation report that the reference
manifest bound. Consequently, the replay manifest omitted the validation-report
input and differed from the reference manifest.

The upload step was skipped after the shell failure, so the ephemeral registered
report and book directory were not retained. The workflow log preserves the
study-completion marker, book summary, traceback, exact commit, environment, and
run identity. This run is immutable adverse execution evidence and is never
rerun or relabeled as successful original evidence.

Recovery is restricted to one separately authorized
`recovery-replication`. It uses the unchanged confirmatory-v8 seed list,
generator, coefficients, reconciliation algorithm, resources, and numerical
gates; it is explicitly not a second original or an untouched-holdout execution.
The recovery implementation passes the registered report explicitly to replay
and uploads all partial evidence even if a later step fails.
