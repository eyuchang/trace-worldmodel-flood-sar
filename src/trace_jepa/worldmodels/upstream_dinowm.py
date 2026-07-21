from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from trace_jepa.util import sha256_file


DINOWM_SOURCE_REPOSITORY = "https://github.com/gaoyuezhou/dino_wm"
DINOWM_SOURCE_COMMIT = "0a9492fa12044b852ae9e001cc74604b79c8bb0c"


@dataclass(frozen=True)
class UpstreamDINOWMConfig:
    """Flood-SAR dimensions around the pinned upstream DINO-WM predictor."""

    num_patches: int = 196
    num_hist: int = 3
    visual_dim: int = 384
    action_dim: int = 8
    operational_dim: int = 4
    action_embedding_dim: int = 10
    operational_embedding_dim: int = 10
    depth: int = 6
    heads: int = 16
    mlp_dim: int = 2048
    dim_head: int = 64
    dropout: float = 0.1
    embedding_dropout: float = 0.0

    @property
    def predictor_dim(self) -> int:
        return self.visual_dim + self.action_embedding_dim + self.operational_embedding_dim

    def validate(self) -> None:
        integer_fields = (
            self.num_patches,
            self.num_hist,
            self.visual_dim,
            self.action_dim,
            self.operational_dim,
            self.action_embedding_dim,
            self.operational_embedding_dim,
            self.depth,
            self.heads,
            self.mlp_dim,
            self.dim_head,
        )
        if min(integer_fields) < 1:
            raise ValueError("DINO-WM dimensions must be positive")
        if not 0.0 <= self.dropout < 1.0 or not 0.0 <= self.embedding_dropout < 1.0:
            raise ValueError("DINO-WM dropout values must be in [0,1)")


def build_upstream_compatible_vit_predictor(config: UpstreamDINOWMConfig):
    """Build an audited minimal port of upstream ``models.vit.ViTPredictor``.

    Module names and arithmetic intentionally match upstream commit
    ``0a9492f`` so a state dictionary can be loaded directly for parity tests.
    The only implementation change is storing the causal mask as a nonpersistent
    device-aware buffer instead of allocating it unconditionally on CUDA.
    """

    try:
        import torch
        from einops import rearrange
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("DINO-WM requires the optional ML dependencies") from exc

    config.validate()

    def generate_mask_matrix(npatch: int, nwindow: int):
        zeros = torch.zeros(npatch, npatch)
        ones = torch.ones(npatch, npatch)
        rows = []
        for index in range(nwindow):
            rows.append(torch.cat([ones] * (index + 1) + [zeros] * (nwindow - index - 1), dim=1))
        return torch.cat(rows, dim=0).unsqueeze(0).unsqueeze(0)

    class FeedForward(torch.nn.Module):
        def __init__(self, dim, hidden_dim, dropout=0.0):
            super().__init__()
            self.net = torch.nn.Sequential(
                torch.nn.LayerNorm(dim),
                torch.nn.Linear(dim, hidden_dim),
                torch.nn.GELU(),
                torch.nn.Dropout(dropout),
                torch.nn.Linear(hidden_dim, dim),
                torch.nn.Dropout(dropout),
            )

        def forward(self, x):
            return self.net(x)

    class Attention(torch.nn.Module):
        def __init__(self, dim, heads=8, dim_head=64, dropout=0.0):
            super().__init__()
            inner_dim = dim_head * heads
            project_out = not (heads == 1 and dim_head == dim)
            self.heads = heads
            self.scale = dim_head**-0.5
            self.norm = torch.nn.LayerNorm(dim)
            self.attend = torch.nn.Softmax(dim=-1)
            self.dropout = torch.nn.Dropout(dropout)
            self.to_qkv = torch.nn.Linear(dim, inner_dim * 3, bias=False)
            self.to_out = (
                torch.nn.Sequential(torch.nn.Linear(inner_dim, dim), torch.nn.Dropout(dropout))
                if project_out
                else torch.nn.Identity()
            )
            self.register_buffer(
                "bias",
                generate_mask_matrix(config.num_patches, config.num_hist),
                persistent=False,
            )

        def forward(self, x):
            _, token_count, _ = x.size()
            x = self.norm(x)
            qkv = self.to_qkv(x).chunk(3, dim=-1)
            q, k, v = map(
                lambda tensor: rearrange(tensor, "b n (h d) -> b h n d", h=self.heads),
                qkv,
            )
            dots = torch.matmul(q, k.transpose(-1, -2)) * self.scale
            dots = dots.masked_fill(self.bias[:, :, :token_count, :token_count] == 0, float("-inf"))
            attention = self.dropout(self.attend(dots))
            output = torch.matmul(attention, v)
            output = rearrange(output, "b h n d -> b n (h d)")
            return self.to_out(output)

    class Transformer(torch.nn.Module):
        def __init__(self, dim, depth, heads, dim_head, mlp_dim, dropout=0.0):
            super().__init__()
            self.norm = torch.nn.LayerNorm(dim)
            self.layers = torch.nn.ModuleList([])
            for _ in range(depth):
                self.layers.append(
                    torch.nn.ModuleList(
                        [
                            Attention(dim, heads=heads, dim_head=dim_head, dropout=dropout),
                            FeedForward(dim, mlp_dim, dropout=dropout),
                        ]
                    )
                )

        def forward(self, x):
            for attention, feed_forward in self.layers:
                x = attention(x) + x
                x = feed_forward(x) + x
            return self.norm(x)

    class ViTPredictor(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.pos_embedding = torch.nn.Parameter(
                torch.randn(
                    1,
                    config.num_hist * config.num_patches,
                    config.predictor_dim,
                )
            )
            self.dropout = torch.nn.Dropout(config.embedding_dropout)
            self.transformer = Transformer(
                config.predictor_dim,
                config.depth,
                config.heads,
                config.dim_head,
                config.mlp_dim,
                config.dropout,
            )
            self.pool = "mean"

        def forward(self, x):
            _, token_count, _ = x.shape
            if token_count > self.pos_embedding.shape[1]:
                raise ValueError("DINO-WM token count exceeds the registered history window")
            x = self.dropout(x + self.pos_embedding[:, :token_count])
            return self.transformer(x)

    return ViTPredictor()


def build_upstream_dinowm(config: UpstreamDINOWMConfig):
    """Build a Flood-SAR world model around the upstream-compatible predictor."""

    try:
        import torch
        from einops import rearrange, repeat
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("DINO-WM requires the optional ML dependencies") from exc

    config.validate()

    class ProprioceptiveEmbedding(torch.nn.Module):
        """Exact Conv1d embedding used by the pinned upstream project."""

        def __init__(self, input_dim: int, embedding_dim: int):
            super().__init__()
            self.num_frames = 1
            self.tubelet_size = 1
            self.in_chans = input_dim
            self.emb_dim = embedding_dim
            self.patch_embed = torch.nn.Conv1d(
                input_dim,
                embedding_dim,
                kernel_size=1,
                stride=1,
            )

        def forward(self, values):
            return self.patch_embed(values.permute(0, 2, 1)).permute(0, 2, 1)

    class FloodSARDINOWM(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.predictor = build_upstream_compatible_vit_predictor(config)
            self.proprio_encoder = ProprioceptiveEmbedding(
                config.operational_dim,
                config.operational_embedding_dim,
            )
            self.action_encoder = ProprioceptiveEmbedding(
                config.action_dim,
                config.action_embedding_dim,
            )

        def condition(self, visual, operational, actions):
            expected_visual = (
                visual.ndim == 4
                and visual.shape[1] == config.num_hist
                and visual.shape[2:] == (config.num_patches, config.visual_dim)
            )
            if not expected_visual:
                raise ValueError("DINO-WM visual history does not match the registered schema")
            if operational.shape != (
                len(visual),
                config.num_hist,
                config.operational_dim,
            ):
                raise ValueError("DINO-WM operational history does not match the schema")
            if actions.shape != (len(visual), config.num_hist, config.action_dim):
                raise ValueError("DINO-WM action history does not match the schema")
            proprio = self.proprio_encoder(operational)
            action = self.action_encoder(actions)
            proprio = repeat(proprio.unsqueeze(2), "b t 1 d -> b t p d", p=config.num_patches)
            action = repeat(action.unsqueeze(2), "b t 1 d -> b t p d", p=config.num_patches)
            return torch.cat([visual, proprio, action], dim=-1)

        def predict_conditioned(self, conditioned):
            if conditioned.shape != (
                len(conditioned),
                config.num_hist,
                config.num_patches,
                config.predictor_dim,
            ):
                raise ValueError("DINO-WM conditioned history does not match the schema")
            flat = rearrange(conditioned, "b t p d -> b (t p) d")
            return rearrange(
                self.predictor(flat),
                "b (t p) d -> b t p d",
                t=config.num_hist,
                p=config.num_patches,
            )

        def forward(self, visual, operational, actions):
            return self.predict_conditioned(self.condition(visual, operational, actions))

        def predict_next_visual(self, visual, operational, actions):
            prediction = self.forward(visual, operational, actions)
            return prediction[:, -1, :, : config.visual_dim]

    return FloodSARDINOWM()


def save_upstream_dinowm_checkpoint(
    path: Path,
    model,
    config: UpstreamDINOWMConfig,
    *,
    metadata: dict[str, object],
) -> str:
    import torch

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "checkpoint_schema": "flood-sar-upstream-dinowm-v2",
            "upstream_repository": DINOWM_SOURCE_REPOSITORY,
            "upstream_commit": DINOWM_SOURCE_COMMIT,
            "config": asdict(config),
            "metadata": metadata,
            "state_dict": model.state_dict(),
        },
        path,
    )
    return sha256_file(path)


def load_upstream_dinowm_checkpoint(path: Path):
    import torch

    payload = torch.load(Path(path), map_location="cpu", weights_only=True)
    if payload.get("checkpoint_schema") != "flood-sar-upstream-dinowm-v2":
        raise ValueError("unsupported upstream-conformant DINO-WM checkpoint")
    if payload.get("upstream_commit") != DINOWM_SOURCE_COMMIT:
        raise ValueError("DINO-WM checkpoint references an unexpected upstream commit")
    config = UpstreamDINOWMConfig(**payload["config"])
    model = build_upstream_dinowm(config)
    model.load_state_dict(payload["state_dict"], strict=True)
    model.eval()
    return model, config, dict(payload["metadata"])
