# WF-DFLD-01-SMALL original-authorization attempt 1

- Authorization tag: `wf-dfld-01-small-confirmatory-v8-original`
- Tagged commit: `d96705664841e07dd51a4607c327aaa0c170da39`
- GitHub Actions run: `31285710374`
- Run attempt: `1`
- Outcome: `failed-before-execution`
- Confirmatory seeds accessed: `false`

The exact annotated tag triggered the dedicated workflow once. GitHub's checkout
action initially fetched the annotated tag object, then replaced the local tag
reference with the peeled commit while checking out the event SHA. The preflight
assertion expected the local reference to remain an annotated-tag object and
failed. GitHub skipped the prior-run check, registered study, book generation,
replay, publication, and artifact-upload steps.

The tag, commit, and failed workflow run remain immutable audit evidence. The
recovery authorization uses
`wf-dfld-01-small-confirmatory-v8-original-r2`, verifies the annotated tag object
through GitHub's Git data API, and preserves the confirmatory-v8 seeds,
coefficients, reconciliation algorithm, resource roster, acceptance gates, and
simulator mechanics unchanged.
