import numpy as np
import pytest

from trace_jepa.perception.dinov2 import DINOv2EncoderSpec, DINOv2PatchEncoder


torch = pytest.importorskip("torch")


class _FakeDINO(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.projection = torch.nn.Linear(3, 6)

    def forward_features(self, values):
        pooled = torch.nn.functional.adaptive_avg_pool2d(values, (8, 8))
        tokens = pooled.permute(0, 2, 3, 1).reshape(len(values), 64, 3)
        return {"x_norm_patchtokens": self.projection(tokens)}


def test_dinov2_patch_encoder_preserves_spatial_tokens_and_freezes_model():
    model = _FakeDINO()
    encoder = DINOv2PatchEncoder(
        spec=DINOv2EncoderSpec(input_size=112),
        model=model,
    )
    images = np.zeros((2, 48, 64, 3), dtype=np.uint8)
    features = encoder.encode_images(images)
    assert features.shape == (2, 64, 6)
    assert features.dtype == np.float32
    assert all(not parameter.requires_grad for parameter in model.parameters())


def test_dinov2_patch_encoder_rejects_non_image_arrays():
    encoder = DINOv2PatchEncoder(model=_FakeDINO())
    with pytest.raises(ValueError, match="uint8"):
        encoder.encode_images(np.zeros((2, 3), dtype=np.float32))
