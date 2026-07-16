from __future__ import annotations


def require_torch():
    try:
        import torch
        from torch import nn
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install the 'ml' optional dependencies") from exc
    return torch, nn


def build_model(input_dim: int, action_dim: int, output_dim: int = 4):
    torch, nn = require_torch()

    class ActionPrefixMLP(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim + action_dim, 128),
                nn.ReLU(),
                nn.Linear(128, 128),
                nn.ReLU(),
                nn.Linear(128, output_dim),
            )

        def forward(self, state, action):
            return self.net(torch.cat([state, action], dim=-1))

    return ActionPrefixMLP()
