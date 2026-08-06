# WF-DFLD-01-SMALL v2 delivery report

Date: 2026-08-05 America/Los_Angeles  
Branch: `demo-delta-scenario`

## Outcome

Tasks 1 and 2 now include a runnable, deterministic Small simulator with the
common Toy/MLP/V-JEPA predictor boundary, full TRACE evidence/record/commitment
persistence, government-source geography, truth-first lossy observations,
capability-aware resource allocation, byte-identical replay, a write-once
confirmatory study, and deterministic publication artifacts.

The approved v2 amendment is complete. It preserves generator v5 and `book_v1`
as adverse audit evidence, introduces generator v6 with one preauthorized Rio
Vista engine and Zodiac rescue boat staged at T+5,400 seconds, and separates
intrinsic gross scenario load from controller-dependent residual pressure.

## Scientific result

| Measure | v5 preserved result | v6 amended result |
|---|---:|---:|
| Book observed calls | 45 | 45 |
| Book allocations / refusals / repairs | 7 / 28 / 10 | 13 / 22 / 10 |
| Book headline ratio | 3.0 hybrid pressure | 1.5 gross compatible load |
| Primary confirmatory median headline ratio | 3.0 (`confirmatory-v4`) | 1.5 (`confirmatory-v5`) |

For the 100 untouched `confirmatory-v5` seeds:

- mean observed calls were 38.55 (95% CI 37.00–40.10);
- hour-four mean calls were 11.18 (95% CI 10.24–12.12), so the configured
  expectation of 12/hour lies inside the interval;
- median peak gross load was 1.5 (deterministic bootstrap 95% CI 1.333–1.5);
- mean peak gross load was 1.536, with range 1.0–2.0;
- median finite residual pressure was 2.25 (95% CI 2.0–3.0);
- all 100 TRACE chains verified;
- geography, weather, gauges, crossing states, truth, observations, and prior
  profile were byte-identical between v5 and v6 for all 100 seeds;
- every preregistered numeric and chain gate passed.

The book seed remains descriptive. Its allocation share was 0.3714, it exercised
allocation, refusal, and visible-evidence repair, and it had 11 residual
unserviceable windows. Residual pressure is not presented as the 1.5 headline.

## Provenance and immutable evidence

Implementation history:

- `9324085` — froze v6 mechanics, resource provenance, metric contracts, tests,
  and the exact `confirmatory-v5` seed list before holdout execution;
- `e5c16f7` — recorded the single write-once 100-development/100-confirmatory
  validation execution;
- `462311f` — published documentation, `book_v2`, and deterministic figures;
- `830e0e0` — rebound generated manifests to the commit containing all inputs.

Primary SHA-256 values:

| Object | SHA-256 |
|---|---|
| v2 scenario configuration | `81a986f1f27a883c1bee5ab06dfc55621af1b32dce386c14ca10f3e73a364ae6` |
| v6 acceptance protocol and exact seeds | `eb3a8aefc56b8d30cfc2853f1b5bb0536b962b937f003dbcf9e8f089c8937d7c` |
| Rio Vista factual source extract | `3b57433c0810cde8aa563420ac2e48683b99dc0d4e5fe3dd88bebf32064e4d91` |
| write-once validation report | `2754b9d92c2df4e0c20026a388e092ec1039b315d38617c76ac8b3be8d44a24c` |
| `book_v2` replay manifest | `78b02f0ef670bb3dc8f01f60922ccc171671ddea674a533f7f9a385ff0725263` |
| publication manifest | `ec44c1bbd5be92c8ccac0ac70c399ee091413fb0c70fbe0feef621c40a7ba303` |

The archived v1 configuration retains SHA-256
`a97cb37c0547183828019ca5bc56662af9d3cc73db5eebc906f8e3f11975939b`;
the `book_v1` manifest retains
`ad69d57fde24db6c7c49080c71398bdbec59f7f164e42470c62e94c1e6581e19`.

## Verification

- 121 tests collected: 120 passed, one optional heavyweight V-JEPA test skipped
  because PyTorch is intentionally absent from the lightweight environment.
- Scoped Ruff lint and formatting passed.
- Strict mypy passed for 22 Delta/predictor source files.
- `git diff --check` passed.
- Local generate + run + clean replay: 0.342 seconds, below the 55-second gate.
- GitHub Actions Python 3.11 CI run
  [31066613191](https://github.com/eyuchang/trace-worldmodel-flood-sar/actions/runs/31066613191)
  passed all install, lint, typing, and test steps in 44 seconds.
- Static `book_v1` and `book_v2` manifests verify; `book_v2` replay and all five
  SVG figures regenerate byte-for-byte without network access.
- Security/leakage tests cover path traversal, unsafe feature IDs, symlinks,
  pickle avoidance, checksum/version mismatch, non-finite arrays, artifact
  tampering, offline execution, and hidden-truth exclusion from public runtime
  artifacts. Callback tokens and description tokens are synthetic.

The GitHub runner emitted a non-failing platform annotation that Actions using
Node.js 20 are currently forced to Node.js 24. It did not affect the Python 3.11
quality job.

## Exact commands

```bash
.venv/bin/trace-jepa-delta-small run \
  --output data/scenario/delta/reference/wf_dfld_01_small_book_v2
.venv/bin/trace-jepa-delta-small replay \
  --reference data/scenario/delta/reference/wf_dfld_01_small_book_v2 \
  --output /tmp/delta-book-v2-replay
.venv/bin/trace-jepa-delta-small publish \
  --reference data/scenario/delta/reference/wf_dfld_01_small_book_v2 \
  --output /tmp/delta-book-v2-figures
```

The committed confirmatory report is the original write-once execution. Running
`validate` again creates an independent replication and must use a new output
path; the validator refuses to overwrite an existing report.

## Limitations and deferred scope

- Rio Vista availability and T+5,400 staging are frozen teaching assumptions,
  not real-time staffing, dispatch, or readiness claims.
- The source extract retains official URLs and URL hashes, but upstream content
  hashes are unavailable because the City server returned HTTP 403 to the
  reproducibility client. No upstream page is redistributed.
- Station 55 uses a secondary address geocode, not a surveyed coordinate.
- Hydrology remains reduced-order teaching physics, geography remains
  simulation-grade, and the cohort remains synthetic and nonrepresentative.
- `service_units=2` is a normalized analytical load unit, not personnel count or
  a field-validated response-capacity claim.
- Task 3 remains untouched: breach/cascade dynamics, mutual-aid negotiation and
  tiers, crew duty cycles, federation, the full crossing network, casualty
  modeling, and a learned Delta-specific JEPA effectiveness study are deferred.
