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

## Process-control and regenerated G3 status

The local command wrapper may yield a live session identifier before the child
process exits. Several focused commands were initially treated as complete at
that yield boundary. An operating-system process audit detected the live
children before their results were used. Three redundant processes were
terminated, their incomplete outputs were removed, and none of their partial
results is counted. Subsequent expensive commands are polled through their
unified session until an explicit exit code is captured.

After the relative-root correction, the five-fixture non-LEAP G3
characterization completed with exit code `0` in 417.077 seconds. Its index
digest is
`71b74bab0ca029ee89aaa6aa26df907a31dc74f7a332cf65c6642c8b653bb606`;
its integrity report passed every registered runtime check and binds scientific
input aggregate
`0b61b09c6fc390de95973c1fc1d815775d205539069e36c3d0f1937c50c70b53`.
All four exact registered mission-runtime gate nodes later completed together
with exit code `0`.

A fresh exact-replay gate retry was deliberately stopped with exit code `143`
after another project began a declared disk-using run and projected cumulative
growth would have crossed the 4-GiB free-disk floor. One test had emitted a pass
before termination, but the interrupted command has no aggregate pass status.
The interrupted attempt was never counted as a gate result.

The subsequent source-stable retry completed all three registered provenance
gates with exit code `0`: public-artifact hidden-identifier exclusion, artifact
tamper detection, and byte-identical exact replay. Its temporary pytest root
peaked at 1.3 GiB, substantially above the 437-MiB stale-tree observation used
for the retry projection, and free disk briefly reached 3.7 GiB rather than the
declared 4-GiB floor. The run had already completed successfully when this peak
was measured. This resource-projection miss does not change the gate result,
but future replay notices must use the observed 1.3-GiB peak plus filesystem
margin rather than the smaller stale-tree estimate.

The source-stable G3 regeneration then completed. The committed scientific
input aggregate is
`0b61b09c6fc390de95973c1fc1d815775d205539069e36c3d0f1937c50c70b53`,
the G3 acceptance-receipt digest is
`fc09ae6a4fb1413ba5af3a1ac2e5eba40049bd2511fc100f4135964bf2f6bdc6`,
and the non-LEAP handoff-manifest digest is
`eece179ed2fb43923eb1b176c6f55aed20aa8748f6cd872489ae3ffa601d1860`.
The registered handoff and integrity regressions, Ruff, and strict mypy checks
passed before commit `619779d`.

## Phase 6 source-stable executions

The source-stable Phase 6 fault stage completed with exit code `0` in 266.679
seconds. It exercised every registered fault family, restart equivalence,
public/hidden separation, and all event, evidence, TRACE, commitment,
authorization, correction, and outcome joins. Its receipt digest is
`a1b3c460684b061ba010abff392b606d3656a408665a98d4660dcde100bb5b74`;
the nested integrity-report digest is
`ffe458e524ae2ac0d91e89ed7336db4b172479080e6097bcdfd4394397f95766`.

The next source-stable `phase6-core` attempt used the documented relative
repository root `.` and stopped before replay or publication after the nominal
runtime had been written. Artifact-manifest source-tree hashing still compared
absolute source paths with the unresolved relative root and raised
`ValueError`. The command exited `1` and produced no core receipt. This exposed
a second relative-root normalization boundary, distinct from the earlier
scientific-input-manifest boundary. The partial nominal store is not evidence;
it may be deleted after the defect and regression are committed. The corrective
requirement is that direct source-tree hashing resolve and validate the trusted
repository root before source enumeration and relative-path conversion, with
absolute/relative digest equivalence tested directly.

That correction is committed at `2f4c6b3`. The direct source-tree hash now
resolves the trusted root once, and focused absolute-versus-relative digest
equivalence, Ruff, formatting, and strict mypy checks passed. The failed partial
core tree was removed only after the process had exited and no open file handle
remained.

The five characterization fixtures were then regenerated in 467.084 seconds
using only spent development seed `20260812`. Their scientific behavior bytes
were unchanged; only the source-bound characterization index and nested
integrity report changed. The new characterization-index digest is
`2c03a0f6229b8aed4c16734bffd2017ca8bb6ffce5732ac8b156c42cc644a7a2`,
the regenerated integrity-report digest is
`7a2a22d684dfd54f55de9d0ad486016a9c1c8df0a47d714cfbfcf16129e5c568`,
and the current uncommitted scientific-input aggregate is
`9f12ed0993ac11fd3636e0a195fb21ae442829930f94f531135e7e2c0c4194b5`.

On the corrected source, 57 registered low-resource G3 checks, all four exact
mission-runtime gates, the causal-pipeline gate, the runtime-factory
hidden-lineage-independence gate, the fault/restart integrity gate, and the
public-artifact hidden-identifier gate passed in fresh bounded processes. After
free disk reached 6,078,800 KiB, the exact tamper-detection and byte-identical
replay gates ran sequentially in isolated roots. Both passed; each root occupied
859 MiB at its measurement boundary and left about 4.94 GiB free. Each root was
removed only after its child process exited and no open handle remained.

The complete registered G3 gate set therefore supports regenerated acceptance
receipt
`c31931d42e1eea7aebea46d5891d5e66bf2d5af846015aaf8485e82515df8d97`
and non-LEAP handoff manifest
`26e4231068d65de55cd9acf2adccf9880982f0d421c29f0e09e3aee6f27fdbc1`.
Nine handoff reconstruction and binding tests passed after regeneration. The
handoff explicitly reports `g3_ready=true`, `leap_implementation_present=false`,
and `effectiveness_evidence_present=false`.

## Next heavy-run gate

No further generation, runtime, replay, publication, or multi-seed command may
start until concurrent work on the host is clear and the operator has reviewed
the following projection:

1. each runtime test module runs in its own process with a predeclared resource
   projection and monitored upper bound; exceeding 15 minutes is recorded
   rather than used as an automatic termination rule, while the canonical
   15-minute acceptance ceiling remains unchanged;
2. the final core and isolation stages run only after source freeze;
3. core output is expected to approach 0.88 GiB and is bounded at 1.10 GiB, so
   it runs only when that upper bound preserves the 4-GiB free-disk floor;
4. canonical performance remains pending until the digest-pinned Python 3.11
   Linux environment produces its own verified receipt.
