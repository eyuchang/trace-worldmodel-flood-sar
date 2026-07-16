import pytest


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
