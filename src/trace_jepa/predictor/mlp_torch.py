from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType


@dataclass(frozen=True)
class TorchModules:
    torch: ModuleType
    nn: ModuleType


def require_torch() -> TorchModules:
    try:
        torch = importlib.import_module("torch")
        nn = importlib.import_module("torch.nn")
    except ImportError as exc:
        raise RuntimeError("Install the 'ml' optional dependencies") from exc
    return TorchModules(torch=torch, nn=nn)


def build_model(
    input_dim: int,
    action_dim: int,
    output_dim: int,
) -> object:
    modules = require_torch()
    torch = modules.torch
    nn = modules.nn

    class ActionPrefixMLP(nn.Module):  # type: ignore[name-defined]
        def __init__(self) -> None:
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim + action_dim, 128),
                nn.ReLU(),
                nn.Linear(128, 128),
                nn.ReLU(),
                nn.Linear(128, output_dim),
            )

        def forward(self, state: object, action: object) -> object:
            return self.net(torch.cat([state, action], dim=-1))

    return ActionPrefixMLP()
