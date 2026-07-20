from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from trace_jepa.util import sha256_file


@dataclass(frozen=True)
class DINOWMPredictorConfig:
    patch_count: int
    feature_dim: int
    action_count: int
    predictor_dim: int = 96
    depth: int = 2
    heads: int = 4
    mlp_dim: int = 192
    dropout: float = 0.1

    def validate(self) -> None:
        if min(
            self.patch_count,
            self.feature_dim,
            self.action_count,
            self.predictor_dim,
            self.depth,
            self.heads,
            self.mlp_dim,
        ) < 1:
            raise ValueError("DINO-WM predictor dimensions must be positive")
        if self.predictor_dim % self.heads:
            raise ValueError("predictor_dim must be divisible by heads")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0,1)")


def build_dinowm_predictor(config: DINOWMPredictorConfig):
    """Build the action-conditioned spatial residual transformer lazily."""

    try:
        import torch
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("DINO-WM requires the optional jepa dependencies") from exc

    config.validate()

    class ActionConditionedSpatialPredictor(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.input_projection = torch.nn.Linear(
                config.feature_dim, config.predictor_dim
            )
            self.action_embedding = torch.nn.Embedding(
                config.action_count, config.predictor_dim
            )
            self.position_embedding = torch.nn.Parameter(
                torch.zeros(1, config.patch_count, config.predictor_dim)
            )
            layer = torch.nn.TransformerEncoderLayer(
                d_model=config.predictor_dim,
                nhead=config.heads,
                dim_feedforward=config.mlp_dim,
                dropout=config.dropout,
                activation="gelu",
                batch_first=True,
                norm_first=True,
            )
            self.transformer = torch.nn.TransformerEncoder(
                layer,
                num_layers=config.depth,
                enable_nested_tensor=False,
            )
            self.output_normalization = torch.nn.LayerNorm(config.predictor_dim)
            self.delta_projection = torch.nn.Linear(
                config.predictor_dim, config.feature_dim
            )
            torch.nn.init.trunc_normal_(self.position_embedding, std=0.02)
            torch.nn.init.zeros_(self.delta_projection.weight)
            torch.nn.init.zeros_(self.delta_projection.bias)

        def forward(self, current, actions):
            if current.ndim != 3 or current.shape[1:] != (
                config.patch_count,
                config.feature_dim,
            ):
                raise ValueError("current latent tensor does not match predictor schema")
            if actions.ndim != 1 or len(actions) != len(current):
                raise ValueError("actions must contain one index per transition")
            tokens = self.input_projection(current)
            tokens = (
                tokens
                + self.position_embedding
                + self.action_embedding(actions)[:, None, :]
            )
            encoded = self.transformer(tokens)
            delta = self.delta_projection(self.output_normalization(encoded))
            return current + delta

    return ActionConditionedSpatialPredictor()


def save_dinowm_checkpoint(
    path: Path,
    model,
    config: DINOWMPredictorConfig,
    *,
    metadata: dict[str, object],
) -> str:
    import torch

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "checkpoint_schema": "flood-sar-dinowm-predictor-v1",
            "config": asdict(config),
            "metadata": metadata,
            "state_dict": model.state_dict(),
        },
        path,
    )
    return sha256_file(path)


def load_dinowm_checkpoint(path: Path):
    """Load a local predictor with PyTorch's restricted weights-only unpickler."""

    import torch

    path = Path(path)
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if payload.get("checkpoint_schema") != "flood-sar-dinowm-predictor-v1":
        raise ValueError("unsupported DINO-WM predictor checkpoint")
    config = DINOWMPredictorConfig(**payload["config"])
    model = build_dinowm_predictor(config)
    model.load_state_dict(payload["state_dict"], strict=True)
    model.eval()
    return model, config, dict(payload["metadata"])
