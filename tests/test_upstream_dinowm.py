from __future__ import annotations

import pytest

from trace_jepa.worldmodels.upstream_dinowm import (
    DINOWM_SOURCE_COMMIT,
    UpstreamDINOWMConfig,
    build_upstream_dinowm,
    build_upstream_compatible_vit_predictor,
    load_upstream_dinowm_checkpoint,
    save_upstream_dinowm_checkpoint,
)


torch = pytest.importorskip("torch")


def _tiny_config() -> UpstreamDINOWMConfig:
    return UpstreamDINOWMConfig(
        num_patches=4,
        num_hist=3,
        visual_dim=6,
        action_dim=3,
        operational_dim=2,
        action_embedding_dim=2,
        operational_embedding_dim=2,
        depth=2,
        heads=2,
        mlp_dim=16,
        dim_head=4,
        dropout=0.0,
        embedding_dropout=0.0,
    )


def test_registered_defaults_match_pinned_upstream_architecture() -> None:
    config = UpstreamDINOWMConfig()
    assert config.num_hist == 3
    assert config.depth == 6
    assert config.heads == 16
    assert config.mlp_dim == 2048
    assert config.visual_dim == 384
    assert config.num_patches == 196
    assert DINOWM_SOURCE_COMMIT == "0a9492fa12044b852ae9e001cc74604b79c8bb0c"


def test_minimal_port_has_upstream_state_dict_names_and_device_aware_mask() -> None:
    model = build_upstream_compatible_vit_predictor(_tiny_config())
    keys = set(model.state_dict())
    assert "pos_embedding" in keys
    assert "transformer.layers.0.0.norm.weight" in keys
    assert "transformer.layers.0.0.to_qkv.weight" in keys
    assert "transformer.layers.0.0.to_out.0.weight" in keys
    assert "transformer.layers.0.1.net.1.weight" in keys
    assert "transformer.norm.weight" in keys
    assert "transformer.layers.0.0.bias" not in keys
    assert model.transformer.layers[0][0].bias.device.type == "cpu"


def test_causal_attention_prevents_future_frame_leakage() -> None:
    torch.manual_seed(3)
    config = _tiny_config()
    model = build_upstream_compatible_vit_predictor(config).eval()
    values = torch.randn(1, config.num_hist * config.num_patches, config.predictor_dim)
    changed = values.clone()
    changed[:, -config.num_patches :] += 100.0
    with torch.inference_mode():
        baseline = model(values)
        perturbed = model(changed)
    assert torch.allclose(
        baseline[:, : config.num_patches],
        perturbed[:, : config.num_patches],
        atol=1e-6,
        rtol=1e-6,
    )
    assert not torch.allclose(baseline[:, -config.num_patches :], perturbed[:, -config.num_patches :])


def test_flood_sar_model_uses_action_and_operational_conditioning() -> None:
    torch.manual_seed(5)
    config = _tiny_config()
    model = build_upstream_dinowm(config).eval()
    visual = torch.randn(1, config.num_hist, config.num_patches, config.visual_dim)
    operational = torch.zeros(1, config.num_hist, config.operational_dim)
    actions = torch.zeros(1, config.num_hist, config.action_dim)
    with torch.inference_mode():
        baseline = model.predict_next_visual(visual, operational, actions)
        action_changed = actions.clone()
        action_changed[:, :, 1] = 1.0
        action_prediction = model.predict_next_visual(visual, operational, action_changed)
        operation_changed = operational.clone()
        operation_changed[:, :, 0] = 1.0
        operation_prediction = model.predict_next_visual(visual, operation_changed, actions)
    assert baseline.shape == (1, config.num_patches, config.visual_dim)
    assert not torch.equal(baseline, action_prediction)
    assert not torch.equal(baseline, operation_prediction)


def test_upstream_dinowm_checkpoint_roundtrip_is_strict(tmp_path) -> None:
    torch.manual_seed(7)
    config = _tiny_config()
    model = build_upstream_dinowm(config).eval()
    visual = torch.randn(1, config.num_hist, config.num_patches, config.visual_dim)
    operational = torch.randn(1, config.num_hist, config.operational_dim)
    actions = torch.randn(1, config.num_hist, config.action_dim)
    with torch.inference_mode():
        expected = model(visual, operational, actions)
    checkpoint = tmp_path / "dinowm-v2.pt"
    digest = save_upstream_dinowm_checkpoint(
        checkpoint,
        model,
        config,
        metadata={"training_split_sha256": "a" * 64},
    )
    restored, restored_config, metadata = load_upstream_dinowm_checkpoint(checkpoint)
    with torch.inference_mode():
        actual = restored(visual, operational, actions)
    assert len(digest) == 64
    assert restored_config == config
    assert metadata["training_split_sha256"] == "a" * 64
    assert torch.equal(actual, expected)
