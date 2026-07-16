# Lab 4 - Flood-domain action-prefix prediction

## Goal

Train the first domain model that maps visible rescue state plus a candidate action to future mission predicates.

## Tasks

1. Generate the synthetic teaching dataset.
2. Inspect its manifest and verify that labels depend only on visible state and action.
3. Train the reference MLP.
4. Compare held-out error with the constant baseline.
5. Inspect the checkpoint manifest for the data hash, seed, normalization, action schema, and training snapshot.

## Commands

```bash
python scripts/generate_synthetic_dataset.py \
  --episodes 1000 \
  --output data/processed/synthetic_flood_trajectories.npz
python scripts/train_action_predictor.py \
  --dataset data/processed/synthetic_flood_trajectories.npz \
  --output models/checkpoints/toy_action_predictor.pt \
  --epochs 100
```

## Exit test

The selected validation checkpoint beats the constant baseline, and its manifest is sufficient to reconstruct the split and preprocessing.
