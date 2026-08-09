# WF-DFLD-01-SMALL registered reconstruction delivery record

## Evidence role and immutable execution identity

This record documents deterministic artifact-reconstruction evidence. It does
not relabel the failed original or recovery execution, restore untouched-holdout
status, or create a new confirmatory ensemble.

- execution role: `artifact-reconstruction-replication`
- GitHub run: `31291073813`
- workflow: `delta-artifact-reconstruction-v8.yml`
- annotated authorization tag:
  `wf-dfld-01-small-confirmatory-v8-artifact-reconstruction-replication-v1`
- source commit: `42cb7f17e32754feb970e3e3f498f7b0501c05af`
- failed original bound by the report: `31286349320`
- failed recovery bound by the report: `31289293944`
- retained GitHub artifact ID: `9031422771`
- retained GitHub artifact digest:
  `b97b5d6080f696f389a7c411f300c892fae996a3e8537d122119066d395295b2`

The workflow passed exact-tag, exact-commit, first-attempt, prior-failure, and
once-only checks before executing. It ran in the registered Python 3.11.14
Linux/amd64 environment, evaluated the 100 development seeds and the same 100
previously consumed confirmatory-v8 seeds, generated book v6, verified exact
scientific replay, regenerated publication v6, transferred ownership only for
the four declared output paths, and retained one source-bound artifact.

## Frozen bindings

| Binding | SHA-256 |
|---|---|
| Acceptance protocol v10 | `bae5dc6cf0c9f397f57501b9084962aeb788c21efba95dcbdc335ad2f4a8b470` |
| Scientific-input manifest file | `2254e6296ec0b24d10d91e722606e321da318dbc0e7b2d86a18a32645a7fdb8a` |
| Scientific-input core aggregate | `3337810e69d9fa575fc4acd50e182cea076321c1db0933a5abef6a7830918527` |
| Scientific-input full aggregate | `96f3f6ab567659044510410f2c2cc25b3c7915577a05f15c3e857e1333f844d3` |
| Environment contract | `f5ee29d8402a9b094769f3a272ec26a748f0e9ffccee5836097f69166bbc305a` |
| Dependency lock | `06b286ad1b4b4d2397af27e567de3c207db59e67400d329edd214032d58355e1` |
| Scenario configuration | `9daf9b649ec3f6b9ba803e8b375af9adb37aeddff87291bc2d075cd994374543` |
| Geography catalog | `6121aea138d7a9295a8d33ac83175ec98cd81f2d9f2aa46bf148b576dd13fddf` |
| Policy | `968c04a0df8d60c64ddec036fded53d1d3f332c756c3dde6b18a641b30fb6e20` |

## Registered reconstruction results

All frozen non-reconciliation gates passed: mean report volume, expected
peak-hour coverage, every observation-channel tolerance, nonzero operational
behavior, episode uniqueness, TRACE/outcome-link integrity, and runtime. There
was no strict-load numerical gate.

| Measure | Estimate | 95% interval |
|---|---:|---:|
| Observed calls per seed | 39.80 | 38.12–41.49 |
| Hour-four calls per seed | 12.24 | 11.35–13.18 |
| Finite strict-load median | 2.00 | 1.833–2.00 |
| Finite uncapped-load median | 1.50 | 1.25–1.50 |
| Finite historical normalized-index median | 1.75 | 1.60–2.00 |
| Allocations per seed | 9.49 | 9.11–9.89 |
| Refusals per seed | 17.62 | 16.67–18.56 |
| Visible-evidence repairs per seed | 12.69 | 11.90–13.51 |
| Selected pairwise precision | 0.815 | 0.787–0.841 |
| Selected pairwise recall | 0.946 | 0.933–0.958 |
| Selected pairwise F1 | 0.868 | 0.850–0.885 |

The preregistered paired endpoint was satisfied:

- false-merge difference, selected minus baseline: `-0.0351`, 95% interval
  `[-0.0637, -0.0067]`;
- pairwise-recall difference: `-0.0346`, 95% interval
  `[-0.0466, -0.0234]`, above the registered `-0.05` noninferiority margin.

The adverse secondary result is retained without qualification: the
false-report-merge difference was `+0.0396`, 95% interval
`[+0.0011, +0.0787]`. Thus the selected evidence graph reduced overall false
merges and met recall noninferiority, but merged the false-report subset more
often than the immutable baseline. It should not be described as uniformly
better across every reconciliation measure.

The descriptive book seed (`20260803`) realized 18 latent incidents, 28 calls,
8 allocations, 12 refusals, and 8 visible-evidence repairs. Its finite strict,
uncapped, historical normalized, and residual-pressure peaks were respectively
1.333, 1.000, 1.333, and 1.500. It had zero strict-unserviceable windows and
three residual-strict-unserviceable windows. Seven commitments completed in the
window and one remained active at scenario censoring.

Generate, run, and exact replay took `0.858` seconds in the registered
environment, below the frozen 55-second limit.

## Committed evidence and verification

| Evidence | SHA-256 |
|---|---|
| Validation report v6 | `3a071da87cd6a789d221b1b3fa69dfb2873132bc71a4dfeba6bb279ea0fbf7f9` |
| Registered-evidence identity | `d10be5bf205e2a153dd8b77c0f426fb291e66a9d1be7bdb086c687579177b577` |
| Registered-evidence registry | `14898c9d4e6dec8c5bd05798d73aa5431c47f0ae2e1101c58961aca55d01ce98` |
| Book replay manifest | `f52ae922a6a91a35816714286430a2bf701f5319c25a5cc01294fcc145dbb8c8` |
| Book execution receipt | `3f3d482a8e9d52f8b587b6825a627962ac9a4c35e06b09323aa775024af1b856` |
| Publication manifest | `6a6cee911784c089b66c328867dd47e649292aaa747cdc2cb72c09d705d369ae` |
| Machine-readable publication table | `ebd158fbe92d76f57e72c22fe47bbd659cc5869d02756693006e53f828cca6e0` |

The report was validated with `RegisteredEvidenceIdentity.from_report`; the
committed registry binds both its byte digest and canonical identity digest.
Independent local regeneration matched every replay-manifest-bound scientific
artifact byte-for-byte. The separate execution receipt differed as designed
because it records actual execution context and is not part of scientific byte
identity. Independent publication regeneration matched all eight committed
publication artifacts exactly.

The authoritative numerical source is
`docs/delta/figures/wf_dfld_01_small_v6/publication_result_table.json`. This
record and prose summaries must not supersede that machine-readable table.
