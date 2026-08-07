# WF-DFLD-01-SMALL v7 scientific-hardening protocol

Status: development protocol, frozen before v7 mechanics or evaluation were changed.

Implementation note (added after the audited mechanics were completed): the v7
mechanics and development-only coefficient record are frozen locally. The
`confirmatory-v6` ensemble remains unexecuted and may run only after the complete
acceptance file and its bound implementation commit are pushed. The acceptance
file discloses that its midnight timestamp is an administrative placeholder; the
first publishing Git commit time is authoritative.

## Purpose

This protocol corrects limitations identified in the publication-readiness audit of
WF-DFLD-01-SMALL. It creates a new, explicitly versioned simulator revision rather
than rewriting prior evidence. The v7 simulator remains a synthetic teaching model;
it is not a hydrodynamic forecast, demographic reconstruction, learned-model
effectiveness study, or operational emergency-response system.

## Immutable inherited evidence

The following Git objects at baseline commit
`c89a598c7dce03aa19e143cf4dafcd267e9dd3e5` are immutable. Tests MUST fail if a v7
change alters one of these objects.

| Evidence | Git object |
|---|---|
| `wf_dfld_01_small_v1.yaml` | `2fe3a3bb35f0048100a0dd442b31a0a6cb38c8fe` |
| v6 default configuration (to be archived as v2) | `d4ad63089fd00b3f7cdd46ea02e322e551262729` |
| v5 acceptance protocol | `206a553b1cc58b5d6491b807144a1be7c75e6e3c` |
| v6 acceptance protocol | `4796cd35b22ae7fd70cafdd18b3e043b2dcc5e9d` |
| `book_v1` reference tree | `4e24b3f361d0b43c662503179954ebbd4ea83285` |
| `book_v2` reference tree | `a8fd4f5ce8fd271084826391debf833840e254b6` |
| v1 publication-figure tree | `fb0ac156c57b71fdef0ad7d036fed962d4bcfe11` |
| v2 publication-figure tree | `3782b7cd0b79f1e53d257749e8117dd7228c6efa` |
| v5 validation report | `a9671dfa48840d04dde3ba1300360d5e4cef8e57` |
| v6 validation report | `73d050c1124cb064d1717c622286464d4535ae61` |

These identifiers are Git object hashes, not claims about scientific adequacy. The
adverse and amended historical results remain part of the audit trail.

## Frozen v7 decisions

- Scenario schema: `trace-delta-scenario-v3`.
- Generator: `delta-small-generator-v7` with a new v7 randomness namespace.
- Ground truth: keyed structure/tick/type hazards, version
  `delta-ground-truth-v4`.
- Observations: keyed zero/one/many channel, version `delta-observations-v4`.
- Coordination: evidence-delivery-only model, version `delta-coordination-v1`.
- Capacity: one physical resource may cover at most one concurrent incident;
  version `delta-demand-capacity-v3`.
- Validation: seed-cluster inference, version `delta-validation-v3`.
- Replay: deterministic scientific manifest separated from an execution receipt;
  version `delta-replay-manifest-v4`.
- Canonical environment: a digest-pinned Python 3.11 container and a hash-locked
  dependency set.
- Canonical predictor: the transparent Toy teaching fixture. Learned predictors are
  unqualified unless an independently frozen qualification artifact matches every
  governed field.
- Resource inventory is unchanged from v6. No resource is added or reclassified to
  force a target ratio.
- The primary load measure is strict physical concurrency. The v6 capped measure is
  retained only as `registered_normalized_coverable_load_index`.
- No numerical acceptance band is imposed on the new strict load ratio.

## Causal invariants

The simulator MUST enforce these invariants with common-random-number tests:

- `sigma` changes hazard and may change downstream truth.
- `kappa`, `mu`, and `delta` change resources, timing, or availability but not
  geography, weather, hydrology, exposure, truth, or raw observations.
- `iota` changes observations only.
- the exposure profile changes placement, occupancy, and vulnerability but not
  meteorology or hydrology.
- `phi` changes controller-visible authority routing and evidence delivery only.
- `pi` selects a within-predictor prior/calibration profile only.
- hidden lineage is unavailable to online policy, predictor, TRACE records,
  commitments, outcomes, and controller-facing figures.

## Evaluation discipline

Existing development seeds may be used for debugging and for fitting only the
declared baseline incident intercepts and observation coefficients. After those
values, the implementation, the environment digest, and all gates are frozen, 100
new seeds will be derived from
`SHA-256("WF-DFLD-01-SMALL|confirmatory-v6|index")` using the registered unsigned
31-bit reduction. The exact list will be committed and pushed before execution.

The confirmatory run will execute once against that remote commit in the canonical
environment. Failures will be reported without seed replacement or post-hoc
retuning.

## Scope exclusions

V7 does not add breach or cascade physics, casualty modeling, negotiated mutual aid,
crew duty cycles, federation, a second runtime, the full crossing network, a new UI,
or a trained Delta-specific JEPA predictor. Rio Vista resources remain explicitly
described as a preauthorized automatic-aid teaching schedule, not local inventory or
real-time operational availability.
