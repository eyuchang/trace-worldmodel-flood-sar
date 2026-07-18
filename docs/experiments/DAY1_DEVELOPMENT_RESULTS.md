# Day 1 active-refresh development results

## Scope

This record covers the completed development-only implementation and checks for
WP-E, WP1, WP3, WP4, WP5, G2, and the structural smoke matrix. It is not an
inferential result, does not establish policy superiority, and does not include
validation or test-seed execution.

The original G2 workload completed before route conditions could become stale
at action execution. A versioned later-horizon workload introduced a common,
policy-invariant gauge observation followed by a later incident, without
changing the physical water dynamics. A subsequent measurement correction
retained every TRACE proposal record while computing primary coverage from
stable commitment units rather than repeated record revisions.

## Verification

- Full test suite: 161 passed, 1 skipped. The skip is the declared optional
  Torch/V-JEPA seam.
- D0.5 verification script: all four stages passed.
- Ruff and whitespace checks: passed.
- Preserved protocol-evidence cells validated independently: 98/98.
- Additional implementation-QA cells validated independently: 3/3.
- Validation and test partitions accessed: no.

## G2 regression

G2 passed at the single frozen forcing-noise setting of 0.35.

| Quantity | Result |
| --- | ---: |
| Complete, valid cells | 20/20 |
| Raw TRACE proposal records | 5,146 |
| Unique proposed commitment units | 44 |
| Executed commitment units | 19 |
| Held commitment units | 25 |
| Escalated commitment units | 0 |
| Stale executions | 6 |
| Stale execution rate | 6/19 = 0.315789 |
| Commitment-unit coverage | 19/44 = 0.431818 |
| Development gate interval | 0.10--0.40 |

The stale-rate numerator and denominator are unchanged by the commitment-unit
correction. The 44 commitment units are not treated as independent samples;
future inference remains clustered by mission seed.

## Structural smoke matrix

All nine cells in the three-policy by three-seed smoke matrix passed artifact,
provenance, and common-random-number checks.

| Policy | Executed / proposed units for seeds 41, 42, 43 | Total verification cost per seed |
| --- | --- | --- |
| `fixed-k:45` | 1/2, 0/1, 1/2 | 0.4, 0.4, 0.4 |
| `clock:0.55` | 1/2, 0/1, 1/2 | 0.2, 0.2, 0.2 |
| `adaptive:1` | 0/2, 0/1, 0/2 | 0.2, 0.2, 0.2 |

The adaptive cells held every commitment in these three smoke seeds and made
no discretionary acquisition. This is recorded as an observed structural
outcome, not evidence of comparative performance. Coverage and the future
false-HOLD analysis are required safeguards against rewarding abstention.

After removing only amendment/workload identifiers and hashes, all 29 final
development-cell exogenous projections were byte-identical to their preceding
amendment counterparts. The physical trajectories and scheduled inputs were
therefore unchanged.

## Integrity and source identity

The full per-run evidence remains outside Git. Its compact manifest and result
hashes are recorded in `DAY1_DEVELOPMENT_RESULTS.json`.

The executed evidence source-tree SHA-256 is
`bb2ca86c3d14d82bb1dc788b30ca5e76fd21256c00ef5b1f305e65ad4786b340`.
The review-branch source-tree SHA-256 is
`85fd563f00d28915942e524dc32590fdbdc6d513434e99677479df0e03f475da`.
Their source inventories have identical paths and differ only in the CLI help
text of `scripts/run_day1_amendment_1.py`; experiment behavior and parameters
are unchanged. The review-branch hash is not represented as the executed
evidence hash.

The next experiment phase is intentionally absent. The provisional experiment
policy remains inactive, and no G3 manifest or preregistration claim is made.
