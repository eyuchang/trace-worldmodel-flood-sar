import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "models/manifests/vjepa2_1_vit_base_384.manifest.json"


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


def test_downloader_and_offline_path_share_immutable_encoder_pin(tmp_path: Path) -> None:
    from trace_jepa.perception.download import download_model, load_encoder_pin

    pin = load_encoder_pin(PIN, trusted_root=PIN.parent)
    assert pin["manifest_version"] == "trace-vjepa-encoder-pin-v1"
    assert pin["checkpoint"]["file_name"] == "vjepa2_1_vitb_dist_vitG_384.pt"
    with pytest.raises(ValueError, match="must not overwrite"):
        download_model(
            PIN,
            PIN,
            tmp_path,
            pin_root=PIN.parent,
            receipt_root=PIN.parent,
        )

    malformed = dict(pin)
    malformed["checkpoint"] = {**pin["checkpoint"], "sha256": "0" * 64}
    malformed_path = tmp_path / "malformed-pin.json"
    malformed_path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(ValueError, match="disagrees with source registry"):
        load_encoder_pin(malformed_path, trusted_root=tmp_path)
