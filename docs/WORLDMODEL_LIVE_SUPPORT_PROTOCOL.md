# Live World-Model Supporting-Evidence Protocol

## Scope

This protocol evaluates a development-only integration boundary for learned
visual models. It does not replace the transparent surrogate used by TRACE and
does not modify TRACE policy, evidence gates, commitment semantics, refresh
policies, or authority checks.

Learned inference is assigned the fixed role `supporting-non-licensing`.
Learned outputs are stored for provenance and audit but are not used to calculate
TRACE gate quantities, select a plan, or license an action.

## Live execution path

The evaluated path is:

1. receive a controller-visible visual observation package;
2. verify the observation identifier, frame digest, manifest digest, sensor
   version, study partition, and timestamp;
3. bind the request to a complete model-bundle identity;
4. run an uncached learned-model inference;
5. write the latent output and receipt to a content-addressed artifact store;
6. append the completed inference as a new version of the originating TRACE
   record without re-evaluating its gates or consumer decision;
7. reproduce the exact artifact through a verified cache replay.

The service uses a bounded single-worker queue. Invalid observations, model
identity mismatches, unsupported actions, non-finite outputs, artifact tampering,
unsafe paths, saturation, and backend errors fail closed with typed receipts.

## Model identities

### V-JEPA 2.1

The V-JEPA backend loads the official encoder and masked latent predictor from
revision `204698b45b3712590f06245fbfba32d3be539812`. The checkpoint digest is
`848a77c33cc9e6649ed2119c9bea1e2c569bcdab9539ff3e7c02ccc2959ddf4d`.
The live backend predicts future spatiotemporal tokens from delivered video.
Flood-SAR actions do not enter this predictor, so the resulting latent is not an
action-conditioned route prediction.

### DINO-WM Flood-SAR adaptation

The operational DINO-WM backend uses the official DINOv2 ViT-S/14 encoder and a
Flood-SAR-trained action-conditioned latent predictor. Its identity is explicitly
`upstream-inspired-adaptation`, with DINO-WM revision
`0a9492fa12044b852ae9e001cc74604b79c8bb0c` recorded as its method basis. It is
not represented as an unmodified upstream DINO-WM runtime or robotics checkpoint.

A separate minimal port of the pinned upstream predictor is used only for the
numerical parity check.

## Development qualification

The frozen configuration is
[`configs/experiments/worldmodel_live_support_v1.yaml`](../configs/experiments/worldmodel_live_support_v1.yaml).
It contains 12 synthetic development episodes. No held-out or RQ1-RQ5 data is
generated or opened.

For each learned backend, the qualification runs:

- correctly aligned observations;
- static-video intervention;
- camera-stratified episode-shuffled intervention;
- a deterministic structured-feature reference;
- a deterministic ten-dimensional simple-visual reference.

The checks cover request balance, controller/audit separation, content identity,
input sensitivity, cache replay, and descriptive post-warm-up batch-one latency.
They do not score predictive accuracy or operational outcomes.

## Reproduction

The exact resolved GPU environment is recorded in
[`configs/environments/worldmodel_live_h100_v1.txt`](../configs/environments/worldmodel_live_h100_v1.txt).
It used PyTorch 2.7.0 with CUDA 12.8. CUDA-enabled PyTorch wheels must be
obtained from the official PyTorch package index before installing the remaining
recorded dependencies; an equivalent environment is acceptable when its package
and accelerator versions are captured with the resulting report.

Run and verify V-JEPA qualification:

```bash
python scripts/run_live_worldmodel_qualification.py \
  --model vjepa \
  --device cuda:0 \
  --vjepa-upstream "$VJEPA_UPSTREAM" \
  --vjepa-checkpoint-dir "$VJEPA_CHECKPOINT_DIR" \
  --output "$OUTPUT_ROOT/vjepa"

python scripts/verify_live_worldmodel_qualification.py \
  --report "$OUTPUT_ROOT/vjepa/vjepa_live_qualification_report.json" \
  --output-root "$OUTPUT_ROOT/vjepa" \
  --verification-output "$OUTPUT_ROOT/vjepa/independent_verification.json"
```

Run and verify DINO-WM qualification:

```bash
python scripts/run_live_worldmodel_qualification.py \
  --model dinowm \
  --device cuda:0 \
  --dinowm-checkpoint "$DINOWM_CHECKPOINT" \
  --dinov2-upstream "$DINOV2_UPSTREAM" \
  --output "$OUTPUT_ROOT/dinowm"

python scripts/verify_live_worldmodel_qualification.py \
  --report "$OUTPUT_ROOT/dinowm/dinowm_live_qualification_report.json" \
  --output-root "$OUTPUT_ROOT/dinowm" \
  --verification-output "$OUTPUT_ROOT/dinowm/independent_verification.json"
```

The parity and TRACE smoke commands expose their complete argument contracts with
`--help`. All output directories must be new or empty, and downloaded model
weights, observations, caches, and inference artifacts remain outside Git.

## Interpretation boundary

This protocol establishes executable integration, provenance binding,
fail-closed behavior, replayability, input-channel sensitivity, and descriptive
latency in a synthetic development environment. It does not establish predictive
superiority, safety, operational effectiveness, field-video transfer, or
performance on TRACE RQ1-RQ5.
