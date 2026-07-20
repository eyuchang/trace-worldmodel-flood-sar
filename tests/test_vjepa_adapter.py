import pytest
import numpy as np


def test_vjepa_pooling_contract_when_torch_is_available():
    torch = pytest.importorskip("torch")
    from trace_jepa.perception.vjepa import VJEPA2Encoder

    features = torch.arange(2 * 4 * 3, dtype=torch.float32).reshape(2, 4, 3)
    pooled = VJEPA2Encoder.pool_features(features)
    assert pooled.shape == (2, 3)
    assert torch.allclose(pooled, features.mean(dim=1))


def test_official_checkpoint_prefixes_are_removed():
    from trace_jepa.perception.download import clean_backbone_state_dict

    state = {
        "module.backbone.layer.weight": 1,
        "module.layer.bias": 2,
    }
    assert clean_backbone_state_dict(state) == {
        "layer.weight": 1,
        "layer.bias": 2,
    }


def test_official_single_clip_list_is_unwrapped():
    torch = pytest.importorskip("torch")
    from trace_jepa.perception.vjepa import VJEPA2Encoder

    class Encoder(torch.nn.Module):
        def forward(self, clip):
            assert clip.shape == (1, 3, 4, 8, 8)
            return torch.ones((1, 5, 7))

    adapter = object.__new__(VJEPA2Encoder)
    adapter.torch = torch
    adapter.device = "cpu"
    adapter.encoder = Encoder()
    adapter.processor = lambda frames: [torch.zeros((3, 4, 8, 8))]

    result = adapter.encode_frames(np.zeros((4, 8, 8, 3), dtype=np.uint8))
    assert result.shape == (1, 7)


def test_multiple_preprocessor_views_are_rejected():
    torch = pytest.importorskip("torch")
    from trace_jepa.perception.vjepa import VJEPA2Encoder

    adapter = object.__new__(VJEPA2Encoder)
    adapter.torch = torch
    adapter.device = "cpu"
    adapter.encoder = torch.nn.Identity()
    adapter.processor = lambda frames: [torch.zeros((3, 4, 8, 8))] * 2

    with pytest.raises(ValueError, match="multiple clips"):
        adapter.encode_frames(np.zeros((4, 8, 8, 3), dtype=np.uint8))
