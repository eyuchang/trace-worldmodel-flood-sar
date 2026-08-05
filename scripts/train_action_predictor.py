from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from trace_jepa.predictor.mlp_torch import build_model, require_torch
from trace_jepa.util import sha256_file

LOGGER = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Train the starter action-prefix predictor")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--learning-rate", type=float, default=3e-3)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument(
        "--allow-underfit",
        action="store_true",
        help="write a checkpoint even when validation MSE does not beat the constant baseline",
    )
    args = parser.parse_args()

    if args.epochs < 1:
        raise SystemExit("--epochs must be positive")

    torch = require_torch().torch
    torch.set_num_threads(max(1, args.threads))
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)

    data = np.load(args.dataset)
    states_np = data["states"].astype(np.float32)
    actions_np = data["actions"].astype(np.float32)
    targets_np = data["targets"].astype(np.float32)
    if not (len(states_np) == len(actions_np) == len(targets_np)):
        raise ValueError("states, actions, and targets must contain the same number of rows")

    permutation = rng.permutation(len(states_np))
    split = max(1, int(0.8 * len(permutation)))
    train_index = permutation[:split]
    val_index = permutation[split:]
    if len(val_index) == 0:
        raise ValueError("dataset is too small to create a validation split")

    states = torch.tensor(states_np, dtype=torch.float32)
    actions = torch.tensor(actions_np, dtype=torch.float32)
    targets = torch.tensor(targets_np, dtype=torch.float32)
    train_idx = torch.tensor(train_index, dtype=torch.long)
    val_idx = torch.tensor(val_index, dtype=torch.long)

    # Normalize the state using training-only statistics and store those statistics
    # in the checkpoint so inference can reproduce the exact transformation.
    state_mean = states[train_idx].mean(dim=0, keepdim=True)
    state_std = states[train_idx].std(dim=0, keepdim=True).clamp_min(1e-6)
    normalized_states = (states - state_mean) / state_std

    model = build_model(
        states.shape[1],
        actions.shape[1],
        targets.shape[1],
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    loss_fn = torch.nn.MSELoss()

    best_state = None
    best_val_mse = float("inf")
    for epoch in range(args.epochs):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        prediction = model(normalized_states[train_idx], actions[train_idx])
        loss = loss_fn(prediction, targets[train_idx])
        loss.backward()
        optimizer.step()

        model.eval()
        with torch.no_grad():
            val_prediction = model(normalized_states[val_idx], actions[val_idx])
            val_mse = loss_fn(val_prediction, targets[val_idx]).item()
        if val_mse < best_val_mse:
            best_val_mse = val_mse
            best_state = {
                key: value.detach().cpu().clone() for key, value in model.state_dict().items()
            }
        if epoch in {0, args.epochs - 1} or (epoch + 1) % 25 == 0:
            LOGGER.info(
                "epoch=%03d train_mse=%.6f validation_mse=%.6f",
                epoch + 1,
                loss.item(),
                val_mse,
            )

    assert best_state is not None
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        val_prediction = model(normalized_states[val_idx], actions[val_idx])
        val_mse = loss_fn(val_prediction, targets[val_idx]).item()
        constant = targets[train_idx].mean(dim=0, keepdim=True).expand_as(targets[val_idx])
        baseline_mse = loss_fn(constant, targets[val_idx]).item()

    improvement = baseline_mse - val_mse
    beats_baseline = val_mse < baseline_mse
    LOGGER.info(
        "best_validation_mse=%.6f constant_baseline_mse=%.6f improvement=%.6f",
        val_mse,
        baseline_mse,
        improvement,
    )

    if not beats_baseline and not args.allow_underfit:
        raise SystemExit(
            "The predictor did not beat the constant baseline. Increase data/epochs or inspect the data contract. "
            "Use --allow-underfit only for debugging."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "input_dim": states.shape[1],
            "action_dim": actions.shape[1],
            "output_dim": targets.shape[1],
            "state_mean": state_mean.squeeze(0),
            "state_std": state_std.squeeze(0),
        },
        args.output,
    )
    manifest = {
        "checkpoint": str(args.output),
        "dataset": str(args.dataset),
        "dataset_sha256": sha256_file(args.dataset),
        "checkpoint_sha256": sha256_file(args.output),
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "seed": args.seed,
        "validation_rows": len(val_index),
        "validation_mse": val_mse,
        "constant_baseline_mse": baseline_mse,
        "beats_constant_baseline": beats_baseline,
        "improvement": improvement,
        "action_schema_version": "flood-actions-v1",
        "feature_contract_version": "action-prefix-features-v1",
        "predictor_version": "mlp-action-prefix-v1",
        "calibration_version": "mlp-uncalibrated-v1",
        "calibration_status": "unqualified_pending_external_calibration",
        "qualified_for_high_consequence": False,
        "training_snapshot": "synthetic-flood-v2",
    }
    manifest_path = args.output.with_suffix(args.output.suffix + ".json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    LOGGER.info("wrote checkpoint: %s", args.output)
    LOGGER.info("wrote checkpoint manifest: %s", manifest_path)


if __name__ == "__main__":
    main()
