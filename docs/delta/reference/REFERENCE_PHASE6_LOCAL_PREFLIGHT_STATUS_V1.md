# Reference Phase 6 local preflight status

## Scope

This record preserves development-only engineering observations made on
2026-08-12 in a local macOS/Python 3.13.1 environment. The executions used only
the already-spent illustrative seed `20260812`. They did not use or derive a
selection, validation, holdout, or confirmatory seed and did not exercise LEAP.
They are not canonical-environment evidence or statistical validation results.
As an execution-status record, this file is deliberately excluded from the
scientific-input inventory.

## Completed staged observations

The first bounded `phase6-core` preflight completed successfully before a later
source-formatting change:

| Observation | Value |
|---|---:|
| Non-performance checks | passed |
| Wall time | 415.200 seconds |
| Peak resident memory | 1,126,662,144 bytes |
| Transient output at measurement boundary | 876,366,812 bytes |
| Wall-time ceiling | 900 seconds |
| Peak-memory ceiling | 2,147,483,648 bytes |
| Transient-output ceiling | 1,073,741,824 bytes |
| Scientific-input aggregate at execution | `ffeeae429fe489bf215c5ed8ae332a07e079f0d839de042f52f5597c80d1b912` |
| Nominal replay-manifest digest | `a695e3a31347aee8d520fcce39e1a53a0c99e08bee25d68470b52ce0bcee9dc4` |
| Publication-manifest digest | `34d268e83b6a72a9d56320a923816d4faf29d8feeb00223b57672bc57f53ae3e` |
| Resource-receipt digest | `d32d4cc28e03fa57cfeaeb9c666f3eb737e28713b7a9049f67af91babe88931a` |

The paired `phase6-isolation` preflight then completed in 165.898 seconds. Its
hidden-lineage deletion comparison passed for decisions, outcomes,
reconciliations, public event projection, TRACE, evidence, and commitments. Its
then-current eight axis checks also returned pass, but the `phi` check compared
unchanged source content rather than the underlying coordination draws. A later
audit showed that recipient partition IDs, which change with `phi`, were part of
the latency/loss draw key. The old axis result therefore did not establish the
claimed common-random-number property and is superseded by protocol amendment
V5. The corrected probe records and compares hidden raw draws for shared
evidence-recipient pairs. The isolation receipt bound the same scientific input
aggregate and nominal replay-manifest digest shown above.

These two temporary output trees occupied approximately 1.16 GiB together.
They were removed after inspection to recover local disk space. The small
receipt files were not copied before removal; their essential values are
preserved above from the execution log. Because formatting and source-binding
corrections followed the run, neither receipt is eligible for final Phase 6
acceptance. No receipt has been reconstructed or represented as original.

## Adverse bounded-batch observation

A combined runtime test batch containing the decision-engine, mission-runtime,
and runtime-factory modules was stopped at the registered 15-minute command
ceiling. Tests that completed before the stop emitted passing results, but the
batch did not complete and therefore has no pass status. The process exited by
intentional termination (`143`), and observed resident memory approached
1.94 GiB near the stop boundary.

This is a test-orchestration and resource-margin finding, not a simulator result.
Subsequent local verification must execute these high-memory module-scoped
fixtures in separate fresh processes so fixture retention cannot accumulate
across modules. The capped batch must remain recorded and must not be replaced
by a claim that the combined batch passed.

## Relative-root characterization failure

The first post-Amendment-V5 G3 characterization command used the documented
relative repository root `.`. The runtime fixtures completed, but the final
scientific-input binding raised `ValueError` because the manifest builder
compared absolute source-closure paths to the unresolved relative root. The
command exited `1` and produced no eligible characterization receipt. This is a
CLI/path-normalization defect rather than a scenario-integrity result.

The corrective rule is to resolve and validate the caller-trusted repository
root once before source-closure calculation, relative-path conversion, or file
binding. A focused regression must exercise a relative repository root before
characterization is rerun. The partial runtime stores are temporary failed-run
outputs and are not retained as evidence after this record is committed.

## Next heavy-run gate

No further generation, runtime, replay, publication, or multi-seed command may
start until concurrent work on the host is clear and the operator has reviewed
the following projection:

1. each runtime test module runs in its own process with a predeclared resource
   projection and monitored upper bound; exceeding 15 minutes is recorded
   rather than used as an automatic termination rule, while the canonical
   15-minute acceptance ceiling remains unchanged;
2. the final core and isolation stages run only after source freeze;
3. core output is expected to approach 0.88 GiB, so at least 2 GiB of free disk
   should be reserved for one stage plus filesystem overhead;
4. canonical performance remains pending until the digest-pinned Python 3.11
   Linux environment produces its own verified receipt.
