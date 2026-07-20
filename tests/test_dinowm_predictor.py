import pytest

from trace_jepa.worldmodels.dinowm import (
    DINOWMPredictorConfig,
    build_dinowm_predictor,
    load_dinowm_checkpoint,
    save_dinowm_checkpoint,
)


torch = pytest.importorskip("torch")


def test_dinowm_predictor_is_action_conditioned_and_round_trips(tmp_path):
    torch.manual_seed(7)
    config = DINOWMPredictorConfig(
        patch_count=4,
        feature_dim=6,
        action_count=2,
        predictor_dim=8,
        depth=1,
        heads=2,
        mlp_dim=16,
        dropout=0.0,
    )
    model = build_dinowm_predictor(config)
    with torch.no_grad():
        model.delta_projection.weight.normal_(std=0.1)
    current = torch.randn(2, 4, 6)
    model.eval()
    prediction = model(current, torch.tensor([0, 1]))
    assert prediction.shape == current.shape
    assert not torch.equal(prediction[0], prediction[1])

    checkpoint = tmp_path / "predictor.pt"
    digest = save_dinowm_checkpoint(
        checkpoint,
        model,
        config,
        metadata={"development_only": True},
    )
    restored, restored_config, metadata = load_dinowm_checkpoint(checkpoint)
    assert len(digest) == 64
    assert restored_config == config
    assert metadata["development_only"] is True
    assert torch.equal(prediction, restored(current, torch.tensor([0, 1])))


def test_dinowm_predictor_validates_schema():
    config = DINOWMPredictorConfig(
        patch_count=4,
        feature_dim=6,
        action_count=2,
        predictor_dim=7,
        heads=2,
    )
    with pytest.raises(ValueError, match="divisible"):
        build_dinowm_predictor(config)
