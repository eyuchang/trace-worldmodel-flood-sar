import numpy as np

from trace_jepa.perception import MockVideoEncoder


def test_mock_encoder_is_deterministic_and_normalized():
    encoder = MockVideoEncoder(embedding_dim=16)
    a = encoder.encode(b"same observation")
    b = encoder.encode(b"same observation")
    c = encoder.encode(b"different observation")
    assert np.allclose(a, b)
    assert not np.allclose(a, c)
    assert np.isclose(np.linalg.norm(a), 1.0)
