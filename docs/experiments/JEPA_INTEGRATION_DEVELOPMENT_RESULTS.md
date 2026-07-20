# V-JEPA Integration Development Results

## Study status

These are development-only results from synchronized synthetic sensor imagery.
No held-out test episode was generated, encoded, selected against, or evaluated.

## Experimental design

The study used 400 independent simulator episodes and 800 counterfactual action
rows. Complete episodes were deterministically assigned to train, tuning,
calibration, and validation partitions with counts of 220, 53, 61, and 66.
Both action rows from an episode remained in the same partition.

At each delivered drone survey, `flood-sim-drone-rgb-v2` captured 16 frames at
step 4 over a 61-source-frame span. The frozen official V-JEPA 2.1 ViT-B encoder
produced one 768-dimensional vector per content-addressed observation. The
structured input excluded the latent water depth and debris state used by the
camera and outcome adjudicator. Targets used the workbench zero-process-noise
water update at each action's arrival horizon.

The tuning split selected ridge regularization, the calibration split fitted
isotonic success calibration, and the validation split was evaluated once for
the reported development comparison. Uncertainty intervals use paired bootstrap
resampling over the 66 independent validation episodes.

## Model comparison

| Development model | Brier | NLL | ECE-10 | AUROC | Average precision | All-target MSE |
|---|---:|---:|---:|---:|---:|---:|
| Constant | 0.27708 | 0.74853 | 0.17536 | 0.5000 | 0.5499 | 0.09037 |
| Structured only | 0.16121 | 0.49410 | 0.11523 | 0.8597 | 0.8805 | 0.04856 |
| Visual only | **0.08841** | **0.29465** | **0.05295** | **0.9349** | **0.8884** | 0.04043 |
| Fused | 0.10401 | 0.33442 | 0.06463 | 0.9250 | 0.8805 | **0.02690** |
| Fused, episode-shuffled visual | 0.27189 | 0.73905 | 0.18444 | 0.6149 | 0.6918 | 0.08348 |

Paired episode-cluster bootstrap differences, reported as estimate and 95%
interval:

- fused minus structured Brier: `-0.05720` [`-0.13007`, `0.02021`];
- fused minus structured all-target MSE: `-0.02166`
  [`-0.04183`, `-0.00074`];
- fused minus episode-shuffled Brier: `-0.16788`
  [`-0.22804`, `-0.10300`];
- fused minus episode-shuffled all-target MSE: `-0.05658`
  [`-0.07195`, `-0.03891`].

The registered development criterion was satisfied. Fused prediction improved
both primary point estimates relative to structured-only prediction; the
all-target MSE interval excluded zero in the favorable direction; and both fused
metrics improved over the episode-shuffled visual control with intervals excluding
zero. The probability result is narrower: the fused-versus-structured Brier
interval includes zero, and visual-only prediction has the best Brier point
estimate.

## Predictor-version diagnostic

The controlled RQ5 diagnostic held prediction values fixed and changed only
whether a midmission replacement predictor was qualified. Across 20 decisions,
the replacement was unqualified for three decisions.

| Diagnostic quantity | Result |
|---|---:|
| Base-gate CLEARs using unqualified replacement evidence | 3 |
| Guarded CLEARs using unqualified replacement evidence | 0 |
| Guarded HOLDs during the unqualified interval | 3 |
| Registry hash chain valid | yes |
| Test seeds accessed | no |

This diagnostic establishes the implemented guard invariant; it does not estimate
end-to-end mission utility or predictor quality.

## Protocol amendments

Two amendments are retained in the public record:

1. The official encoder used 16 frames at step 4 instead of a dense 64-frame CPU
   path. The change was made before an official comparison was trained or
   inspected, preserves the declared source-frame interval, and matches the
   pinned upstream ViT-B evaluation sampling.
2. The negative control was corrected from independent action-row shuffling to
   complete-episode shuffling. This preserves the paired counterfactual actions
   associated with each source observation. The correction affected only the
   negative control; structured, visual, and fused predictions were unchanged.

The published protocol contains prose-only normalization of its claim boundary and
represents the registered gate-failure behavior as a declarative state. Registered
seeds, partitions, models, thresholds, metrics, and the positive development
criterion are unchanged.

## Artifact integrity

- executed protocol SHA-256:
  `bef71719f13b45fa2b95cd6797bf0acb19f6349669e9d598fafaa79fa58d8ecc`;
- published protocol SHA-256:
  `0851c4da6415cdb1bf9cebe46024bca57f086d4536014dec27b1666d62585405`;
- V-JEPA checkpoint SHA-256:
  `848a77c33cc9e6649ed2119c9bea1e2c569bcdab9539ff3e7c02ccc2959ddf4d`;
- synchronized dataset SHA-256:
  `73e9a3a2d0335a036b1c04de649995af81cb10a386f1d454527f25d6286b1b25`;
- episode inventory SHA-256:
  `116ca1e162c8f2a242c976f80cc8d669bf721b15816ab6b29382a0d0da3b10be`;
- development head SHA-256:
  `d1aa6adbfd974e284abea9baf7478d51119106d0bef3e97b2d1d913689e077b3`;
- sanitized deterministic report SHA-256:
  `8c70cc101066285d26114753f26e7ae0e35ab319af1f6e951366b3a7539cb320`;
- RQ5 controlled report SHA-256:
  `95299a5f56c9ce54bf34f445a5a008ab766271fed24f5d493c03ffb1ac4d9363`.

Generated observations, features, checkpoints, and detailed reports remain outside
Git.

## Interpretation limits

The results establish synchronized prototype integration, provenance, leakage
resistance, model-version guard behavior, and simulator-channel sensitivity. They
do not establish field-video generalization, cross-domain superiority, certified
safety, or operational effectiveness in emergency response.
