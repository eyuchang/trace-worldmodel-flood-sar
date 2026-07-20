# DINO-WM Integration Protocol

## Scope

This integration evaluates DINO-WM as a second open-source world model behind
the existing TRACE route-prediction interface. It does not modify TRACE evidence,
commitment, refresh, or authority semantics. The existing Flood-SAR
zero-process-noise dynamics define synchronized current and future observations.

Unlike an image-encoder baseline, DINO-WM predicts future spatial DINOv2 patch
embeddings conditioned on the candidate action. A separately calibrated
Flood-SAR head maps the predicted future state, action, and controller-visible
structured inputs to the existing route outcomes.

## Upstream method

The implementation follows the public DINO-WM method: a frozen DINOv2 encoder
produces spatial patch tokens and an action-conditioned transformer predicts
future tokens from offline trajectories. The design reference is upstream commit
`0a9492fa12044b852ae9e001cc74604b79c8bb0c`, released under the MIT license.

Flood-SAR does not reuse a robotics checkpoint because the upstream checkpoints
are tied to different observations and action spaces. The predictor is trained
only on synchronized Flood-SAR development trajectories. DINOv2 remains frozen.

## Development confirmation

The prospectively registered campaign contains 600 independent episodes with two
counterfactual actions per episode. Complete episodes are assigned to train,
tuning, calibration, and validation partitions. The fresh campaign seeds differ
from the earlier V-JEPA study. Test observations cannot be generated or encoded
without an activated freeze manifest.

The dynamics comparison uses future-patch mean squared error. Persistence and
shuffled-action controls test whether the learned transition contributes more
than static scene representation or action-independent evolution. The outcome
comparison includes structured-only, current-visual, predicted-future, fused,
and episode-shuffled predicted-future controls. Calibration and validation remain
separate from predictor fitting and hyperparameter selection.

All uncertainty intervals resample complete episodes, preserving the two related
action rows. The positive gate is declared in the experiment configuration. A
held-out evaluation is opened exactly once only if every gate condition passes.

## Claim boundary

Passing the gate would support a controlled simulator-domain result that the
TRACE interface can consume useful predictions from an action-conditioned
open-source world model. It would not establish operational safety, transfer to
field imagery, or generality across arbitrary model families.
