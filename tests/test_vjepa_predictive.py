from __future__ import annotations

import hashlib

import numpy as np
import pytest

from trace_jepa.worldmodels.vjepa_predictive import (
    VJEPA21_SOURCE_COMMIT,
    VJEPA21FuturePredictor,
    VJEPA21PredictiveSpec,
)


torch = pytest.importorskip("torch")


class _Processor:
    def __call__(self, frames):
        return frames.permute(1, 0, 2, 3).float() / 255.0


class _Encoder(torch.nn.Module):
    def __init__(self, spec: VJEPA21PredictiveSpec):
        super().__init__()
        self.spec = spec
        self.scale = torch.nn.Parameter(torch.tensor(1.0))
        self.last_masks = None

    def forward(self, video, masks):
        self.last_masks = masks
        batch, _, frames, _, _ = video.shape
        tubelet_values = video.mean(dim=(1, 3, 4)).reshape(batch, frames, 1)
        tubelet_values = tubelet_values.repeat_interleave(
            self.spec.spatial_token_count,
            dim=1,
        )
        tokens = torch.cat(
            [tubelet_values, tubelet_values + 1.0, tubelet_values + 2.0],
            dim=-1,
        )
        index = masks[0].unsqueeze(-1).repeat(1, 1, tokens.shape[-1])
        return torch.gather(tokens, 1, index) * self.scale


class _Predictor(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.scale = torch.nn.Parameter(torch.tensor(1.0))
        self.last_context_masks = None
        self.last_target_masks = None

    def forward(self, encoded, context_masks, target_masks, mod):
        assert mod == "video"
        self.last_context_masks = context_masks
        self.last_target_masks = target_masks
        target_count = target_masks[0].shape[1]
        prediction = encoded.mean(dim=1, keepdim=True).repeat(1, target_count, 1)
        return prediction * self.scale, encoded


def _adapter(tmp_path):
    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"predictive-fixture")
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    spec = VJEPA21PredictiveSpec(
        crop_size=4,
        total_frames=4,
        context_frames=2,
        patch_size=2,
        tubelet_size=1,
        checkpoint_sha256=digest,
    )
    encoder = _Encoder(spec)
    predictor = _Predictor()
    return (
        VJEPA21FuturePredictor(
            encoder=encoder,
            predictor=predictor,
            processor=_Processor(),
            device="cpu",
            checkpoint_path=checkpoint,
            spec=spec,
        ),
        encoder,
        predictor,
    )


def _frames() -> np.ndarray:
    values = np.zeros((3, 4, 4, 3), dtype=np.uint8)
    values[1] = 64
    values[2] = 128
    return values


def test_registered_vjepa_revision_and_future_mask_defaults() -> None:
    spec = VJEPA21PredictiveSpec()
    assert VJEPA21_SOURCE_COMMIT == "204698b45b3712590f06245fbfba32d3be539812"
    assert spec.total_frames == 64
    assert spec.context_frames == 48
    assert spec.target_frames == 16
    assert spec.context_token_count == 24 * 24 * 24
    assert spec.target_token_count == 8 * 24 * 24


def test_predictor_preserves_tokens_and_uses_disjoint_future_masks(tmp_path) -> None:
    adapter, encoder, predictor = _adapter(tmp_path)
    prediction = adapter.predict_future_tokens(_frames())
    context_mask = encoder.last_masks[0]
    target_mask = predictor.last_target_masks[0]
    assert prediction.shape == (1, adapter.spec.target_token_count, 3)
    assert context_mask.shape == (1, adapter.spec.context_token_count)
    assert target_mask.shape == (1, adapter.spec.target_token_count)
    assert context_mask[0, 0].item() == 0
    assert context_mask[0, -1].item() == adapter.spec.context_token_count - 1
    assert target_mask[0, 0].item() == adapter.spec.context_token_count
    assert not set(context_mask.flatten().tolist()) & set(target_mask.flatten().tolist())


def test_masked_target_pixels_cannot_leak_into_predictions(tmp_path) -> None:
    adapter, _, _ = _adapter(tmp_path)
    zero_target = adapter.predict_future_tokens(_frames(), target_fill=0)
    white_target = adapter.predict_future_tokens(_frames(), target_fill=255)
    assert np.array_equal(zero_target, white_target)


def test_context_encoder_preserves_spatiotemporal_tokens(tmp_path) -> None:
    adapter, _, _ = _adapter(tmp_path)
    context = adapter.encode_context_tokens(_frames())
    assert context.shape == (1, adapter.spec.context_token_count, 3)
    assert context.ndim == 3
    assert all(not parameter.requires_grad for parameter in adapter.encoder.parameters())
    assert all(not parameter.requires_grad for parameter in adapter.predictor.parameters())


def test_vjepa_predictive_adapter_rejects_bad_inputs_and_checkpoint_identity(tmp_path) -> None:
    adapter, _, _ = _adapter(tmp_path)
    with pytest.raises(ValueError, match="uint8"):
        adapter.predict_future_tokens(np.zeros((3, 4, 4, 3), dtype=np.float32))
    with pytest.raises(ValueError, match="at least two"):
        adapter.predict_future_tokens(np.zeros((1, 4, 4, 3), dtype=np.uint8))

    checkpoint = tmp_path / "bad.pt"
    checkpoint.write_bytes(b"bad")
    with pytest.raises(ValueError, match="hash mismatch"):
        VJEPA21FuturePredictor(
            encoder=_Encoder(adapter.spec),
            predictor=_Predictor(),
            processor=_Processor(),
            device="cpu",
            checkpoint_path=checkpoint,
            spec=adapter.spec,
        )
