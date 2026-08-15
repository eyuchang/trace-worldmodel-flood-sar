# WF-DFLD-01-REFERENCE base validation-v2 result

## Status and evidence role

| Field | Value |
|---|---|
| Scenario | `WF-DFLD-01-REFERENCE` |
| Execution role | `original-base-reference-validation-recovery` |
| Authorization tag | `wf-dfld-01-reference-validation-v2-recovery-v2` |
| Workflow run | [`31858415326`](https://github.com/eyuchang/trace-worldmodel-flood-sar/actions/runs/31858415326) |
| Source commit | `7aae9ef84b0db69fd95d10d3b63aa8110555cd59` |
| Frozen scientific source | `2cb58539425af467ac068ba7ef7500891e2fbe78` |
| Missions | 100 independent `validation-v2` missions in 20 five-mission shards |
| Result | All ten registered exact integration gates passed |
| LEAP behavior | Excluded |

This is the first mission-executing evaluation of the protected Reference
`validation-v2` namespace. It validates the non-LEAP simulator, TRACE execution,
replay, recovery, causal-isolation, provenance, and security contracts. It is not
a policy-effectiveness comparison, a field-reliability study, a historical Delta
reconstruction, or evidence that LEAP or a learned predictor improves outcomes.

## Execution lifecycle

The original authorization run `31833291955` derived the same protected seed-list
identity but failed while uploading its root-owned plan; every mission and aggregate
job was skipped. Recovery-v1 run `31856190911` failed its annotated-tag identity
guard before seed derivation; every downstream job was skipped. Neither run observed
a scientific outcome.

Recovery-v2 retained the original namespace, seed-list digest, scientific inputs,
mechanics, coefficients, gates, and environment. Its authorization passed, all 20
shards completed once, and the aggregate disclosed the exact seed plan only beside
the completed report. The lifecycle failures remain in the report as adverse
governance history rather than being erased or relabeled.

## Exact integration gates

All missions and aggregate checks passed:

- causal-axis isolation under keyed common random numbers;
- canonical environment and performance limits;
- event, evidence, TRACE, commitment, authorization, and outcome-chain integrity;
- resource, crew, capacity, and outcome conservation;
- exact replay and deterministic publication;
- reachability of every registered fault family;
- hidden-truth exclusion and hidden-lineage deletion equivalence;
- uninterrupted-versus-restarted recovery equivalence;
- immutable Small preservation; and
- source, path, offline, and security controls.

No operational metric had a numerical acceptance gate. A demanding workload is
therefore a descriptive result, not a failed integration check.

## Descriptive mission-level results

Intervals are deterministic 10,000-resample mission-cluster bootstrap percentile
intervals. The mission seed—not an incident, report, decision, or commitment—is the
independent unit.

| Metric | Mean | 95% interval |
|---|---:|---:|
| Evaluation reports | 2,891.71 | 2,869.24–2,913.70 |
| Evaluation truth incidents | 1,992.04 | 1,981.42–2,003.05 |
| Evidence-acquisition requests | 1,260.36 | 1,226.34–1,291.87 |
| Allocations | 406.22 | 403.20–409.31 |
| Refusals | 1,887.34 | 1,871.15–1,903.77 |
| Nominal-path compensations | 0.00 | 0.00–0.00 |
| Nominal-path consistency debts | 0.00 | 0.00–0.00 |
| Peak finite strict concurrent load ratio | 25.250 | 24.290–26.225 |
| Strict-unserviceable windows | 15.84 | 13.10–18.68 |
| `kappa=0.5` scarcity peak finite strict load ratio | 29.376 | 27.788–31.095 |
| `kappa=0.5` scarcity strict-unserviceable windows | 18.12 | 15.22–21.08 |

The report-count and latent-incident means are close to the frozen synthetic design
targets of approximately 2,900 and 2,000 without forcing either value per mission.
The high refusal count, peak finite load, and unserviceable windows show that the
Reference workload is severely resource-constrained. That is relevant stress-test
evidence but does not establish operational service quality. The zero compensation
and consistency-debt values summarize the nominal execution path; the separately
registered fault path exercised the compensation/recovery contract and passed its
reachability, integrity, and restart gates.

## Retained evidence and identities

| Item | SHA-256 or internal digest |
|---|---|
| Report file | `b1e8403667d2755665fd5c99d522951bd5cb822ec095ef6330f83cd70721b83b` |
| Report internal digest | `605967175ae0adbce88699eb1b6b19b212af26cae0a7e56b3fc17bed4d533c27` |
| Seed-plan file | `1d5314981d8fe35da36146cc521324e9374762577ef1b87d10e15b346c8bba4c` |
| Seed-list digest | `2be02697a2379a974d709fda7b7285935227ae58a8ebe51fc38c0c48020ffa87` |
| Result-registry file | `6dd1344425e89e1acb2c65cff1acdc40d781eb10c286558d06c45f9bdf2d6475` |
| Result-registry internal digest | `509c6b57388c520c74db00a599b26eebd7ab8a37bb40a408710a00755fde81c1` |
| Recovery-governance aggregate | `23c5417c5d3e90b09f790247482daf661211236ec3dd75f26ffa662cf0c6a3f3` |
| Scientific-input aggregate | `f9cf4103d75b28d9c14aa5fdb7721552a099a0a8dfccde852401c62036ee8b86` |
| Base-validation freeze | `b401b976fd22c19d6f2f81100e011946b566a48443ccd21a62d525bf9da820b3` |

The committed registry binds the report, disclosed seed plan, and all 20 shard
receipts byte-for-byte and verifies that mission indices 0–99 occur exactly once.
Verify it from a clean checkout with:

```bash
python scripts/reference/manage_base_validation_result_v1.py \
  --repository-root . verify
```

Replication remains a separately authorized action. A later execution must verify
this registry exactly, identify itself as a replication, and cannot replace this
result.

## Claim and release limits

- The cohort, truth burden, reports, authorities, resources, breach, and faults are
  synthetic research mechanisms; they do not represent current emergency staffing,
  legal command, demographic incidence, or operational readiness.
- The reduced-order physical model is source-anchored but is not a historical
  reconstruction or flood forecast.
- The geography catalog is suitable for the frozen offline simulation. Public
  redistribution remains fail-closed until the repository-history and source-license
  delivery gate is satisfied.
- No policy-superiority, TRACE-versus-baseline, or LEAP-effectiveness claim follows
  from this integration validation. Those questions require separate protocols.
