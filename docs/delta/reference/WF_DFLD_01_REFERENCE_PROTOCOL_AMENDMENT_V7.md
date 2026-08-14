# WF-DFLD-01-REFERENCE protocol amendment v7

## Document control

| Field | Value |
|---|---|
| Amendment ID | `reference-protocol-amendment-v7` |
| Status | Approved CI-governance correction |
| Approval date | 2026-08-14 |
| Approved by | Jay Roy, project owner |
| Supplements | Amendments v1 through v6 |
| Protected-seed authority | None |
| Validation-execution authority | None |
| Authorization-tag authority | None |
| LEAP authority | None |

Jay approved additional execution time for the complete branch quality suite
after the corrected branch reached coverage testing but GitHub canceled the job
at its inherited 15-minute limit. This amendment changes CI orchestration only.
It does not alter scenario mechanics, coefficients, model or policy behavior,
registered scientific performance ceilings, protected namespaces, or any
validation endpoint.

## D13 — Branch CI timeout and adverse-run record

The `quality` job in `.github/workflows/ci.yml` has a 45-minute upper timeout.
This matches the repository's artifact and confirmatory workflow scale and
provides enough orchestration time for the complete test-and-branch-coverage
surface. The timeout is an infrastructure ceiling, not a scientific runtime
target. The canonical Reference performance gate remains the separately
measured and source-bound 900-second Phase 6 limit.

The following branch-CI outcomes are retained as adverse execution evidence:

1. GitHub Actions run `31770344929` terminated at the Ruff formatting check.
   Ruff identified five unformatted files. The files were formatted using the
   pinned Ruff version, and no scientific test failure was reported by that
   run.
2. GitHub Actions run `31791847888` passed environment verification, lint,
   formatting, and strict typing. GitHub then canceled the
   `Test with registered branch coverage` step when the job reached the
   15-minute job limit. The run reported no failing test assertion.

Neither outcome is relabeled as a successful scientific execution. The first
is a formatting failure and the second is an infrastructure timeout. The
corrected workflow must execute the same test, coverage, scientific-input,
replay, and branch-diff checks without weakening or skipping a gate.

## Source binding and regression protection

The CI workflow, this amendment, and the focused timeout-regression test are
members of the complete Reference scientific-input inventory. Any future
workflow reduction below 45 minutes fails the regression test and invalidates
the committed source manifest.

Because this correction changes bound scientific inputs, all current-source
manifests, G3 handoff evidence, Phase 6 development receipts, canonical
execution receipt, and the seed-free validation freeze must be regenerated in
the pinned Python 3.11 Linux environment. Historical receipts remain unchanged.

This amendment does not authorize protected-seed derivation, validation
execution, an authorization tag, LEAP implementation, or a push.
