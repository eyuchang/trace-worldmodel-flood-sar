# Predictor qualification and provenance

## August decision

Task 1 is completed as a predictor boundary and governance experiment. It does
not train or claim a Delta-specific JEPA predictor. V-JEPA's released
self-supervised/pretraining heads are not Flood-SAR action predictors.

| Implementation | Real execution path | Default status | Permitted claim |
|---|---|---|---|
| Toy | deterministic source-reviewed fixture | `QUALIFIED` teaching fixture | protocol and TRACE path coverage only |
| MLP | pickle-free NPZ loader and frozen structured schema | `UNQUALIFIED` | loading/substitution/governance behavior only |
| V-JEPA-backed | content-addressed frozen encoder features plus separate flood head | `UNQUALIFIED` | adapter/loading/substitution/governance behavior only |

## Common request

One `ActionPrefixPredictor` protocol receives a plan/grounded action and typed
controller-visible context: route/crossing belief, confidence, timestamp/age,
travel estimate, resource telemetry, weather/hydrology observations, selected
prior profile, and optional content-addressed visual-feature reference.

`pi` selects a versioned prior/calibration profile inside the configured
predictor. Predictor identity is a separate experimental factor.

## Required provenance

Every evidence object binds predictor and calibration versions/hashes, training
snapshot, feature/action schemas, supported action classes, adequacy status, and,
for V-JEPA, encoder version/checkpoint hash. The official pinned encoder manifest
is `models/manifests/vjepa2_1_vit_base_384.manifest.json`. Third-party weights are
not committed.

MLP loading validates checkpoint schema/dimensions, finite arrays, action names,
metadata, and exact file hash. V-JEPA loading additionally validates safe
observation IDs, regular non-symlink files, content digest, encoder/head
agreement, finite features, and calibration metadata. All NPZ loading uses
`allow_pickle=False`. Missing or mismatched evidence fails closed.

A learned model cannot become `QUALIFIED` through a constructor argument. A
verified `QualificationArtifact` must bind predictor/model, calibration,
encoder/checkpoint when applicable, feature and action schemas, exact action
classes, evaluation protocol/report hashes, adequacy status, issuer
identity/version, and claim limit. Any mismatch fails closed. The Toy artifact
is explicitly scoped to a non-empirical teaching fixture.

Visual feature references additionally bind feature-cache SHA-256, observation
digest, capture time, feature schema, encoder version, and checkpoint hash.
Inference rejects traversal, symlinks, nonregular files, future captures,
features older than 300 simulation seconds, dimension mismatch, non-finite
values, and digest mismatch before opening the feature array.

MLP model and calibration artifacts are separate and independently hashed.
Loading rejects unexpected arrays, malformed shapes or schemas, and non-finite
values, and uses an overflow-safe sigmoid.

## Offline V-JEPA path

CI fixtures are generated deterministically by:

```bash
.venv/bin/python scripts/build_delta_predictor_fixtures.py
```

The optional heavyweight command verifies/downloads the pinned official
checkpoint, encodes a synchronized local clip, writes a deterministic feature
cache, and optionally executes a separately supplied flood head:

```bash
.venv/bin/python scripts/run_delta_vjepa_offline.py --help
```

No official or project claim treats the CI head as calibrated effectiveness
evidence.

The encoder pin is immutable. The downloader consumes the pin and writes a
separate receipt; it is forbidden from overwriting the pin:

```bash
.venv/bin/trace-jepa-download \
  --pin-manifest models/manifests/vjepa2_1_vit_base_384.manifest.json \
  --receipt models/receipts/vjepa2_1_vit_base_384.download.json \
  --checkpoint-dir models/external/vjepa2
```

## Revalidation rule

Fixed-axis substitution tests hold scenario, observations, plans/actions, and
prior profile constant while predictor identity changes. Unqualified MLP/V-JEPA
evidence causes high-consequence decisions to `HOLD`. Qualification may clear
only the exact current predictor/calibration/model/action-class combination.
Superseded, mismatched, unregistered, pending, or unqualified evidence cannot
authorize a durable commitment.
